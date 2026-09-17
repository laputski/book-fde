# Extracted from the book automatically. Lines above the mark are not part of the listing.
from stubs import Chunk  # noqa: F401
# --- the listing ---
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class LiveIndex:
    """Истина о том, что живо: версии документов и надгробия отозванных."""
    rows: dict[str, Chunk] = field(default_factory=dict)
    live_version: dict[str, int] = field(default_factory=dict)
    revoked: set[str] = field(default_factory=set)

    def publish(self, doc_id: str, version: int, chunks: Sequence[Chunk]) -> tuple[int, int]:
        stale = [cid for cid, row in self.rows.items()
                 if row.doc_id == doc_id and row.version < version]
        for cid in stale:
            del self.rows[cid]
        for chunk in chunks:
            self.rows[chunk.id] = chunk
        self.live_version[doc_id] = version
        self.revoked.discard(doc_id)
        return len(chunks), len(stale)

    def revoke(self, doc_id: str) -> None:
        self.revoked.add(doc_id)                 # надгробие ставится сразу
        for cid in [cid for cid, row in self.rows.items() if row.doc_id == doc_id]:
            del self.rows[cid]

    def alive(self, chunk: Chunk) -> bool:
        return (chunk.doc_id not in self.revoked
                and chunk.version >= self.live_version.get(chunk.doc_id, chunk.version))


@dataclass
class SearchReplica:
    """Реплика поиска, догоняющая индекс с задержкой в минуты."""
    rows: dict[str, Chunk] = field(default_factory=dict)

    def sync(self, index: LiveIndex) -> None:
        self.rows = dict(index.rows)

    def search(self, term: str, index: LiveIndex, k: int = 5) -> list[Chunk]:
        found = [row for row in self.rows.values() if term in row.text]
        return [row for row in found if index.alive(row)][:k]   # надгробия читаются в запросе


if __name__ == "__main__":
    def make(cid: str, doc_id: str, version: int, text: str) -> Chunk:
        return Chunk(id=cid, doc_id=doc_id, text=text, acl=frozenset({"icu"}), version=version)

    index, replica = LiveIndex(), SearchReplica()
    index.publish("gl-17", 3, [make("gl-17:v3", "gl-17", 3, "порог лактата 2 ммоль/л")])
    replica.sync(index)
    assert [row.id for row in replica.search("лактата", index)] == ["gl-17:v3"]

    added, removed = index.publish("gl-17", 4, [make("gl-17:v4", "gl-17", 4, "порог лактата 4 ммоль/л")])
    assert (added, removed) == (1, 1)                    # старая версия удалена
    assert replica.search("лактата", index) == []        # реплика отстала, надгробие сработало
    replica.sync(index)
    assert [row.id for row in replica.search("лактата", index)] == ["gl-17:v4"]

    index.revoke("gl-17")
    assert replica.rows and replica.search("лактата", index) == []   # отзыв действует до синхронизации
    print("строк в реплике:", len(replica.rows), "· видно в поиске:", len(replica.search("лактата", index)))
