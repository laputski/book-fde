from __future__ import annotations

import operator
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

OPS: dict[str, Callable[[float, float], bool]] = {">=": operator.ge, "<=": operator.le}


@dataclass(frozen=True)
class Criterion:
    clause: str                   # пункт SOW: "4.1"
    metric: str                   # имя метрики в отчёте измерений
    op: str
    threshold: float
    window_days: int = 0          # сколько дней подряд метрика должна быть измерена

    def __post_init__(self) -> None:
        if self.op not in OPS or not re.fullmatch(r"\d+\.\d+", self.clause):
            raise ValueError(f"критерий {self.clause}/{self.metric} нельзя исполнить")

    def failure(self, measured: Mapping[str, tuple[float, int]]) -> str | None:
        if self.metric not in measured:
            return f"SOW {self.clause}: {self.metric} не измерена"
        value, days = measured[self.metric]
        if days < self.window_days:
            return f"SOW {self.clause}: {self.metric} измерена {days} дн. из {self.window_days}"
        if not OPS[self.op](value, self.threshold):
            return f"SOW {self.clause}: {self.metric} = {value}, требуется {self.op} {self.threshold}"
        return None


def acceptance_report(criteria: list[Criterion], payments: Mapping[str, int],
                      measured: Mapping[str, tuple[float, int]]) -> dict[str, list[str]]:
    """Для каждого платёжного пункта SOW: пустой список означает, что счёт можно выставить."""
    untested = sorted(set(payments) - {c.clause for c in criteria})
    if untested:
        raise ValueError(f"платёж без исполнимого теста: SOW {untested}")
    report: dict[str, list[str]] = {clause: [] for clause in payments}
    for c in criteria:
        if (problem := c.failure(measured)) and c.clause in report:
            report[c.clause].append(problem)
    return report


if __name__ == "__main__":
    payments = {"2.1": 15, "3.2": 30, "4.1": 35, "5.3": 20}          # доля гонорара, %
    criteria = [
        Criterion("2.1", "baseline_orders", ">=", 200),
        Criterion("3.2", "groundedness", ">=", 0.90),
        Criterion("3.2", "approval_bound_to_args", ">=", 1.0),
        Criterion("4.1", "p95_first_token_s", "<=", 2.0, window_days=14),
        Criterion("4.1", "availability", ">=", 0.995, window_days=14),
        Criterion("5.3", "releases_without_fde", ">=", 2),
        Criterion("5.3", "runbook_drills_passed", ">=", 1),
    ]
    measured = {"baseline_orders": (212, 10), "groundedness": (0.93, 1),
                "approval_bound_to_args": (1.0, 1), "p95_first_token_s": (1.7, 14),
                "availability": (0.993, 14)}
    report = acceptance_report(criteria, payments, measured)
    assert [c for c, failed in report.items() if not failed] == ["2.1", "3.2"]
    assert report["4.1"] == ["SOW 4.1: availability = 0.993, требуется >= 0.995"]
    assert report["5.3"] == ["SOW 5.3: releases_without_fde не измерена",
                             "SOW 5.3: runbook_drills_passed не измерена"]
    for bad in (lambda: Criterion("4.1", "quality", "satisfactory", 0.0),
                lambda: acceptance_report(criteria[:1], payments, measured)):
        try:
            bad()
            raise AssertionError("неисполнимый критерий или платёж без теста принят")
        except ValueError:
            pass
    print("к оплате: SOW 2.1, 3.2; не приняты:", sorted(c for c, f in report.items() if f))
