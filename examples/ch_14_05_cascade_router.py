from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

LABELS = ("scratch", "dent", "crack", "porosity")


@dataclass(frozen=True)
class Case:
    case_id: str
    difficulty: float          # известна фейковым моделям, но не маршрутизатору
    truth: str


@dataclass(frozen=True)
class Answer:
    label: str
    confidence: float


@dataclass(frozen=True)
class Tier:
    name: str
    usd_per_call: float
    answer: Callable[[Case], Answer]


def other(label: str) -> str:
    return LABELS[(LABELS.index(label) + 1) % len(LABELS)]


def small(case: Case) -> Answer:
    if case.difficulty < 0.70:
        return Answer(case.truth, 0.978 - case.difficulty / 4)
    if case.difficulty < 0.75:
        return Answer(other(case.truth), 0.90)       # уверенная ошибка
    return Answer(other(case.truth), 0.60)


def large(case: Case) -> Answer:
    return Answer(case.truth if case.difficulty < 0.95 else other(case.truth), 0.90)


@dataclass(frozen=True)
class Report:
    escalation_rate: float     # доля кейсов, дошедших до второй ступени
    usd_per_case: float
    accuracy: float
    accepted_errors: float     # ошибки первой ступени, пропущенные воротами


def evaluate(first: Tier, second: Tier, threshold: float, cases: list[Case]) -> Report:
    escalated = correct = missed = 0
    usd = 0.0
    for case in cases:
        answer = first.answer(case)
        usd += first.usd_per_call
        if answer.confidence < threshold:
            escalated += 1
            usd += second.usd_per_call
            answer = second.answer(case)
        elif answer.label != case.truth:
            missed += 1
        correct += answer.label == case.truth
    n = len(cases)
    return Report(escalated / n, usd / n, correct / n, missed / n)


if __name__ == "__main__":
    cases = [Case(f"c{i}", i / 100, LABELS[i % 4]) for i in range(100)]
    cheap, strong = Tier("small", 0.0004, small), Tier("large", 0.0040, large)

    only_large = evaluate(strong, strong, 0.0, cases)
    at_80 = evaluate(cheap, strong, 0.80, cases)
    at_92 = evaluate(cheap, strong, 0.92, cases)

    assert at_80.escalation_rate == 0.25
    assert math.isclose(at_80.usd_per_case, 0.0004 + 0.25 * 0.0040)   # смешанная цена
    assert at_80.usd_per_case < 0.4 * only_large.usd_per_case
    assert (at_80.accuracy, at_80.accepted_errors) == (0.90, 0.05)
    assert (at_92.escalation_rate, at_92.accuracy) == (0.76, only_large.accuracy)
    assert at_92.usd_per_case > 2 * at_80.usd_per_case
    print(f"порог 0.80: эскалация {at_80.escalation_rate:.0%}, "
          f"${at_80.usd_per_case:.4f} за кейс, точность {at_80.accuracy:.0%}")
