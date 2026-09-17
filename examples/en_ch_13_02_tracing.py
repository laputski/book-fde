from __future__ import annotations

import contextvars
import functools
import hashlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

type Attr = str | int | float | bool


@dataclass
class ManualClock:
    t: float = 0.0

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t = round(self.t + seconds, 6)


@dataclass(frozen=True)
class SpanContext:
    trace_id: str
    span_id: str


@dataclass
class Span:
    name: str
    context: SpanContext
    parent_id: str | None
    start: float
    end: float = 0.0
    status: str = "ok"
    attributes: dict[str, Attr] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 6)


@dataclass(frozen=True)
class Completion:
    input_tokens: int               # under the OTel conventions it includes cached tokens
    cache_read_tokens: int
    output_tokens: int


CURRENT: contextvars.ContextVar[SpanContext | None] = contextvars.ContextVar("span", default=None)
BAGGAGE: contextvars.ContextVar[tuple[tuple[str, str], ...]] = contextvars.ContextVar("baggage", default=())


@contextmanager
def baggage(items: dict[str, str]) -> Iterator[None]:
    """Request attributes inherited by every span further down the tree."""
    token = BAGGAGE.set(BAGGAGE.get() + tuple(items.items()))
    try:
        yield
    finally:
        BAGGAGE.reset(token)


def inject() -> dict[str, str]:
    """W3C headers for HTTP; in MCP the same keys travel in params._meta."""
    ctx = CURRENT.get()
    assert ctx is not None, "inject outside a span"
    return {"traceparent": f"00-{ctx.trace_id}-{ctx.span_id}-01",
            "baggage": ",".join(f"{k}={v}" for k, v in BAGGAGE.get())}


@contextmanager
def extracted(carrier: dict[str, str]) -> Iterator[None]:
    """The receiving side: the remote parent and the baggage from the headers."""
    _, trace_id, span_id, _ = carrier["traceparent"].split("-")
    pairs = tuple((k, v) for k, v in (p.split("=", 1) for p in carrier["baggage"].split(",") if p))
    parent, bag = CURRENT.set(SpanContext(trace_id, span_id)), BAGGAGE.set(pairs)
    try:
        yield
    finally:
        BAGGAGE.reset(bag)
        CURRENT.reset(parent)


