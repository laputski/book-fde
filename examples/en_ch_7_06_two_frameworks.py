from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypedDict

TOOLS = ("get_telematics", "get_carrier_status", "get_customs_status")


@dataclass(frozen=True)
class Step:
    tool: str | None                       # None means "the investigation is over"
    answer: str = ""


def policy(evidence: Sequence[str]) -> Step:
    """The agent's logic, shared by both frameworks and independent of either."""
    for tool in TOOLS:
        if tool not in evidence:
            return Step(tool)
    return Step(None, answer="customs delay, notify the customer")


# ── Framework 1: the runner stores the state ──────────────────────────────────


class Session:
    """A skeleton in the spirit of ADK: the framework's session keeps untyped state."""

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
        return "step budget exhausted"


# ── Framework 2: the application declares the state schema ────────────────────


class GraphState(TypedDict):
    """The state schema is declared by the application and checked by its types."""

    evidence: list[str]
    answer: str
    steps: int


class Graph:
    """A skeleton in the spirit of LangGraph: pure nodes, a route picks the next node."""

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
        state["answer"] = "step budget exhausted"
        return state


if __name__ == "__main__":
    calls: list[str] = []

    def make_tool(name: str) -> Callable[[], str]:
        def tool() -> str:
            calls.append(name)
            return f"{name}: done"
        return tool

    runner = Runner({name: make_tool(name) for name in TOOLS})
    session = Session()
    assert runner.run(session) == "customs delay, notify the customer"
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
    assert final["answer"] == "customs delay, notify the customer"
    assert final["evidence"] == list(TOOLS) and final["steps"] == 3
    assert calls == list(TOOLS) * 2                      # one and the same investigation

    assert set(GraphState.__annotations__) == {"evidence", "answer", "steps"}
    assert "evidence" not in Session().state             # the runner has no state schema
    print("one logic, two frameworks; the difference is who declares the state schema")
