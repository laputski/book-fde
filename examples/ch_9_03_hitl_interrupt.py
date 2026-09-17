from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

DAY = 86_400.0
SIGNING_KEY = b"demo-only"              # в production ключ подписи хранится в KMS


@dataclass(frozen=True)
class Action:
    tool: str
    args: dict[str, Any]

    def digest(self) -> str:
        raw = json.dumps({"tool": self.tool, "args": self.args}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Interrupt:
    run_id: str
    action: Action
    preconditions: dict[str, Any]       # то, на чём основано предложение
    expires_at: float


@dataclass(frozen=True)
class ApprovalToken:
    run_id: str
    action_digest: str
    approver: str
    expires_at: float
    signature: str


def sign(run_id: str, digest: str, approver: str, expires_at: float) -> str:
    message = f"{run_id}|{digest}|{approver}|{expires_at}".encode()
    return hmac.new(SIGNING_KEY, message, hashlib.sha256).hexdigest()


def approve(interrupt: Interrupt, approver: str) -> ApprovalToken:
    digest = interrupt.action.digest()
    return ApprovalToken(interrupt.run_id, digest, approver, interrupt.expires_at,
                         sign(interrupt.run_id, digest, approver, interrupt.expires_at))


class ResumeRefused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def resume(interrupt: Interrupt, token: ApprovalToken, action: Action, now: float,
           read_preconditions: Callable[[], dict[str, Any]]) -> Action:
    """Разрешает действие, только если одобрено именно оно, в срок и на тех же основаниях."""
    expected = sign(token.run_id, token.action_digest, token.approver, token.expires_at)
    if not hmac.compare_digest(expected, token.signature):
        raise ResumeRefused("bad_signature")
    if token.run_id != interrupt.run_id or token.action_digest != action.digest():
        raise ResumeRefused("action_changed")
    if now >= token.expires_at:
        raise ResumeRefused("expired")
    if read_preconditions() != interrupt.preconditions:
        raise ResumeRefused("preconditions_changed")
    return action


if __name__ == "__main__":
    bank = {"risk_rating": "medium", "account": "active", "kyc_docs_version": 3,
            "screening_date": "2026-03-02"}
    action = Action("set_risk_rating", {"customer": "C-104233", "rating": "high", "reason": "pep_match"})
    interrupt = Interrupt("run-7", action, dict(bank), expires_at=7 * DAY)
    token = approve(interrupt, approver="officer-12")

    def outcome(act: Action, now: float, tok: ApprovalToken = token) -> str:
        try:
            resume(interrupt, tok, act, now, lambda: dict(bank))
        except ResumeRefused as refused:
            return refused.code
        return "allowed"

    assert outcome(action, now=2 * DAY) == "allowed"
    other = Action("restrict_account", {"customer": "C-104233"})
    assert outcome(other, now=2 * DAY) == "action_changed"         # модель сменила действие
    assert outcome(action, now=8 * DAY) == "expired"
    assert outcome(action, 2 * DAY, replace(token, approver="agent")) == "bad_signature"
    bank["kyc_docs_version"] = 4                                    # клиент загрузил документ
    assert outcome(action, now=5 * DAY) == "preconditions_changed"
    print("одобрение привязано к действию, истекает и не переживает смену оснований")
