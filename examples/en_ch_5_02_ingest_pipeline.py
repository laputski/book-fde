from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

MAX_CHUNK = 220         # characters per chunk before the rest moves to the next one
MIN_TEXT = 40           # below this the parser counts as having failed
HEADING = re.compile(r"^##\s+(.+)$")


@dataclass(frozen=True)
class RawDoc:
    """What arrived from SharePoint: the text was either extracted or it was not."""
    id: str
    title: str
    department: str
    version: int
    text: str | None


@dataclass(frozen=True)
class IndexedChunk:
    id: str
    doc_id: str
    heading: str
    text: str
    acl_groups: frozenset[str]
    doc_version: int
    content_hash: str


def sections(text: str) -> list[tuple[str, str]]:
    """Splitting on headings: a chunk never crosses a section boundary."""
    parts: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        found = HEADING.match(line.strip())
        if found:
            parts.append((found.group(1), []))
        else:
            parts[-1][1].append(line)
    return [(head, "\n".join(body).strip()) for head, body in parts if "".join(body).strip()]


def pack(heading: str, body: str, limit: int = MAX_CHUNK) -> list[str]:
    """A long section is cut on sentence boundaries, a short one stays whole."""
    pieces: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        if current and len(current) + len(sentence) + 1 > limit:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return [f"{heading}. {piece}" if heading else piece for piece in pieces]


def content_hash(doc: RawDoc, text: str) -> str:
    payload = f"{doc.id}|{doc.version}|{doc.department}|{text}"
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=12).hexdigest()


@dataclass
class Index:
    rows: dict[str, IndexedChunk] = field(default_factory=dict)

    def upsert(self, chunk: IndexedChunk) -> int:
        if chunk.id in self.rows:
            return 0                      # same hash: nothing to write
        self.rows[chunk.id] = chunk
        return 1


@dataclass
class Quarantine:
    rows: list[tuple[str, str]] = field(default_factory=list)

    def hold(self, doc: RawDoc, reason: str) -> None:
        if all(held != doc.id for held, _ in self.rows):
            self.rows.append((doc.id, reason))


def ingest(docs: Iterable[RawDoc], index: Index, quarantine: Quarantine) -> int:
    written = 0
    for doc in docs:
        if doc.text is None or len(doc.text.strip()) < MIN_TEXT:
            quarantine.hold(doc, "the parser extracted no text")
            continue
        for heading, body in sections(doc.text):
            for piece in pack(heading, body):
                digest = content_hash(doc, piece)
                written += index.upsert(IndexedChunk(
                    id=f"{doc.id}:{digest}", doc_id=doc.id, heading=heading, text=piece,
                    acl_groups=frozenset({doc.department}), doc_version=doc.version,
                    content_hash=digest))
    return written


if __name__ == "__main__":
    body = ("## Indications\nA lactate above 2 mmol/l calls for a second measurement.\n"
            "## Actions\nBlood cultures precede the antibiotic. The dose follows within an hour.\n")
    docs = [RawDoc("gl-17", "Sepsis", "icu", 3, body),
            RawDoc("gl-18", "A scan from 2009", "cardio", 1, None),
            RawDoc("gl-19", "An export with no text", "cardio", 1, "   ")]
    index, quarantine = Index(), Quarantine()
    assert ingest(docs, index, quarantine) == len(index.rows) == 2
    assert {c.heading for c in index.rows.values()} == {"Indications", "Actions"}
    assert all(c.acl_groups == frozenset({"icu"}) for c in index.rows.values())
    assert [d for d, _ in quarantine.rows] == ["gl-18", "gl-19"]   # held in quarantine
    assert ingest(docs, index, quarantine) == 0                    # a rerun writes nothing
    assert ingest([RawDoc("gl-17", "Sepsis", "icu", 4, body)], index, quarantine) == 2
    assert {c.doc_version for c in index.rows.values()} == {3, 4}  # the old chunks are still there
    print("sections indexed:", len(index.rows), "· quarantined:", len(quarantine.rows))
