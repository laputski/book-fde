from __future__ import annotations

import operator
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

OPS: dict[str, Callable[[float, float], bool]] = {">=": operator.ge, "<=": operator.le}


@dataclass(frozen=True)
class Criterion:
    clause: str                   # SOW clause: "4.1"
    metric: str                   # metric name in the measurement report
    op: str
    threshold: float
    window_days: int = 0          # consecutive days the metric must be measured

    def __post_init__(self) -> None:
        if self.op not in OPS or not re.fullmatch(r"\d+\.\d+", self.clause):
            raise ValueError(f"criterion {self.clause}/{self.metric} cannot be executed")

    def failure(self, measured: Mapping[str, tuple[float, int]]) -> str | None:
        if self.metric not in measured:
            return f"SOW {self.clause}: {self.metric} not measured"
        value, days = measured[self.metric]
        if days < self.window_days:
            return f"SOW {self.clause}: {self.metric} measured {days} of {self.window_days} days"
        if not OPS[self.op](value, self.threshold):
            return f"SOW {self.clause}: {self.metric} = {value}, required {self.op} {self.threshold}"
        return None


def acceptance_report(criteria: list[Criterion], payments: Mapping[str, int],
                      measured: Mapping[str, tuple[float, int]]) -> dict[str, list[str]]:
    """For every payment clause of the SOW: an empty list means the invoice may be issued."""
    untested = sorted(set(payments) - {c.clause for c in criteria})
    if untested:
        raise ValueError(f"payment without an executable test: SOW {untested}")
    report: dict[str, list[str]] = {clause: [] for clause in payments}
    for c in criteria:
        if (problem := c.failure(measured)) and c.clause in report:
            report[c.clause].append(problem)
    return report


if __name__ == "__main__":
    payments = {"2.1": 15, "3.2": 30, "4.1": 35, "5.3": 20}          # share of the fee, %
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
    assert report["4.1"] == ["SOW 4.1: availability = 0.993, required >= 0.995"]
    assert report["5.3"] == ["SOW 5.3: releases_without_fde not measured",
                             "SOW 5.3: runbook_drills_passed not measured"]
    for bad in (lambda: Criterion("4.1", "quality", "satisfactory", 0.0),
                lambda: acceptance_report(criteria[:1], payments, measured)):
        try:
            bad()
            raise AssertionError("an unexecutable criterion or an untested payment was accepted")
        except ValueError:
            pass
    print("payable: SOW 2.1, 3.2; not accepted:", sorted(c for c, f in report.items() if f))
