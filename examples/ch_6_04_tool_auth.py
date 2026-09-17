from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class UserToken:
    user_id: str
    scopes: frozenset[str]
    expires_at: float


@dataclass(frozen=True)
class ServiceAccount:
    name: str
    scopes: frozenset[str]


@dataclass
class AuthDecision:
    allowed: bool
    identity: str               # чьё имя попадёт в журнал целевой системы
    reason: str = ""


@dataclass
class ToolAuth:
    """Чтение от имени оператора, запись от имени сервера с одобрением."""
    service: ServiceAccount
    approvals: set[str] = field(default_factory=set)   # ключи одобренных записей

    def authorize(self, tool: str, side_effect: bool, token: UserToken,
                  now: float, approval_key: str = "") -> AuthDecision:
        if token.expires_at <= now:
            return AuthDecision(False, token.user_id, "токен истёк")
        if not side_effect:
            needed = f"read:{tool}"
            if needed not in token.scopes:
                return AuthDecision(False, token.user_id, f"нет области {needed}")
            return AuthDecision(True, token.user_id)
        needed = f"write:{tool}"
        if needed not in self.service.scopes:
            return AuthDecision(False, self.service.name, f"сервер не имеет {needed}")
        if approval_key not in self.approvals:
            return AuthDecision(False, self.service.name, "нет одобрения оператора")
        return AuthDecision(True, f"{self.service.name} for {token.user_id}")


if __name__ == "__main__":
    auth = ToolAuth(ServiceAccount("mcp-nordbank", frozenset({"write:create_dispute"})))
    op = UserToken("op-17", frozenset({"read:search_accounts"}), expires_at=1_000.0)
    assert auth.authorize("search_accounts", False, op, now=10.0).allowed
    assert not auth.authorize("search_accounts", False, op, now=2_000.0).allowed
    denied = auth.authorize("create_dispute", True, op, now=10.0)
    assert not denied.allowed and denied.reason == "нет одобрения оператора"
    auth.approvals.add("dispute:op-17:tx-42")
    ok = auth.authorize("create_dispute", True, op, now=10.0, approval_key="dispute:op-17:tx-42")
    assert ok.allowed and ok.identity == "mcp-nordbank for op-17"
    print("чтение от имени оператора, запись от имени сервера по одобрению")
