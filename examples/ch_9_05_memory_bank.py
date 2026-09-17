from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

DAY = 86_400.0
NEVER_REMEMBER = frozenset({"suspicious_activity", "special_category", "credentials", "document_number"})


class Source(StrEnum):
    SYSTEM_OF_RECORD = "system_of_record"
    OFFICER = "officer"
    CUSTOMER = "customer"


@dataclass(frozen=True)
class Record:
    subject: str
    topic: str
    text: str
    source: Source
    source_ref: str                     # запись в источнике или событие журнала
    created_at: float
    ttl_s: float

    @property
    def is_claim(self) -> bool:
        return self.source is Source.CUSTOMER          # слова клиента: утверждение, не факт


class ForbiddenTopic(Exception):
    """Эта тема не запоминается ни при каком согласии."""


@dataclass
class MemoryBank:
    now: Callable[[], float]
    consent: dict[str, bool] = field(default_factory=dict)
    rows: list[Record] = field(default_factory=list)

    def remember(self, record: Record) -> bool:
        if record.topic in NEVER_REMEMBER:
            raise ForbiddenTopic(record.topic)
        if not self.consent.get(record.subject, False):
            return False
        self.rows.append(record)
        return True

    def recall(self, subject: str) -> list[Record]:
        t = self.now()
        return [r for r in self.rows if r.subject == subject and t - r.created_at < r.ttl_s]

    def facts_for_action(self, subject: str) -> list[Record]:
        return [r for r in self.recall(subject) if not r.is_claim]

    def render(self, subject: str) -> list[str]:
        return [f"клиент утверждает ({r.source_ref}): {r.text}" if r.is_claim
                else f"факт ({r.source.value}, {r.source_ref}): {r.text}"
                for r in self.recall(subject)]

    def withdraw_consent(self, subject: str) -> int:
        self.consent[subject] = False
        before = len(self.rows)
        self.rows = [r for r in self.rows if r.subject != subject]
        return before - len(self.rows)


if __name__ == "__main__":
    clock = {"t": 0.0}
    bank = MemoryBank(now=lambda: clock["t"])
    moved = Record("C-104233", "address", "переехал в Осло в марте", Source.CUSTOMER,
                   "event:run-1/14", created_at=0.0, ttl_s=7 * DAY)
    assert not bank.remember(moved) and bank.rows == []           # согласия нет: не храним

    bank.consent["C-104233"] = True
    decision = Record("C-104233", "risk_decision", "повышение риска отклонено", Source.OFFICER,
                      "approval:run-1/officer-12", created_at=0.0, ttl_s=365 * DAY)
    assert bank.remember(moved) and bank.remember(decision)
    clock["t"] = 2 * DAY
    assert [r.topic for r in bank.facts_for_action("C-104233")] == ["risk_decision"]
    assert bank.render("C-104233")[0].startswith("клиент утверждает")
    clock["t"] = 10 * DAY
    assert [r.topic for r in bank.recall("C-104233")] == ["risk_decision"]   # утверждение истекло
    try:
        bank.remember(Record("C-104233", "suspicious_activity", "…", Source.OFFICER, "sar:17", 0.0, DAY))
        raise AssertionError("подозрение не запоминается")
    except ForbiddenTopic:
        pass
    assert bank.withdraw_consent("C-104233") == 2 and bank.recall("C-104233") == []
    print("память различает факты и утверждения, истекает и уважает согласие")
