from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, Field


class BudgetExceeded(Exception):
    """The loop must stop: one of the budgets is exhausted."""


@dataclass
class Budget:
    max_steps: int = 8
    max_side_effects: int = 1
    steps: int = 0
    side_effects: int = 0

    def charge_step(self) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise BudgetExceeded("steps")

    def charge_side_effect(self) -> None:
        self.side_effects += 1
        if self.side_effects > self.max_side_effects:
            raise BudgetExceeded("side effects")


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True)
class Observation:
    tool: str
    content: str
    is_error: bool = False
    code: str = ""


class Finding(BaseModel):
    """The structured result of an investigation: cause, action, evidence."""

    cause: str
    action: str
    evidence: list[str] = Field(default_factory=list)


@dataclass
class AgentState:
    task: str
    budget: Budget = field(default_factory=Budget)
    observations: list[Observation] = field(default_factory=list)

    def evidence(self) -> list[str]:
        return [o.tool for o in self.observations if not o.is_error]


class Model(Protocol):
    def decide(self, state: AgentState) -> ToolCall | Finding: ...


@dataclass(frozen=True)
class Tool:
    name: str
    handler: Callable[[Mapping[str, Any]], str]
    side_effect: bool = False


class Registry:
    def __init__(self, tools: Sequence[Tool]) -> None:
        self.tools = {t.name: t for t in tools}

    def invoke(self, call: ToolCall, budget: Budget) -> Observation:
        tool = self.tools.get(call.name)
        if tool is None:
            return Observation(call.name, f"no tool named {call.name}", True, "unknown_tool")
        if tool.side_effect:
            budget.charge_side_effect()
        try:
            return Observation(call.name, tool.handler(call.arguments))
        except TimeoutError:
            return Observation(call.name, "the system did not answer in time", True, "upstream_timeout")


def run(model: Model, registry: Registry, state: AgentState) -> Finding:
    while True:
        try:
            state.budget.charge_step()
            decision = model.decide(state)
            if isinstance(decision, Finding):
                return decision
            state.observations.append(registry.invoke(decision, state.budget))
        except BudgetExceeded as stop:
            return Finding(cause=f"budget exhausted: {stop}", action="escalate_to_human",
                           evidence=state.evidence())


class ScriptedModel:
    """A model stub: reads the observations and emits the next step of the scenario."""

    def decide(self, state: AgentState) -> ToolCall | Finding:
        seen = state.evidence()
        for name in ("get_telematics", "get_carrier_status", "get_customs_status"):
            if name not in seen:
                return ToolCall(name, {"shipment_id": "SHP-8842"})
        if "notify_customer" not in seen:
            return ToolCall("notify_customer", {"shipment_id": "SHP-8842", "eta": "2026-03-04"})
        return Finding(cause="cargo held by customs: document M-4 is missing",
                       action="notify_customer", evidence=seen)


if __name__ == "__main__":
    flaky = {"n": 0}

    def customs(args: Mapping[str, Any]) -> str:
        flaky["n"] += 1
        if flaky["n"] == 1:
            raise TimeoutError
        return "hold: document M-4 required"

    registry = Registry([
        Tool("get_telematics", lambda a: "delay 9 h, Wrocław"),
        Tool("get_carrier_status", lambda a: "trip rescheduled to 4 March"),
        Tool("get_customs_status", customs),
        Tool("notify_customer", lambda a: "message sent", side_effect=True),
    ])
    state = AgentState(task="exception on SHP-8842")
    found = run(ScriptedModel(), registry, state)
    assert found.action == "notify_customer"
    assert found.evidence == ["get_telematics", "get_carrier_status",
                              "get_customs_status", "notify_customer"]
    assert state.budget.steps == 6          # five calls, the retry included, and the conclusion
    assert state.budget.side_effects == 1

    tight = AgentState(task="the same exception", budget=Budget(max_steps=2))
    stopped = run(ScriptedModel(), Registry(list(registry.tools.values())), tight)
    assert stopped.action == "escalate_to_human" and tight.budget.steps == 3
    print("the loop ended with a structured answer and stopped on the budget")
