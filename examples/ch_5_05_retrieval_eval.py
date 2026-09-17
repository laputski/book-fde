from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

NOT_INDEXED = "не проиндексировано"
HIDDEN = "скрыто фильтром"
CANDIDATES = "не попало в кандидаты"
RANKING = "ниже среза k"
FOUND = "найдено"


@dataclass(frozen=True)
class Question:
    qid: str
    text: str
    gold: frozenset[str]           # чанки, которые обязаны попасть в ответ


@dataclass(frozen=True)
class Diagnosis:
    qid: str
    rank: int | None
    stage: str                     # где именно потерялся правильный ответ


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
        Question("q1", "порог лактата при сепсисе", frozenset({"gl-17#1"})),
        Question("q2", "оценка суицидального риска", frozenset({"gl-44#1"})),
        Question("q3", "срок хранения снимков", frozenset({"gl-52#3"})),
        Question("q4", "когда вводят антибиотик", frozenset({"gl-17#4"})),
    ]
    runs: dict[str, list[str]] = {
        "q1": ["gl-31#1", "gl-17#1", "gl-90#1"],
        "q2": ["gl-31#1", "gl-90#1"],
        "q3": ["gl-31#1"],
        "q4": ["gl-31#1", "gl-90#1", "gl-52#1", "gl-52#2", "gl-44#1", "gl-17#4"],
    }
    indexed = frozenset({"gl-17#1", "gl-17#4", "gl-31#1", "gl-44#1", "gl-90#1",
                         "gl-52#1", "gl-52#2"})
    visible = indexed - {"gl-44#1"}          # психиатрия закрыта для этого principal
    report = evaluate(questions, lambda q: runs[q.qid], indexed, visible, k=5)

    assert report.recall_at_k == 0.25 and report.mrr == 0.125
    assert report.failed(HIDDEN) == ["q2"]           # индекс есть, прав нет
    assert report.failed(NOT_INDEXED) == ["q3"]      # документа нет в индексе вовсе
    assert report.failed(RANKING) == ["q4"]          # нашлось шестым при k = 5
    print("recall@5:", report.recall_at_k, "· MRR:", report.mrr,
          "· отказов:", len(report.rows) - 1)
