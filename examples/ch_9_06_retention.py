from __future__ import annotations

from dataclasses import dataclass, field

DAY = 86_400.0
REDACTED = "[стёрто]"


@dataclass
class Record:
    run_id: str
    subject: str
    kind: str                           # "event": аудит; "checkpoint": операционный класс
    skeleton: dict[str, str]            # что, кто, когда, ссылки на системы записи
    content: dict[str, str]             # копии персональных данных
    run_ended_at: float | None = None


@dataclass
class RetentionEnforcer:
    records: list[Record]
    legal_hold: set[str] = field(default_factory=set)
    operational_ttl_s: float = 30 * DAY
    audit: list[dict[str, str]] = field(default_factory=list)

    def erase(self, subject: str, request_id: str, now: float) -> str:
        if subject in self.legal_hold:
            self.audit.append({"request": request_id, "subject": subject, "outcome": "deferred"})
            return "deferred"
        erased = 0
        for r in self.records:
            if r.subject == subject and any(v != REDACTED for v in r.content.values()):
                r.content = dict.fromkeys(r.content, REDACTED)
                r.skeleton = {**r.skeleton, "erased_by": request_id}
                erased += 1
        self.audit.append({"request": request_id, "subject": subject, "outcome": "erased",
                           "records": str(erased), "at": str(now)})
        return "erased"

    def purge_operational(self, now: float) -> int:
        def expired(r: Record) -> bool:
            return (r.kind == "checkpoint" and r.run_ended_at is not None
                    and now - r.run_ended_at > self.operational_ttl_s)
        before = len(self.records)
        self.records = [r for r in self.records if not expired(r)]
        return before - len(self.records)


if __name__ == "__main__":
    records = [
        Record("run-1", "C-104233", "event",
               {"tool": "search_documents", "doc_ref": "DMS-88121/v3", "at": "2026-03-02T10:14"},
               {"result": "паспорт NB-000123, адрес Storgatan 5"}),
        Record("run-1", "C-104233", "event",
               {"tool": "set_risk_rating", "decision": "high", "approved_by": "officer-12"},
               {"reason_text": "совпадение с перечнем PEP: родственник"}),
        Record("run-1", "C-104233", "checkpoint", {"next_step": "5"},
               {"state": "клиент сообщил о переезде в Осло"}, run_ended_at=2 * DAY),
        Record("run-2", "C-200871", "event", {"tool": "screen_sanctions"},
               {"result": "возможное совпадение"}),
    ]
    enforcer = RetentionEnforcer(records, legal_hold={"C-200871"})
    assert enforcer.erase("C-104233", "ER-311", now=3 * DAY) == "erased"
    erased = [r for r in enforcer.records if r.subject == "C-104233"]
    assert all(v == REDACTED for r in erased for v in r.content.values())
    assert erased[1].skeleton["approved_by"] == "officer-12"         # скелет аудита цел
    assert enforcer.erase("C-200871", "ER-312", now=3 * DAY) == "deferred"
    assert enforcer.records[3].content["result"] == "возможное совпадение"
    assert enforcer.purge_operational(now=40 * DAY) == 1              # истёк только checkpoint
    assert [r.kind for r in enforcer.records] == ["event", "event", "event"]
    assert [a["outcome"] for a in enforcer.audit] == ["erased", "deferred"]
    print("персональные данные стёрты, скелет аудита сохранён, удержание учтено")
