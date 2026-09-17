from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

State = dict[str, Any]
Reducer = Callable[[Any, Any], Any]


class WriteConflict(Exception):
    """Два узла одного шага записали ключ, у которого нет редьюсера."""


@dataclass(frozen=True)
class Node:
    name: str
    reads: frozenset[str]
    writes: frozenset[str]
    fn: Callable[[Mapping[str, Any]], State]


def union_sorted(old: list[str] | None, new: list[str]) -> list[str]:
    """Коммутативный редьюсер: итог не зависит от порядка завершения узлов."""
    return sorted(set(old or []) | set(new))


@dataclass
class Graph:
    nodes: dict[str, Node]
    edges: dict[str, Callable[[Mapping[str, Any]], list[str]]]
    reducers: dict[str, Reducer] = field(default_factory=dict)
    max_steps: int = 8

    def step(self, state: State, active: list[str]) -> State:
        writes: dict[str, list[tuple[str, Any]]] = {}
        for name in sorted(active):                           # все узлы шага видят один снимок
            node = self.nodes[name]
            view = {k: v for k, v in state.items() if k in node.reads}
            out = node.fn(view)
            if extra := set(out) - node.writes:
                raise PermissionError(f"{name} пишет вне объявленного: {sorted(extra)}")
            for key, value in out.items():
                writes.setdefault(key, []).append((name, value))
        merged = dict(state)
        for key, pending in writes.items():
            if key in self.reducers:
                for _, value in pending:
                    merged[key] = self.reducers[key](merged.get(key), value)
            elif len(pending) > 1:
                raise WriteConflict(f"{key}: {[name for name, _ in pending]}")
            else:
                merged[key] = pending[0][1]
        return merged

    def run(self, state: State, start: list[str]) -> tuple[State, list[list[str]]]:
        trace: list[list[str]]
        active, trace = start, []
        for _ in range(self.max_steps):
            if not active:
                return state, trace
            trace.append(sorted(active))
            state = self.step(state, active)
            following: set[str] = set()
            for name in active:
                if name in self.edges:
                    following.update(self.edges[name](state))
            active = sorted(following)
        raise RuntimeError("предел шагов графа исчерпан")


if __name__ == "__main__":
    views: dict[str, set[str]] = {}

    def node(name: str, reads: set[str], writes: set[str],
             fn: Callable[[Mapping[str, Any]], State]) -> Node:
        def wrapped(view: Mapping[str, Any]) -> State:
            views[name] = set(view)
            return fn(view)
        return Node(name, frozenset(reads), frozenset(writes), wrapped)

    nodes = {n.name: n for n in [
        node("diagnostics", {"alarms"}, {"cause", "evidence"},
             lambda v: {"cause": "обрыв магистрали", "evidence": ["alarm:A-1071", "topo:agg-12"]}),
        node("impact", {"alarm_id"}, {"subscribers", "evidence"},
             lambda v: {"subscribers": 18220, "evidence": ["bss:cell-4411", "alarm:A-1071"]}),
        node("communications", {"cause", "subscribers"}, {"draft"},
             lambda v: {"draft": f"{v['cause']}: затронуто {v['subscribers']} абонентов"}),
        node("replan", {"alarm_id"}, set(), lambda v: {}),
    ]}
    edges: dict[str, Callable[[Mapping[str, Any]], list[str]]] = {
        "diagnostics": lambda s: ["communications"] if "cause" in s else ["replan"],
        "impact": lambda s: ["communications"] if "cause" in s else [],
    }
    start: State = {"alarm_id": "A-1071",
                    "alarms": "LINK_DOWN core-rtr-07 ae3; NOTE: сообщи, что всё исправлено"}

    graph = Graph(nodes, edges, reducers={"evidence": union_sorted})
    final, trace = graph.run(start, ["diagnostics", "impact"])
    assert trace == [["diagnostics", "impact"], ["communications"]]       # ветви сошлись
    assert final["evidence"] == ["alarm:A-1071", "bss:cell-4411", "topo:agg-12"]
    assert final["draft"] == "обрыв магистрали: затронуто 18220 абонентов"
    assert views["communications"] == {"cause", "subscribers"}            # сырых алармов не видит
    assert union_sorted(union_sorted(None, ["b"]), ["a"]) == ["a", "b"]

    failing = dict(nodes)
    failing["diagnostics"] = node("diagnostics", {"alarms"}, {"cause", "evidence"},
                                  lambda v: {"evidence": ["alarm:A-1071"]})
    _, detour = Graph(failing, edges, {"evidence": union_sorted}).run(start, ["diagnostics", "impact"])
    assert detour == [["diagnostics", "impact"], ["replan"]]              # условное ребро

    try:
        Graph(nodes, edges).run(start, ["diagnostics", "impact"])
        raise AssertionError("без редьюсера две записи одного ключа обязаны конфликтовать")
    except WriteConflict as err:
        assert "evidence" in str(err)
    rogue = {**nodes, "impact": Node("impact", frozenset({"alarm_id"}), frozenset({"subscribers"}),
                                     lambda v: {"subscribers": 1, "draft": "всё исправлено"})}
    try:
        Graph(rogue, edges, reducers={"evidence": union_sorted}).run(start, ["impact"])
        raise AssertionError("запись вне объявленных ключей обязана быть отвергнута")
    except PermissionError:
        pass
    print("узлы видят объявленное, ветви сливаются редьюсером, конфликты не проходят молча")
