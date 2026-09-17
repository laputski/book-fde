from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Decision:
    action_class: str
    outcome: Literal["accepted", "modified", "rejected"]
    shown_at: float
    decided_at: float
    reverted_later: bool = False                # действие позже отменил фармацевт или коллега


@dataclass(frozen=True)
class ClassStats:
    action_class: str
    n: int
    acceptance: float
    override: float
    override_upper: float                       # верхняя граница 95 % по Уилсону
    median_decision_s: float
    reverted: int


def wilson_upper(k: int, n: int, z: float = 1.96) -> float:
    p = k / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre + margin) / (1 + z * z / n)


def by_class(decisions: list[Decision]) -> dict[str, ClassStats]:
    groups: dict[str, list[Decision]] = defaultdict(list)
    for d in decisions:
        groups[d.action_class].append(d)
    out: dict[str, ClassStats] = {}
    for name, ds in sorted(groups.items()):
        accepted = sum(d.outcome == "accepted" for d in ds)
        overridden = len(ds) - accepted
        out[name] = ClassStats(name, len(ds), accepted / len(ds), overridden / len(ds),
                               wilson_upper(overridden, len(ds)),
                               statistics.median(d.decided_at - d.shown_at for d in ds),
                               sum(d.reverted_later for d in ds))
    return out


@dataclass(frozen=True)
class WideningRule:
    min_decisions: int = 300
    max_override_upper: float = 0.02
    min_median_s: float = 4.0                   # быстрее: решения не читаются
    never: frozenset[str] = frozenset({"order.medication"})

    def propose(self, s: ClassStats) -> tuple[bool, str]:
        if s.action_class in self.never:
            return False, "класс исключён из предавторизации политикой"
        if s.n < self.min_decisions:
            return False, f"мало решений: {s.n}"
        if s.median_decision_s < self.min_median_s:
            return False, "решения слишком быстрые: признак усталости, а не доверия"
        if s.override_upper > self.max_override_upper:
            return False, f"верхняя граница override {s.override_upper:.3f}"
        if s.reverted:
            return False, "есть действия, отменённые позже"
        return True, "вынести предавторизацию класса на решение клинического комитета"


def simulate(action_class: str, n: int, overrides: int, seconds: float) -> list[Decision]:
    return [Decision(action_class, "modified" if i < overrides else "accepted", 60.0 * i, 60.0 * i + seconds)
            for i in range(n)]


if __name__ == "__main__":
    log = (simulate("order.lab", 400, 1, 9.0) + simulate("order.nursing", 500, 0, 1.5)
           + simulate("order.medication", 600, 2, 12.0) + simulate("order.imaging", 120, 0, 10.0)
           + simulate("order.referral", 350, 12, 15.0))
    stats = by_class(log)
    rule = WideningRule()
    assert round(stats["order.referral"].override, 3) == 0.034
    assert stats["order.lab"].acceptance == 399 / 400 and stats["order.lab"].median_decision_s == 9.0
    verdicts = {name: rule.propose(s)[0] for name, s in stats.items()}
    assert verdicts == {"order.imaging": False, "order.lab": True, "order.nursing": False,
                        "order.medication": False, "order.referral": False}
    assert "усталости" in rule.propose(stats["order.nursing"])[1]
    print("предавторизация предлагается только для order.lab: остальные классы не прошли пороги")
