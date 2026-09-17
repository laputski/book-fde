# Extracted from the book automatically. Lines above the mark are not part of the listing.
from stubs import Chunk  # noqa: F401
# --- the listing ---
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class LiveIndex:
    """The truth about what is alive: document versions and the tombstones of the revoked."""
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
        self.revoked.add(doc_id)                 # the tombstone is written at once
        for cid in [cid for cid, row in self.rows.items() if row.doc_id == doc_id]:
            del self.rows[cid]

    def alive(self, chunk: Chunk) -> bool:
        return (chunk.doc_id not in self.revoked
                and chunk.version >= self.live_version.get(chunk.doc_id, chunk.version))


@dataclass
class SearchReplica:
    """The serving replica, minutes behind the index it copies."""
    rows: dict[str, Chunk] = field(default_factory=dict)

    def sync(self, index: LiveIndex) -> None:
        self.rows = dict(index.rows)

    def search(self, term: str, index: LiveIndex, k: int = 5) -> list[Chunk]:
        found = [row for row in self.rows.values() if term in row.text]
        return [row for row in found if index.alive(row)][:k]   # tombstones read at query time


if __name__ == "__main__":
    def make(cid: str, doc_id: str, version: int, text: str) -> Chunk:
        return Chunk(id=cid, doc_id=doc_id, text=text, acl=frozenset({"icu"}), version=version)

    index, replica = LiveIndex(), SearchReplica()
    index.publish("gl-17", 3, [make("gl-17:v3", "gl-17", 3, "lactate threshold 2 mmol/l")])
    replica.sync(index)
    assert [row.id for row in replica.search("lactate", index)] == ["gl-17:v3"]

    added, removed = index.publish("gl-17", 4, [make("gl-17:v4", "gl-17", 4, "lactate threshold 4 mmol/l")])
    assert (added, removed) == (1, 1)                    # the old version is removed
    assert replica.search("lactate", index) == []        # the replica lags, the tombstone holds
    replica.sync(index)
    assert [row.id for row in replica.search("lactate", index)] == ["gl-17:v4"]

    index.revoke("gl-17")
    assert replica.rows and replica.search("lactate", index) == []   # revocation precedes the sync
    print("rows in the replica:", len(replica.rows), "· visible in search:", len(replica.search("lactate", index)))
