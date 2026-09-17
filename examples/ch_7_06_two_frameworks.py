from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypedDict

TOOLS = ("get_telematics", "get_carrier_status", "get_customs_status")


@dataclass(frozen=True)
class Step:
    tool: str | None                       # None означает «расследование закончено»
    answer: str = ""


def policy(evidence: Sequence[str]) -> Step:
    """Логика агента, общая для обоих фреймворков и не зависящая ни от одного из них."""
    for tool in TOOLS:
        if tool not in evidence:
            return Step(tool)
    return Step(None, answer="задержка на таможне, уведомить клиента")


# ── Фреймворк 1: состояние хранит runner ───────────────────────────────────


class Session:
    """Каркас в духе ADK: сессия фреймворка хранит состояние нетипизированным."""

    def __init__(self) -> None:
        self.state: dict[str, Any] = {}


class Runner:
    def __init__(self, tools: Mapping[str, Callable[[], str]], max_steps: int = 6) -> None:
        self.tools = tools
        self.max_steps = max_steps

    def run(self, session: Session) -> str:
        session.state.setdefault("evidence", [])
        for _ in range(self.max_steps):
            step = policy(session.state["evidence"])
            if step.tool is None:
                return step.answer
            self.tools[step.tool]()
            session.state["evidence"].append(step.tool)
        return "бюджет шагов исчерпан"


# ── Фреймворк 2: схему состояния объявляет приложение ──────────────────────


class GraphState(TypedDict):
    """Схема состояния объявлена приложением и проверяется его типами."""

    evidence: list[str]
    answer: str
    steps: int


class Graph:
    """Каркас в духе LangGraph: узлы чистые, маршрут выбирает следующий узел."""

    def __init__(self, nodes: Mapping[str, Callable[[GraphState], GraphState]],
                 route: Callable[[GraphState], str], max_steps: int = 6) -> None:
        self.nodes = nodes
        self.route = route
        self.max_steps = max_steps

    def invoke(self, state: GraphState) -> GraphState:
        for _ in range(self.max_steps):
            name = self.route(state)
            if name == "END":
                return state
            state = self.nodes[name](state)
        state["answer"] = "бюджет шагов исчерпан"
        return state


if __name__ == "__main__":
    calls: list[str] = []

    def make_tool(name: str) -> Callable[[], str]:
        def tool() -> str:
            calls.append(name)
            return f"{name}: готово"
        return tool

    runner = Runner({name: make_tool(name) for name in TOOLS})
    session = Session()
    assert runner.run(session) == "задержка на таможне, уведомить клиента"
    assert session.state["evidence"] == list(TOOLS)
    assert calls == list(TOOLS)

    def make_node(name: str) -> Callable[[GraphState], GraphState]:
        def node(state: GraphState) -> GraphState:
            calls.append(name)
            return {"evidence": [*state["evidence"], name],
                    "answer": state["answer"], "steps": state["steps"] + 1}
        return node

    def route(state: GraphState) -> str:
        step = policy(state["evidence"])
        if step.tool is None:
            state["answer"] = step.answer
            return "END"
        return step.tool

    graph = Graph({name: make_node(name) for name in TOOLS}, route)
    final = graph.invoke({"evidence": [], "answer": "", "steps": 0})
    assert final["answer"] == "задержка на таможне, уведомить клиента"
    assert final["evidence"] == list(TOOLS) and final["steps"] == 3
    assert calls == list(TOOLS) * 2                      # одно и то же расследование

    assert set(GraphState.__annotations__) == {"evidence", "answer", "steps"}
    assert "evidence" not in Session().state             # схемы состояния у runner нет
    print("одна логика, два фреймворка; различие в том, кто объявляет схему состояния")
