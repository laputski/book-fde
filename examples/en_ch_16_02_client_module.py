from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

MODULE_VERSION = "2.4.0"
SUPPORTED_SCHEMAS = frozenset({3, 4})         # schema 2 was retired in version 2.0.0


class ApprovalPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    approver_role: str = Field(min_length=3)
    ttl_s: int = Field(default=900, ge=60, le=86_400)


class ClientConfig(BaseModel):
    """Everything in which customers differ. The module core contains no customer names."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: int
    client: str = Field(pattern=r"^[a-z][a-z0-9-]{2,30}$")
    prompt_id: str                             # prompt version in the instruction registry
    min_score: float = Field(ge=0.3, le=0.95)
    public_users: bool = False
    require_citations: bool = True
    offline: bool = False
    model_host: Literal["cloud", "on_site"] = "cloud"
    actions: dict[str, ApprovalPolicy] = Field(default_factory=dict)

    @property
    def namespace(self) -> str:
        return f"{self.client}/"

    @model_validator(mode="after")
    def allowed_combinations(self) -> ClientConfig:
        if self.schema_version not in SUPPORTED_SCHEMAS:
            raise ValueError(f"schema {self.schema_version} is not supported by module {MODULE_VERSION}")
        if self.public_users and not self.require_citations:
            raise ValueError("a public service answers only with source citations")
        if self.offline and self.model_host != "on_site":
            raise ValueError("an air-gapped site needs an on-site model")
        return self


@dataclass(frozen=True)
class Passage:
    doc_id: str                                # "helix/wo-118": the tenant is part of the id
    text: str
    score: float


@dataclass(frozen=True)
class GroundedAssistant:
    config: ClientConfig

    def prompt(self, question: str, passages: list[Passage]) -> str | None:
        own = [p for p in passages if p.doc_id.startswith(self.config.namespace)]
        cited = sorted((p for p in own if p.score >= self.config.min_score), key=lambda p: -p.score)
        if self.config.require_citations and not cited:
            return None
        sources = "\n".join(f"[{p.doc_id}] {p.text}" for p in cited)
        return f"@{self.config.prompt_id}\n{sources}\n{question}"

    def may_execute(self, action: str, target: str,
                    approvals: dict[tuple[str, str], float], now: float) -> bool:
        policy = self.config.actions.get(action)
        granted_at = approvals.get((action, target))
        return policy is not None and granted_at is not None and now - granted_at <= policy.ttl_s


def compatibility_test(config: ClientConfig) -> list[str]:
    """One contract for all; runs on every configuration at every release."""
    bot, ns = GroundedAssistant(config), config.namespace
    failures: list[str] = []
    leaked = bot.prompt("question", [Passage("other/doc-1", "foreign document", 0.99)]) or ""
    if "other/" in leaked:
        failures.append("another customer's document reached the prompt")
    ranked = bot.prompt("question", [Passage(ns + "a", "weak", config.min_score),
                                   Passage(ns + "b", "strong", 0.99)]) or ""
    if not ranked or ranked.index(f"[{ns}b]") > ranked.index(f"[{ns}a]"):
        failures.append("sources are not ordered by relevance")
    for action, policy in config.actions.items():
        if bot.may_execute(action, "t-2", {(action, "t-1"): 0.0}, now=1.0):
            failures.append(f"{action}: approval is not bound to the target")
        if bot.may_execute(action, "t-1", {(action, "t-1"): 0.0}, now=policy.ttl_s + 1.0):
            failures.append(f"{action}: an expired approval was accepted")
    if bot.may_execute("undeclared", "t-1", {("undeclared", "t-1"): 0.0}, now=1.0):
        failures.append("an action absent from the configuration was executed")
    return failures


if __name__ == "__main__":
    configs = [
        ClientConfig(schema_version=4, client="nordbank", prompt_id="nb-contact@7", min_score=0.62,
                     actions={"create_dispute": ApprovalPolicy(approver_role="operator")}),
        ClientConfig(schema_version=3, client="orion", prompt_id="or-assist@12", min_score=0.55,
                     actions={"publish_status": ApprovalPolicy(approver_role="duty_engineer", ttl_s=300)}),
        ClientConfig(schema_version=4, client="northgate", prompt_id="ng-citizen@5", min_score=0.70,
                     public_users=True, actions={"submit_request": ApprovalPolicy(approver_role="resident")}),
        ClientConfig(schema_version=4, client="helix", prompt_id="hx-maint@1", min_score=0.60,
                     offline=True, model_host="on_site",
                     actions={"order_part": ApprovalPolicy(approver_role="site_engineer", ttl_s=3600)}),
    ]
    assert {c.client: compatibility_test(c) for c in configs} == {c.client: [] for c in configs}
    base = {"schema_version": 4, "client": "helix", "prompt_id": "hx-maint@1", "min_score": 0.6}
    for bad in ({"public_users": True, "require_citations": False}, {"offline": True},
                {"schema_version": 2}, {"approve_by_name": True}):
        try:
            ClientConfig.model_validate(base | bad)
            raise AssertionError(f"invalid configuration accepted: {bad}")
        except ValidationError:
            pass
    print("module", MODULE_VERSION, "is compatible with", len(configs), "customer configurations")
