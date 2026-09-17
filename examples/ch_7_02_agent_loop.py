from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, Field


class BudgetExceeded(Exception):
    """Цикл обязан остановиться: исчерпан один из бюджетов."""


@dataclass
class Budget:
    max_steps: int = 8
    max_side_effects: int = 1
    steps: int = 0
    side_effects: int = 0

    def charge_step(self) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise BudgetExceeded("шаги")

    def charge_side_effect(self) -> None:
        self.side_effects += 1
        if self.side_effects > self.max_side_effects:
            raise BudgetExceeded("побочные эффекты")


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
    """Структурированный итог расследования: причина, действие, свидетельства."""

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
            return Observation(call.name, f"инструмента {call.name} нет", True, "unknown_tool")
        if tool.side_effect:
            budget.charge_side_effect()
        try:
            return Observation(call.name, tool.handler(call.arguments))
        except TimeoutError:
            return Observation(call.name, "система не ответила вовремя", True, "upstream_timeout")


def run(model: Model, registry: Registry, state: AgentState) -> Finding:
    while True:
        try:
            state.budget.charge_step()
            decision = model.decide(state)
            if isinstance(decision, Finding):
                return decision
            state.observations.append(registry.invoke(decision, state.budget))
        except BudgetExceeded as stop:
            return Finding(cause=f"бюджет исчерпан: {stop}", action="escalate_to_human",
                           evidence=state.evidence())


class ScriptedModel:
    """Заглушка модели: читает наблюдения и выдаёт следующий шаг по сценарию."""

    def decide(self, state: AgentState) -> ToolCall | Finding:
        seen = state.evidence()
        for name in ("get_telematics", "get_carrier_status", "get_customs_status"):
            if name not in seen:
                return ToolCall(name, {"shipment_id": "SHP-8842"})
        if "notify_customer" not in seen:
            return ToolCall("notify_customer", {"shipment_id": "SHP-8842", "eta": "2026-03-04"})
        return Finding(cause="груз задержан таможней: не хватает документа M-4",
                       action="notify_customer", evidence=seen)


if __name__ == "__main__":
    flaky = {"n": 0}

    def customs(args: Mapping[str, Any]) -> str:
        flaky["n"] += 1
        if flaky["n"] == 1:
            raise TimeoutError
        return "hold: требуется документ M-4"

    registry = Registry([
        Tool("get_telematics", lambda a: "задержка 9 ч, Вроцлав"),
        Tool("get_carrier_status", lambda a: "рейс переставлен на 04.03"),
        Tool("get_customs_status", customs),
        Tool("notify_customer", lambda a: "сообщение отправлено", side_effect=True),
    ])
    state = AgentState(task="исключение по SHP-8842")
    found = run(ScriptedModel(), registry, state)
    assert found.action == "notify_customer"
    assert found.evidence == ["get_telematics", "get_carrier_status",
                              "get_customs_status", "notify_customer"]
    assert state.budget.steps == 6          # пять вызовов, включая повтор, и вывод
    assert state.budget.side_effects == 1

    tight = AgentState(task="то же исключение", budget=Budget(max_steps=2))
    stopped = run(ScriptedModel(), Registry(list(registry.tools.values())), tight)
    assert stopped.action == "escalate_to_human" and tight.budget.steps == 3
    print("цикл завершился структурированным ответом и остановился по бюджету")
