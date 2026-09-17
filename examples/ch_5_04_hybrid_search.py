# Extracted from the book automatically. Lines above the mark are not part of the listing.
from stubs import Chunk, FakeVectorStore, Principal, embed  # noqa: F401
# --- the listing ---
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

TOKEN = re.compile(r"[\w.-]+")
RRF_K = 60


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


@dataclass
class LexicalStore:
    """BM25 по тем же чанкам: редкие коды и аббревиатуры, которые вектор смазывает."""
    chunks: list[Chunk] = field(default_factory=list)
    k1: float = 1.2
    b: float = 0.75

    def search(self, query: str, principal: Principal, k: int) -> list[str]:
        allowed = [c for c in self.chunks if c.acl & principal.groups]
        if not allowed:
            return []
        bags = [tokens(c.text) for c in allowed]
        avg = sum(len(bag) for bag in bags) / len(bags)
        scored: list[tuple[str, float]] = []
        for chunk, bag in zip(allowed, bags, strict=True):
            score = 0.0
            for term in set(tokens(query)):
                tf = bag.count(term)
                if not tf:
                    continue
                df = sum(1 for other in bags if term in other)
                idf = math.log(1 + (len(allowed) - df + 0.5) / (df + 0.5))
                norm = tf + self.k1 * (1 - self.b + self.b * len(bag) / avg)
                score += idf * tf * (self.k1 + 1) / norm
            if score:
                scored.append((chunk.id, score))
        scored.sort(key=lambda row: row[1], reverse=True)
        return [cid for cid, _ in scored[:k]]


def rrf(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Слияние по обратным рангам: складываются места, а не несравнимые оценки."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for place, cid in enumerate(ranking, 1):
            scores[cid] = scores.get(cid, 0.0) + 1 / (k + place)
    return sorted(scores.items(), key=lambda row: row[1], reverse=True)


def hybrid(query: str, principal: Principal, lexical: LexicalStore,
           vectors: FakeVectorStore, k: int = 3, depth: int = 10) -> list[str]:
    lex = lexical.search(query, principal, depth)
    vec = [hit.chunk.id for hit in
           vectors.search(embed(query), depth, allowed_groups=principal.groups)]
    return [cid for cid, _ in rrf([lex, vec])[:k]]


if __name__ == "__main__":
    def make(cid: str, dept: str, text: str) -> Chunk:
        return Chunk(id=cid, doc_id=cid.split("#")[0], text=text, acl=frozenset({dept}))

    corpus = [
        make("gl-17#1", "icu", "сепсис по коду R65.2 требует измерения лактата"),
        make("gl-17#2", "icu", "лактат выше двух ммоль на литр повторяют через час"),
        make("gl-31#1", "cardio", "тропонин при коронарном синдроме измеряют дважды"),
        make("gl-44#1", "psych", "код R65.2 в психиатрической выписке не применяется"),
    ]
    lexical = LexicalStore(corpus)
    vectors = FakeVectorStore()
    vectors.upsert(corpus)
    doctor = Principal("u-7", frozenset({"icu", "cardio"}))

    assert lexical.search("R65.2", doctor, 5) == ["gl-17#1"]     # точный код находит только лексика
    assert "gl-44#1" not in hybrid("R65.2", doctor, lexical, vectors)
    merged = rrf([["только-лексика", "оба"], ["оба"]])
    assert merged[0][0] == "оба"     # найденное обоими способами выше найденного одним
    top = hybrid("лактат R65.2", doctor, lexical, vectors)
    assert "gl-17#1" in top and "gl-44#1" not in top
    print("слияние вернуло:", top)
