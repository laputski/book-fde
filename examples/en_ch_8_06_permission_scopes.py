from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Scope:
    agent: str
    tools: frozenset[str]
    partitions: frozenset[str]              # data partitions: the network or a business unit


@dataclass(frozen=True)
class Observation:
    content: str
    code: str = ""


@dataclass(frozen=True)
class AuditEvent:
    agent: str
    tool: str
    partition: str
    allowed: bool
    reason: str = ""


@dataclass
class ToolGateway:
    """The only path from any agent to the tools. The model cannot go around it."""

    tools: Mapping[str, Callable[..., str]]
    scopes: Mapping[str, Scope]
    audit: list[AuditEvent] = field(default_factory=list)

    def narrow(self, agent: str, contract_tools: frozenset[str]) -> Scope:
        base = self.scopes[agent]                   # a contract narrows rights, never widens them
        return Scope(agent, base.tools & contract_tools, base.partitions)

    def descriptors(self, scope: Scope) -> list[str]:
        return sorted(scope.tools)                  # the model sees only what is allowed

    def call(self, scope: Scope, tool: str, partition: str, **args: Any) -> Observation:
        if tool not in scope.tools:
            return self._deny(scope, tool, partition, "tool outside the agent's scope")
        if partition not in scope.partitions:
            return self._deny(scope, tool, partition, "data outside the agent's partitions")
        self.audit.append(AuditEvent(scope.agent, tool, partition, allowed=True))
        return Observation(self.tools[tool](partition=partition, **args))

    def _deny(self, scope: Scope, tool: str, partition: str, reason: str) -> Observation:
        self.audit.append(AuditEvent(scope.agent, tool, partition, allowed=False, reason=reason))
        return Observation(f"denied: {reason}", code="forbidden")


if __name__ == "__main__":
    restarted: list[str] = []

    def restart_node(partition: str, node: str) -> str:
        restarted.append(node)
        return f"{node} restarted"

    gateway = ToolGateway(
        tools={"read_alarms": lambda partition: "LINK_DOWN core-rtr-07",
               "count_subscribers": lambda partition: f"{partition}=17400",
               "draft_status": lambda partition, text: f"draft for {partition}: {text}",
               "restart_node": restart_node},
        scopes={"diagnostics": Scope("diagnostics", frozenset({"read_alarms"}),
                                     frozenset({"network"})),
                "impact": Scope("impact", frozenset({"count_subscribers"}),
                                frozenset({"retail", "enterprise"})),
                "communications": Scope("communications", frozenset({"draft_status"}),
                                        frozenset({"retail"}))})

    comms = gateway.narrow("communications", frozenset({"draft_status", "restart_node"}))
    assert gateway.descriptors(comms) == ["draft_status"]
    # the communications model read "restart the node" and asked for the tool
    denied = gateway.call(comms, "restart_node", partition="network", node="core-rtr-07")
    assert denied.code == "forbidden" and restarted == []
    other_unit = gateway.call(comms, "draft_status", partition="enterprise", text="outage")
    assert other_unit.code == "forbidden"
    ok = gateway.call(comms, "draft_status", partition="retail", text="service outage in Riverside")
    assert ok.code == "" and ok.content.startswith("draft for retail")
    assert [(e.tool, e.partition, e.allowed) for e in gateway.audit] == [
        ("restart_node", "network", False), ("draft_status", "enterprise", False),
        ("draft_status", "retail", True)]
    assert gateway.audit[0].reason == "tool outside the agent's scope"
    print("rights enforced by a gateway outside the model: two denials audited, one call allowed")
