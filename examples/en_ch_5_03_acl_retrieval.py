# Extracted from the book automatically. Lines above the mark are not part of the listing.
from stubs import Chunk, Hit, Principal, cosine, embed  # noqa: F401
# --- the listing ---
from collections.abc import Sequence
from dataclasses import dataclass, field


class AclViolation(Exception):
    """The post-check found what the filter should never have let through."""


@dataclass
class AclVectorStore:
    """A store that filters by tenant and groups before it ranks."""
    rows: dict[str, tuple[Chunk, list[float]]] = field(default_factory=dict)
    ranked: int = 0

    @staticmethod
    def visible(chunk: Chunk, principal: Principal) -> bool:
        return (chunk.metadata.get("tenant") == principal.tenant
                and bool(chunk.acl & principal.groups))

    def upsert(self, chunks: Sequence[Chunk]) -> None:
        for chunk in chunks:
            self.rows[chunk.id] = (chunk, embed(chunk.text))

    def search(self, vector: Sequence[float], k: int,
               principal: Principal | None) -> list[Hit]:
        hits = [Hit(chunk, cosine(vector, vec)) for chunk, vec in self.rows.values()
                if principal is None or self.visible(chunk, principal)]
        self.ranked = len(hits)
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:k]


def rerank(query: str, hits: Sequence[Hit]) -> list[Hit]:
    """A stand-in cross-encoder: the share of query words found in the chunk."""
    words = set(query.lower().split())

    def overlap(hit: Hit) -> float:
        return len(words & set(hit.chunk.text.lower().split())) / len(words)

    return sorted(hits, key=overlap, reverse=True)


def retrieve(store: AclVectorStore, principal: Principal, query: str, k: int = 3,
             candidates: int = 20, prefilter: bool = True) -> list[Hit]:
    vector = embed(query)
    hits = store.search(vector, candidates, principal if prefilter else None)
    top = rerank(query, hits)[:k]
    for hit in top:
        if not AclVectorStore.visible(hit.chunk, principal):
            raise AclViolation(f"{hit.chunk.id} is outside the rights of {principal.id}")
    return top


if __name__ == "__main__":
    def make(cid: str, dept: str, tenant: str, text: str) -> Chunk:
        return Chunk(id=cid, doc_id=cid.split("#")[0], text=text,
                     acl=frozenset({dept}), metadata={"tenant": tenant})

    store = AclVectorStore()
    store.upsert([
        make("gl-17#1", "icu", "meridian", "the lactate threshold in sepsis is 2 mmol"),
        make("gl-31#1", "cardio", "meridian", "the troponin threshold in coronary syndrome"),
        make("gl-44#1", "psych", "meridian", "the risk threshold in suicidal behaviour review"),
        make("gl-90#1", "icu", "harbor", "the lactate threshold in another network protocol"),
    ])
    doctor = Principal("u-7", frozenset({"icu", "cardio"}), tenant="meridian")
    hits = retrieve(store, doctor, "the lactate threshold in sepsis")
    assert {hit.chunk.id for hit in hits} == {"gl-17#1", "gl-31#1"}
    visible = store.ranked
    assert visible == 2                          # only visible chunks are ranked
    try:
        retrieve(store, doctor, "risk threshold", prefilter=False)
    except AclViolation as err:
        assert "gl-44#1" in str(err)
    else:
        raise AssertionError("the post-check must catch a foreign chunk")
    print("ranked", visible, "chunks of", len(store.rows), "· returned", len(hits))
