from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum

PROBES_MIN = 0.95           # share of golden probes with the expected fingerprint
RECALL_MIN = 0.85           # retrieval recall on the control questions
SEARCH_ERRORS_MAX = 0.05    # error rate of the search service


class Rung(IntEnum):
    FULL_AGENT = 0
    RETRIEVAL_ONLY = 1
    SEARCH_RESULTS = 2
    STATIC_NOTICE = 3


@dataclass(frozen=True)
class Signals:
    probe_pass_rate: float
    retrieval_recall: float
    search_error_rate: float
    replay_clean: bool          # the incident's traces no longer produce the error


@dataclass(frozen=True)
class AuditEvent:
    at: float
    capability: str
    before: Rung
    after: Rung
    actor: str
    reason: str


def entry_rung(s: Signals) -> Rung:
    """Entry criteria: the highest rung the signals allow."""
    if s.search_error_rate > SEARCH_ERRORS_MAX:
        return Rung.STATIC_NOTICE
    if s.retrieval_recall < RECALL_MIN:
        return Rung.SEARCH_RESULTS
    if s.probe_pass_rate < PROBES_MIN:
        return Rung.RETRIEVAL_ONLY
    return Rung.FULL_AGENT


@dataclass
class CapabilitySwitch:
    capability: str
    now: Callable[[], float]
    exit_runs: int = 3                              # consecutive green runs to climb a rung
    rung: Rung = Rung.FULL_AGENT
    forced: Rung = Rung.FULL_AGENT                  # the highest rung a human allows
    green: int = 0
    audit: list[AuditEvent] = field(default_factory=list)

    def _move(self, to: Rung, actor: str, reason: str) -> None:
        self.audit.append(AuditEvent(self.now(), self.capability, self.rung, to, actor, reason))
        self.rung, self.green = to, 0

    def kill(self, to: Rung, actor: str, reason: str) -> None:
        self.forced = to
        if to > self.rung:
            self._move(to, actor, reason)

    def release(self, actor: str) -> None:
        self.audit.append(AuditEvent(self.now(), self.capability, self.rung, self.rung,
                                     actor, "switch released; climbing only on signals"))
        self.forced = Rung.FULL_AGENT

    def evidence(self, s: Signals) -> bool:
        """Exit evidence: the climb to the full agent also needs clean incident traces."""
        return s.replay_clean or self.rung > Rung.RETRIEVAL_ONLY

    def observe(self, s: Signals) -> Rung:
        floor = max(entry_rung(s), self.forced)
        if floor > self.rung:
            self._move(floor, "auto", f"entry: the signals require rung {floor.value}")
        elif floor < self.rung and self.evidence(s):
            self.green += 1
            if self.green >= self.exit_runs:        # exit: one rung at a time
                self._move(Rung(self.rung - 1), "auto", f"exit: {self.exit_runs} green runs")
        else:
            self.green = 0
        return self.rung


if __name__ == "__main__":
    clock = {"t": 9 * 3600 + 22 * 60}               # 09:22 in seconds since midnight
    dosing = CapabilitySwitch("dosing_answers", now=lambda: clock["t"])
    summaries = CapabilitySwitch("protocol_summaries", now=lambda: clock["t"])
    dosing.kill(Rung.RETRIEVAL_ONLY, "on-call engineer", "edition 7 cited instead of 8")
    assert dosing.rung is Rung.RETRIEVAL_ONLY and summaries.rung is Rung.FULL_AGENT

    healthy = Signals(probe_pass_rate=1.0, retrieval_recall=0.93, search_error_rate=0.0,
                      replay_clean=True)
    for _ in range(5):
        dosing.observe(healthy)
    assert dosing.rung is Rung.RETRIEVAL_ONLY       # the switch holds until it is released

    clock["t"] += 60 * 60
    dosing.release("on-call engineer")
    dosing.observe(healthy)
    dosing.observe(Signals(1.0, 0.93, 0.0, replay_clean=False))     # no evidence: the count resets
    dosing.observe(healthy)
    dosing.observe(healthy)
    assert dosing.rung is Rung.RETRIEVAL_ONLY
    assert dosing.observe(healthy) is Rung.FULL_AGENT

    assert dosing.observe(Signals(1.0, 0.93, 0.2, replay_clean=True)) is Rung.STATIC_NOTICE
    assert [e.after for e in dosing.audit] == [Rung.RETRIEVAL_ONLY, Rung.RETRIEVAL_ONLY,
                                               Rung.FULL_AGENT, Rung.STATIC_NOTICE]
    assert dosing.audit[0].at == 9 * 3600 + 22 * 60 and dosing.audit[0].actor == "on-call engineer"
    print("down at once on a criterion, up one rung at a time and only on evidence")
