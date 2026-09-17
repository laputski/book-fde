from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum

PROBES_MIN = 0.95           # доля золотых проб с верным отпечатком
RECALL_MIN = 0.85           # полнота поиска на контрольных вопросах
SEARCH_ERRORS_MAX = 0.05    # доля ошибок сервиса поиска


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
    replay_clean: bool          # трассы инцидента больше не дают ошибки


@dataclass(frozen=True)
class AuditEvent:
    at: float
    capability: str
    before: Rung
    after: Rung
    actor: str
    reason: str


def entry_rung(s: Signals) -> Rung:
    """Критерии входа: самая высокая ступень, которую допускают сигналы."""
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
    exit_runs: int = 3                              # зелёных прогонов подряд для подъёма
    rung: Rung = Rung.FULL_AGENT
    forced: Rung = Rung.FULL_AGENT                  # наивысшая ступень, разрешённая человеком
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
                                     actor, "выключатель снят, подъём только по сигналам"))
        self.forced = Rung.FULL_AGENT

    def evidence(self, s: Signals) -> bool:
        """Доказательство подъёма: к полному агенту ещё и чистые трассы инцидента."""
        return s.replay_clean or self.rung > Rung.RETRIEVAL_ONLY

    def observe(self, s: Signals) -> Rung:
        floor = max(entry_rung(s), self.forced)
        if floor > self.rung:
            self._move(floor, "auto", f"вход: сигналы требуют ступень {floor.value}")
        elif floor < self.rung and self.evidence(s):
            self.green += 1
            if self.green >= self.exit_runs:        # выход: по одной ступени за раз
                self._move(Rung(self.rung - 1), "auto", f"выход: {self.exit_runs} зелёных прогона")
        else:
            self.green = 0
        return self.rung


if __name__ == "__main__":
    clock = {"t": 9 * 3600 + 22 * 60}               # 09:22 в секундах от полуночи
    dosing = CapabilitySwitch("dosing_answers", now=lambda: clock["t"])
    summaries = CapabilitySwitch("protocol_summaries", now=lambda: clock["t"])
    dosing.kill(Rung.RETRIEVAL_ONLY, "дежурный инженер", "цитаты редакции 7 вместо 8")
    assert dosing.rung is Rung.RETRIEVAL_ONLY and summaries.rung is Rung.FULL_AGENT

    healthy = Signals(probe_pass_rate=1.0, retrieval_recall=0.93, search_error_rate=0.0,
                      replay_clean=True)
    for _ in range(5):
        dosing.observe(healthy)
    assert dosing.rung is Rung.RETRIEVAL_ONLY       # выключатель держит, пока его не сняли

    clock["t"] += 60 * 60
    dosing.release("дежурный инженер")
    dosing.observe(healthy)
    dosing.observe(Signals(1.0, 0.93, 0.0, replay_clean=False))     # без доказательства: сброс
    dosing.observe(healthy)
    dosing.observe(healthy)
    assert dosing.rung is Rung.RETRIEVAL_ONLY
    assert dosing.observe(healthy) is Rung.FULL_AGENT

    assert dosing.observe(Signals(1.0, 0.93, 0.2, replay_clean=True)) is Rung.STATIC_NOTICE
    assert [e.after for e in dosing.audit] == [Rung.RETRIEVAL_ONLY, Rung.RETRIEVAL_ONLY,
                                               Rung.FULL_AGENT, Rung.STATIC_NOTICE]
    assert dosing.audit[0].at == 9 * 3600 + 22 * 60 and dosing.audit[0].actor == "дежурный инженер"
    print("вниз по критерию сразу, вверх по одной ступени и только с доказательством")
