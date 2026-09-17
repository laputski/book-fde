"""Helper names for the book's listings.

The listings lean on names whose implementations are beside the point:
a model client, a vector store, a warehouse, a tracer, a clock. They are
declared here as Protocols with real types, each with a deterministic
Fake implementation, so that type checking and execution exercise the
listings in substance instead of walking around them. Nothing here talks
to a network.

The file is maintained by hand alongside extract_examples.py and is not
part of the book.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

logger = logging.getLogger("book")

# --- The model client --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    finish_reason: str          # "stop" | "length" | "refusal" | "tool_call"
    usage: Usage
    model: str
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: Mapping[str, Any]
    call_id: str = ""


@runtime_checkable
class LLMClient(Protocol):
    def complete(self, prompt: str, *, model: str = "model-pro", max_output_tokens: int = 1024,
                 tools: Sequence[Mapping[str, Any]] = ()) -> Completion: ...


class FakeLLM:
    """Answers from a script; the n-th call returns the n-th scripted reply."""

    def __init__(self, replies: Sequence[str | Completion] = (), *, model: str = "model-pro") -> None:
        self.replies = list(replies)
        self.calls: list[str] = []
        self.model = model

    def complete(self, prompt: str, *, model: str = "model-pro", max_output_tokens: int = 1024,
                 tools: Sequence[Mapping[str, Any]] = ()) -> Completion:
        self.calls.append(prompt)
        if not self.replies:
            reply: str | Completion = "{}"
        else:
            reply = self.replies.pop(0)
        if isinstance(reply, Completion):
            return reply
        tokens_in = max(1, len(prompt) // 4)
        tokens_out = max(1, len(reply) // 4)
        finish = "length" if tokens_out > max_output_tokens else "stop"
        return Completion(text=reply, finish_reason=finish,
                          usage=Usage(tokens_in, min(tokens_out, max_output_tokens)), model=model or self.model)


def count_tokens(text: str) -> int:
    """A stable approximation: four characters per token, Cyrillic costs more."""
    cyrillic = sum(1 for ch in text if "Ѐ" <= ch <= "ӿ")
    return max(1, (len(text) - cyrillic) // 4 + cyrillic // 2)


# --- Documents and retrieval -------------------------------------------------


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    text: str
    acl: frozenset[str] = frozenset()
    version: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    doc_id: str
    text: str
    acl: frozenset[str] = frozenset()
    version: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Hit:
    chunk: Chunk
    score: float
    source: str = "vector"


def embed(text: str, dims: int = 8) -> list[float]:
    """A deterministic pseudo-embedding: hashing, not semantics."""
    digest = hashlib.blake2b(text.lower().encode("utf-8"), digest_size=dims).digest()
    return [(b - 128) / 128 for b in digest]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


@runtime_checkable
class VectorStore(Protocol):
    def upsert(self, chunks: Sequence[Chunk]) -> None: ...
    def delete(self, chunk_ids: Sequence[str]) -> None: ...
    def search(self, vector: Sequence[float], k: int = 10,
               allowed_groups: frozenset[str] | None = None) -> list[Hit]: ...


class FakeVectorStore:
    def __init__(self) -> None:
        self.rows: dict[str, tuple[Chunk, list[float]]] = {}

    def upsert(self, chunks: Sequence[Chunk]) -> None:
        for c in chunks:
            self.rows[c.id] = (c, embed(c.text))

    def delete(self, chunk_ids: Sequence[str]) -> None:
        for cid in chunk_ids:
            self.rows.pop(cid, None)

    def search(self, vector: Sequence[float], k: int = 10,
               allowed_groups: frozenset[str] | None = None) -> list[Hit]:
        hits = []
        for chunk, vec in self.rows.values():
            if allowed_groups is not None and not (chunk.acl & allowed_groups):
                continue
            hits.append(Hit(chunk, cosine(vector, vec)))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]


# --- Identity ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Principal:
    id: str
    groups: frozenset[str] = frozenset()
    tenant: str = "default"


# --- Systems of record --------------------------------------------------------


@runtime_checkable
class Warehouse(Protocol):
    def query(self, sql: str, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]: ...


class FakeWarehouse:
    def __init__(self, tables: Mapping[str, Sequence[Mapping[str, Any]]] | None = None) -> None:
        self.tables = {k: [dict(r) for r in v] for k, v in (tables or {}).items()}
        self.queries: list[str] = []

    def query(self, sql: str, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        self.queries.append(sql)
        for name, rows in self.tables.items():
            if name in sql:
                return [dict(r) for r in rows]
        return []


# --- Time, tracing, storage --------------------------------------------------


@runtime_checkable
class Clock(Protocol):
    def now(self) -> float: ...


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class SystemClock:
    def now(self) -> float:
        return time.time()


@dataclass
class Span:
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    children: list[Span] = field(default_factory=list)
    duration_ms: float = 0.0

    def set(self, key: str, value: Any) -> None:
        self.attributes[key] = value


class Tracer:
    """A tree of spans kept in memory; enough to assert on in a listing."""

    def __init__(self) -> None:
        self.root = Span("root")
        self._stack = [self.root]

    @contextlib.contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[Span]:
        s = Span(name, dict(attributes))
        self._stack[-1].children.append(s)
        self._stack.append(s)
        started = time.perf_counter()
        try:
            yield s
        finally:
            s.duration_ms = (time.perf_counter() - started) * 1000
            self._stack.pop()

    def spans(self) -> list[Span]:
        out: list[Span] = []

        def walk(s: Span) -> None:
            for c in s.children:
                out.append(c)
                walk(c)
        walk(self.root)
        return out


tracer = Tracer()


class KeyValue:
    """An in-memory key-value store standing in for Redis, Firestore, and the like."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def set(self, key: str, value: str) -> None:
        self.data[key] = value

    def setnx(self, key: str, value: str) -> bool:
        if key in self.data:
            return False
        self.data[key] = value
        return True


def to_json(model: BaseModel | Mapping[str, Any]) -> str:
    if isinstance(model, BaseModel):
        return model.model_dump_json()
    return json.dumps(dict(model), ensure_ascii=False, sort_keys=True)


Handler = Callable[..., Any]