class Tracer:
    def __init__(self, service: str, clock: ManualClock) -> None:
        self.service = service
        self.clock = clock
        self.finished: list[Span] = []
        self._n = 0

    def _id(self, size: int) -> str:
        self._n += 1
        return hashlib.blake2b(f"{self.service}:{self._n}".encode(), digest_size=size).hexdigest()

    @contextmanager
    def span(self, name: str, attributes: dict[str, Attr] | None = None) -> Iterator[Span]:
        parent = CURRENT.get()
        ctx = SpanContext(parent.trace_id if parent else self._id(16), self._id(8))
        inherited: dict[str, Attr] = dict(BAGGAGE.get())
        span = Span(name, ctx, parent.span_id if parent else None, self.clock.now(),
                    attributes=inherited | (attributes or {}))
        token = CURRENT.set(ctx)
        try:
            yield span
        except Exception as err:
            span.status = "error"
            span.attributes["error.type"] = type(err).__name__
            raise
        finally:
            CURRENT.reset(token)
            span.end = self.clock.now()
            self.finished.append(span)

    def _wrap[**P, R](self, name: str, attributes: dict[str, Attr],
                      after: Callable[[Span, Any], None] | None = None
                      ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        def decorator(fn: Callable[P, R]) -> Callable[P, R]:
            @functools.wraps(fn)
            def inner(*args: P.args, **kwargs: P.kwargs) -> R:
                with self.span(name, attributes) as span:
                    result = fn(*args, **kwargs)
                    if after is not None:
                        after(span, result)
                return result
            return inner
        return decorator

    def llm[**P](self, model: str) -> Callable[[Callable[P, Completion]], Callable[P, Completion]]:
        def usage(span: Span, c: Completion) -> None:
            span.attributes |= {"gen_ai.usage.input_tokens": c.input_tokens,
                                "gen_ai.usage.cache_read.input_tokens": c.cache_read_tokens,
                                "gen_ai.usage.output_tokens": c.output_tokens}
        return self._wrap(f"chat {model}", {"gen_ai.operation.name": "chat",
                                             "gen_ai.request.model": model}, usage)

    def tool[**P, R](self, name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
        return self._wrap(f"execute_tool {name}", {"gen_ai.operation.name": "execute_tool",
                                                   "gen_ai.tool.name": name})

    def retrieval[**P, R](self, source: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
        return self._wrap(f"retrieval {source}", {"gen_ai.operation.name": "retrieval",
                                                  "gen_ai.data_source.id": source})


if __name__ == "__main__":
    clock = ManualClock()
    gateway = Tracer("gateway", clock)
    billing = Tracer("mcp-billing", clock)             # another process with its own tracer

    @gateway.retrieval("kb-consumer")
    def search(query: str) -> list[str]:
        clock.advance(0.3)
        return ["kb-112", "kb-587"]

    @gateway.llm("model-flash")
    def chat(prompt: str, seconds: float, usage: tuple[int, int, int]) -> Completion:
        clock.advance(seconds)
        return Completion(*usage)

    def backend(headers: dict[str, str]) -> int:
        with extracted(headers), billing.span("SELECT charges", {"db.system.name": "postgresql"}):
            clock.advance(0.2)
        return 300

    outcomes: Iterator[TimeoutError | None] = iter([TimeoutError("billing: no answer within 2 s"), None])

    @gateway.tool("get_charges")
    def get_charges(account: str) -> int:
        if (failure := next(outcomes)) is not None:
            clock.advance(2.0)
            raise failure
        clock.advance(0.1)
        return contextvars.Context().run(backend, inject())   # an empty context, as in another process

    request = {"orion.tenant": "consumer", "orion.feature": "agent_assist", "orion.user": "u-5f2a"}
    with (baggage(request), gateway.span("POST /assist"),
          gateway.span("invoke_agent assist", {"gen_ai.operation.name": "invoke_agent"})):
        with gateway.span("step 1", {"orion.agent.step": 1}):
            search("why were 300 roubles charged")
            chat("plan", 1.1, (5_000, 4_200, 60))
        with gateway.span("step 2", {"orion.agent.step": 2}):
            try:
                get_charges("acc-17")
            except TimeoutError:
                clock.advance(0.2)                     # backoff before the retry
                get_charges("acc-17")
            chat("answer", 2.3, (13_290, 4_200, 180))

    spans = gateway.finished + billing.finished
    by_id = {s.context.span_id: s for s in spans}
    assert len({s.context.trace_id for s in spans}) == 1             # one trace, the MCP server included
    assert all(s.parent_id in by_id for s in spans if s.parent_id)    # no orphans
    assert all(s.attributes["orion.tenant"] == "consumer" for s in spans)
    tools = [s for s in spans if s.name == "execute_tool get_charges"]
    assert [t.status for t in tools] == ["error", "ok"]
    assert billing.finished[0].parent_id == tools[1].context.span_id
    llm = [s for s in spans if s.attributes.get("gen_ai.operation.name") == "chat"]
    assert sum(int(s.attributes["gen_ai.usage.input_tokens"]) for s in llm) == 18_290
    parents = {s.parent_id for s in spans}
    slowest = max((s for s in spans if s.context.span_id not in parents), key=lambda s: s.duration)
    root = next(s for s in spans if s.parent_id is None)
    step_2 = next(s for s in spans if s.name == "step 2")
    assert root.duration == 6.2 and step_2.duration == 4.8
    assert slowest.name == "chat model-flash" and slowest.parent_id == step_2.context.span_id
    print(f"trace {root.context.trace_id[:8]}: {len(spans)} spans, the longest is {slowest.name} in step 2")
