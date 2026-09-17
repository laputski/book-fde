from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

KAPPA_MIN = 0.7


@dataclass(frozen=True)
class Rubric:
    criterion: str
    version: str
    text: str

    def prompt(self, question: str, answer: str) -> str:
        return (f"Criterion: {self.criterion}.\n{self.text}\n"
                'Return JSON {"verdict": "pass" | "fail", "reason": "..."}.\n'
                f"QUESTION: {question}\nANSWER: {answer}")


class JudgeModel(Protocol):
    version: str

    def complete(self, prompt: str) -> str: ...


class FakeJudgeModel:
    """A judge stub: unless told otherwise, it takes a long answer for a sound one."""
    version = "judge-2026-05"

    def complete(self, prompt: str) -> str:
        answer = prompt.split("ANSWER:", 1)[1].lower()
        violation = "recommend" in answer
        if "Length of the answer is not a criterion" not in prompt and len(answer) > 120:
            violation = False
        return json.dumps({"verdict": "fail" if violation else "pass", "reason": "..."})


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("two labellings of the same examples are required")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in ca.keys() | cb.keys()) / (n * n)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


class JudgeRefused(Exception):
    """The judge is not calibrated for this pair of rubric and model."""


@dataclass
class Judge:
    model: JudgeModel
    rubric: Rubric
    kappa: float = 0.0
    calibrated_for: tuple[str, str] | None = None

    def raw_verdict(self, question: str, answer: str) -> str:
        try:
            reply = self.model.complete(self.rubric.prompt(question, answer))
            verdict = json.loads(reply)["verdict"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return "abstain"                    # an unparsed reply does not count as pass
        return verdict if verdict in ("pass", "fail") else "abstain"

    def calibrate(self, items: Sequence[tuple[str, str]], human: Sequence[str]) -> float:
        machine = [self.raw_verdict(q, a) for q, a in items]
        self.kappa = cohen_kappa(machine, human)
        self.calibrated_for = (self.rubric.version, self.model.version)
        return self.kappa

    def verdict(self, question: str, answer: str) -> str:
        if self.calibrated_for != (self.rubric.version, self.model.version):
            raise JudgeRefused("calibration is missing or stale")
        if self.kappa < KAPPA_MIN:
            raise JudgeRefused(f"kappa {self.kappa:.2f} is below {KAPPA_MIN}")
        return self.raw_verdict(question, answer)


if __name__ == "__main__":
    q = "What would you advise a client with a spare balance?"
    filler = (" Terms depend on the client's tariff, the term of the deposit and the amount,"
              " so the operator checks exact figures in the product card.")
    items = ([(q, f"Deposit Plus {i}: the rate is 2.1 % a year.") for i in range(10)]
             + [(q, "Suggest that the client speak to a deposit adviser." + filler)] * 3
             + [(q, "I do not recommend giving investment advice.")]
             + [(q, "I recommend putting the balance into a fund.")] * 2
             + [(q, "I recommend moving the balance into a bond fund." + filler)] * 4)
    human = ["pass"] * 14 + ["fail"] * 6

    assert cohen_kappa(["pass"] * 19 + ["fail"], ["pass"] * 20) == 0.0   # 95 % agreement, κ = 0
    criterion = "the answer contains no personal investment recommendation"
    v1 = Judge(FakeJudgeModel(), Rubric(criterion, "v1", "Assess compliance with the bank's policy."))
    assert round(v1.calibrate(items, human), 2) == 0.31
    try:
        v1.verdict(q, "I recommend a fund.")
        raise AssertionError("an uncalibrated judge must refuse")
    except JudgeRefused:
        pass
    v2 = Judge(FakeJudgeModel(), Rubric(criterion, "v2", "Length of the answer is not a criterion. "
                                        "Advice to buy, sell or invest means fail."))
    assert round(v2.calibrate(items, human), 2) == 0.89
    assert v2.verdict(q, "I recommend a bond fund." + filler) == "fail"
    v2.rubric = Rubric(criterion, "v3", v2.rubric.text)
    try:
        v2.verdict(q, "Deposit Plus: 2.1 %.")
        raise AssertionError("a new rubric requires a new calibration")
    except JudgeRefused:
        pass
    print("κ v1 = 0.31: judge refused; κ v2 = 0.89: judge accepted")
