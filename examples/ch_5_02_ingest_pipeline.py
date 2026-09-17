from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

MAX_CHUNK = 220         # символов в чанке до переноса остатка в следующий
MIN_TEXT = 40           # меньше этого парсер считается не справившимся
HEADING = re.compile(r"^##\s+(.+)$")


@dataclass(frozen=True)
class RawDoc:
    """То, что пришло из SharePoint: текст либо извлечён парсером, либо нет."""
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
    """Разбор по заголовкам: чанк не пересекает границу раздела."""
    parts: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        found = HEADING.match(line.strip())
        if found:
            parts.append((found.group(1), []))
        else:
            parts[-1][1].append(line)
    return [(head, "\n".join(body).strip()) for head, body in parts if "".join(body).strip()]


def pack(heading: str, body: str, limit: int = MAX_CHUNK) -> list[str]:
    """Длинный раздел режется по границам предложений, короткий остаётся целым."""
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
            return 0                      # тот же хеш: писать нечего
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
            quarantine.hold(doc, "парсер не извлёк текста")
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
    body = ("## Показания\nЛактат выше 2 ммоль/л требует повторного измерения.\n"
            "## Действия\nПосев крови берут до антибиотика. Дозу вводят за час.\n")
    docs = [RawDoc("gl-17", "Сепсис", "icu", 3, body),
            RawDoc("gl-18", "Скан 2009 года", "cardio", 1, None),
            RawDoc("gl-19", "Экспорт без текста", "cardio", 1, "   ")]
    index, quarantine = Index(), Quarantine()
    assert ingest(docs, index, quarantine) == len(index.rows) == 2
    assert {c.heading for c in index.rows.values()} == {"Показания", "Действия"}
    assert all(c.acl_groups == frozenset({"icu"}) for c in index.rows.values())
    assert [d for d, _ in quarantine.rows] == ["gl-18", "gl-19"]   # отложены в карантин
    assert ingest(docs, index, quarantine) == 0                    # повтор ничего не пишет
    assert ingest([RawDoc("gl-17", "Сепсис", "icu", 4, body)], index, quarantine) == 2
    assert {c.doc_version for c in index.rows.values()} == {3, 4}  # старые чанки ещё в индексе
    print("разделов в индексе:", len(index.rows), "· в карантине:", len(quarantine.rows))
