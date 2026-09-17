from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

GENESIS = "0" * 64
type Verdict = Literal["allowed", "denied", "needs_approval"]


def safe(value: str, limit: int = 160) -> str:
    """Недоверенная строка: управляющие символы экранированы, длина ограничена."""
    shown = "".join(ch if ch.isprintable() else f"\\u{ord(ch):04x}" for ch in value)
    return shown if len(shown) <= limit else shown[:limit] + "…"


def canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    seq: int
    at: str
    actor: str                  # сервисная учётная запись агента
    on_behalf_of: str           # псевдоним жителя, а не имя
    action: str                 # имя инструмента в том виде, в каком его предложила модель
    decision: Verdict
    reason: str
    args_mac: str               # ключевой хэш аргументов вместо самих аргументов
    detector_score: float
    policy_version: str
    prev_hash: str
    chain_hash: str = ""


def link_hash(event: AuditEvent) -> str:
    return hashlib.sha256(canonical(event.model_dump(exclude={"chain_hash"}))).hexdigest()


@dataclass
class AuditLog:
    key: bytes                  # ключ из KMS; у тех, кто читает журнал, его нет
    events: list[AuditEvent] = field(default_factory=list)

    def record(self, at: str, actor: str, on_behalf_of: str, action: str, decision: Verdict,
               reason: str, args: dict[str, str], score: float, policy_version: str) -> AuditEvent:
        draft = AuditEvent(
            seq=len(self.events), at=at, actor=actor, on_behalf_of=on_behalf_of,
            action=safe(action), decision=decision, reason=safe(reason),
            args_mac=hmac.new(self.key, canonical(args), hashlib.sha256).hexdigest(),
            detector_score=score, policy_version=policy_version,
            prev_hash=self.events[-1].chain_hash if self.events else GENESIS)
        event = draft.model_copy(update={"chain_hash": link_hash(draft)})
        self.events.append(event)
        return event

    def verify(self) -> int | None:
        """Номер первого нарушенного звена или None, если цепочка цела."""
        prev = GENESIS
        for n, event in enumerate(self.events):
            if event.seq != n or event.prev_hash != prev or event.chain_hash != link_hash(event):
                return n
            prev = event.chain_hash
        return None


if __name__ == "__main__":
    log = AuditLog(key=b"key-from-kms")
    log.record("2026-09-14T10:02:11Z", "sa-citizen-assistant", "cit-7f3a", "search_documents",
               "allowed", "разрешено", {"query": "жилищное пособие"}, 0.0, "policy-12")
    hostile = "export_case\n2026-09-14T10:02:12Z allowed \x1b[32mOK\x1b[0m"
    denied = log.record("2026-09-14T10:02:12Z", "sa-citizen-assistant", "cit-7f3a", hostile, "denied",
                        "инструмент вне allow-list", {"case_id": "C-1002", "to": "drop@attacker.example"},
                        0.91, "policy-12")
    line = denied.model_dump_json()
    decoded = json.loads(line)["action"]
    assert "\n" not in decoded and "\x1b" not in decoded and "drop@attacker" not in line
    assert log.verify() is None
    log.events[1] = denied.model_copy(update={"decision": "allowed"})
    assert log.verify() == 1                                # подмена решения видна
    log.events[1] = denied
    del log.events[0]
    assert log.verify() == 0                                # удаление звена тоже видно
    print("подмена и удаление звена обнаружены, аргументы в журнале не раскрыты")
