from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field, replace
from typing import Literal

SIGNING_KEY = b"demo-only"                      # в production ключ подписи хранится в KMS
type Scope = Literal["action", "class", "plan"]


@dataclass(frozen=True)
class ProposedAction:
    action_id: str
    action_class: str                           # "order.medication", "order.lab", ...
    tool: str
    args: dict[str, str] = field(hash=False)

    def digest(self) -> str:
        raw = json.dumps({"tool": self.tool, "args": self.args}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    scope: Scope
    actions: tuple[ProposedAction, ...]
    expires_at: float


@dataclass(frozen=True)
class Grant:
    """Токен одобрения: подпись над хешами только тех действий, которые отметил врач."""
    request_id: str
    approver: str
    digests: frozenset[str]
    expires_at: float
    signature: str


def sign(request_id: str, approver: str, digests: frozenset[str], expires_at: float) -> str:
    message = "|".join([request_id, approver, *sorted(digests), repr(expires_at)]).encode()
    return hmac.new(SIGNING_KEY, message, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class Gate:
    """Точка исполнения: действие проходит по классу из предавторизации или по токену."""
    preauthorized: frozenset[str] = frozenset()

    def requests(self, plan: list[ProposedAction], scope: Scope, now: float,
                 ttl: float) -> list[ApprovalRequest]:
        human = [a for a in plan if a.action_class not in self.preauthorized]
        groups: dict[str, list[ProposedAction]] = {}
        for a in human:
            key = {"action": a.action_id, "class": a.action_class, "plan": "plan"}[scope]
            groups.setdefault(key, []).append(a)
        return [ApprovalRequest(f"req-{key}", scope, tuple(items), now + ttl)
                for key, items in groups.items()]

    def check(self, action: ProposedAction, grant: Grant | None, now: float) -> str:
        if action.action_class in self.preauthorized:
            return "allowed:class"
        if grant is None:
            return "denied:no_grant"
        expected = sign(grant.request_id, grant.approver, grant.digests, grant.expires_at)
        if not hmac.compare_digest(expected, grant.signature):
            return "denied:bad_signature"
        if now >= grant.expires_at:
            return "denied:expired"
        if action.digest() not in grant.digests:
            return "denied:not_approved"
        return "allowed:grant"


def approve(request: ApprovalRequest, approver: str, selected: set[str]) -> Grant:
    """Пакет можно одобрить частично: токен покрывает только отмеченные действия."""
    digests = frozenset(a.digest() for a in request.actions if a.action_id in selected)
    return Grant(request.request_id, approver, digests, request.expires_at,
                 sign(request.request_id, approver, digests, request.expires_at))


if __name__ == "__main__":
    abx = ProposedAction("a1", "order.medication", "place_order",
                         {"drug": "ceftriaxone", "dose": "2 g", "route": "iv"})
    lactate = ProposedAction("a2", "order.lab", "place_order", {"test": "lactate"})
    culture = ProposedAction("a3", "order.lab", "place_order", {"test": "blood_culture", "sets": "2"})
    note = ProposedAction("a4", "note.draft", "draft_note", {"template": "sepsis_initial"})
    gate = Gate(preauthorized=frozenset({"note.draft"}))
    plan = [abx, lactate, culture, note]

    assert len(gate.requests(plan, "action", now=0.0, ttl=900.0)) == 3
    assert len(gate.requests(plan, "plan", now=0.0, ttl=900.0)) == 1
    meds, labs = gate.requests(plan, "class", now=0.0, ttl=900.0)
    assert [a.action_id for a in labs.actions] == ["a2", "a3"]        # пакет из двух анализов

    meds_grant = approve(meds, "dr-ivanova", {"a1"})
    labs_grant = approve(labs, "dr-ivanova", {"a2"})                   # посев врач снял
    assert gate.check(abx, meds_grant, now=120.0) == "allowed:grant"
    assert gate.check(lactate, labs_grant, now=120.0) == "allowed:grant"
    assert gate.check(culture, labs_grant, now=120.0) == "denied:not_approved"
    assert gate.check(note, None, now=120.0) == "allowed:class"
    double = replace(abx, args={**abx.args, "dose": "4 g"})             # модель изменила дозу
    assert gate.check(double, meds_grant, now=120.0) == "denied:not_approved"
    assert gate.check(abx, meds_grant, now=900.0) == "denied:expired"
    assert gate.check(abx, replace(meds_grant, approver="agent"), now=120.0) == "denied:bad_signature"
    print("одобрение привязано к аргументам, истекает и допускает пакеты и частичный выбор")
