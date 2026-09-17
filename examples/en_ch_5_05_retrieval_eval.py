from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

NOT_INDEXED = "not indexed"
HIDDEN = "hidden by the filter"
CANDIDATES = "missed by candidate generation"
RANKING = "below the cut at k"
FOUND = "found"


@dataclass(frozen=True)
class Question:
    qid: str
    text: str
    gold: frozenset[str]           # the chunks that must appear in the answer


@dataclass(frozen=True)
class Diagnosis:
    qid: str
    rank: int | None
    stage: str                     # exactly where the right answer was lost


@dataclass
class Report:
    recall_at_k: float
    mrr: float
    rows: list[Diagnosis]

    def failed(self, stage: str) -> list[str]:
        return [row.qid for row in self.rows if row.stage == stage]


def diagnose(question: Question, ranked: Sequence[str], indexed: frozenset[str],
             visible: frozenset[str], k: int) -> Diagnosis:
    places = [i for i, cid in enumerate(ranked, 1) if cid in question.gold]
    if places and places[0] <= k:
        return Diagnosis(question.qid, places[0], FOUND)
    if not question.gold & indexed:
        return Diagnosis(question.qid, None, NOT_INDEXED)
    if not question.gold & visible:
        return Diagnosis(question.qid, None, HIDDEN)
    if not places:
        return Diagnosis(question.qid, None, CANDIDATES)
    return Diagnosis(question.qid, places[0], RANKING)


def evaluate(questions: Sequence[Question], run: Callable[[Question], list[str]],
             indexed: frozenset[str], visible: frozenset[str], k: int = 5) -> Report:
    rows = [diagnose(q, run(q), indexed, visible, k) for q in questions]
    found = [row for row in rows if row.stage == FOUND and row.rank]
    return Report(recall_at_k=len(found) / len(rows),
                  mrr=sum(1 / row.rank for row in found if row.rank) / len(rows),
                  rows=rows)


if __name__ == "__main__":
    questions = [
        Question("q1", "the lactate threshold in sepsis", frozenset({"gl-17#1"})),
        Question("q2", "the suicide risk review", frozenset({"gl-44#1"})),
        Question("q3", "how long images are kept", frozenset({"gl-52#3"})),
        Question("q4", "when the antibiotic is given", frozenset({"gl-17#4"})),
    ]
    runs: dict[str, list[str]] = {
        "q1": ["gl-31#1", "gl-17#1", "gl-90#1"],
        "q2": ["gl-31#1", "gl-90#1"],
        "q3": ["gl-31#1"],
        "q4": ["gl-31#1", "gl-90#1", "gl-52#1", "gl-52#2", "gl-44#1", "gl-17#4"],
    }
    indexed = frozenset({"gl-17#1", "gl-17#4", "gl-31#1", "gl-44#1", "gl-90#1",
                         "gl-52#1", "gl-52#2"})
    visible = indexed - {"gl-44#1"}          # psychiatry is closed to this principal
    report = evaluate(questions, lambda q: runs[q.qid], indexed, visible, k=5)

    assert report.recall_at_k == 0.25 and report.mrr == 0.125
    assert report.failed(HIDDEN) == ["q2"]           # indexed, but not for this reader
    assert report.failed(NOT_INDEXED) == ["q3"]      # the document never reached the index
    assert report.failed(RANKING) == ["q4"]          # ranked sixth with k = 5
    print("recall@5:", report.recall_at_k, "· MRR:", report.mrr,
          "· failures:", len(report.rows) - 1)
