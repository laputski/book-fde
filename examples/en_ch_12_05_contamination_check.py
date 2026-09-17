from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

N = 6                                   # n-gram length in words
FLAG_AT = 0.5                           # share of the example's n-grams that match


def ngrams(text: str, n: int = N) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", text.lower())
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


@dataclass(frozen=True)
class EvalItem:
    id: str
    question: str
    reference: str


@dataclass
class Split:
    kept: list[str] = field(default_factory=list)
    excluded: dict[str, str] = field(default_factory=dict)      # id -> source of the match


def check(items: Sequence[EvalItem], sources: Mapping[str, str]) -> Split:
    index: dict[tuple[str, ...], set[str]] = {}
    for name, text in sources.items():
        for gram in ngrams(text):
            index.setdefault(gram, set()).add(name)
    split = Split()
    for item in items:
        grams = ngrams(f"{item.question} {item.reference}")
        hits: dict[str, int] = {}
        for gram in grams:
            for name in index.get(gram, ()):
                hits[name] = hits.get(name, 0) + 1
        worst = max(hits.items(), key=lambda kv: (kv[1], kv[0]), default=("", 0))
        if grams and worst[1] / len(grams) >= FLAG_AT:
            split.excluded[item.id] = worst[0]
        else:
            split.kept.append(item.id)
    return split


if __name__ == "__main__":
    items = [
        EvalItem("e1", "How long does the bank take to resolve a card dispute?",
                 "A card dispute is resolved within 45 days of the date of the request."),
        EvalItem("e2", "Can a card block be lifted without a visit to a branch?",
                 "Yes, an operator lifts the block after checking identity with the code word."),
        EvalItem("e3", "What is the limit without a PIN?", "Without a PIN you can pay up to 50 euros."),
    ]
    sources = {
        "prompt:few-shot-3": ("Example. Question: how long does the bank take to resolve a card "
                              "dispute? Answer: a card dispute is resolved within 45 days of the "
                              "date of the request."),
        "kb:incident-0412": ("Incident review. Can a card block be lifted without a visit to a "
                             "branch? Yes, an operator lifts the block after checking identity "
                             "with the code word."),
        "kb:cards-tariff": ("Contactless payment without entering a PIN is allowed for purchases "
                            "of up to 50 euros inclusive."),
    }
    split = check(items, sources)
    assert split.excluded == {"e1": "prompt:few-shot-3", "e2": "kb:incident-0412"}
    assert split.kept == ["e3"]                 # a shared fact in the tariff is not a leak
    print("excluded from the run:", split.excluded)
