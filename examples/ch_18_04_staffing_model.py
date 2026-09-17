from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from fractions import Fraction
from itertools import combinations

MAX_UTIL = Fraction("0.8")               # остальное: паттерны и модули
TEAM = 2                                 # двое на заказчика: второй снимает риск ключевого человека


class Phase(StrEnum):
    PRESALES = "presales"
    BUILD = "сборка"
    PILOT = "пилот"
    RUN = "эксплуатация"
    HANDOVER = "передача"


LOAD = {Phase.PRESALES: Fraction("0.2"), Phase.BUILD: Fraction("1.0"), Phase.PILOT: Fraction("0.8"),
        Phase.RUN: Fraction("0.4"), Phase.HANDOVER: Fraction("0.4")}   # FTE на заказчика


@dataclass(frozen=True)
class Engineer:
    name: str
    skills: frozenset[str]


@dataclass(frozen=True)
class Customer:
    code: str
    phase: Phase
    skills: frozenset[str]


class Infeasible(Exception):
    """План невозможен; сообщение называет причину."""


def covered(team: tuple[Engineer, ...], customer: Customer) -> bool:
    """Нет единственной точки отказа: каждый навык есть хотя бы у двоих."""
    return all(sum(skill in e.skills for e in team) >= 2 for skill in customer.skills)


def gaps(engineers: list[Engineer], customers: list[Customer]) -> list[str]:
    return [f"{c.code}: {skill} есть у {n} из 2 нужных" for c in customers
            for skill in sorted(c.skills) if (n := sum(skill in e.skills for e in engineers)) < 2]


def plan(engineers: list[Engineer], customers: list[Customer],
         max_util: Fraction = MAX_UTIL) -> dict[str, tuple[str, ...]]:
    if found := gaps(engineers, customers):
        raise Infeasible("; ".join(found))
    demand, capacity = sum(LOAD[c.phase] for c in customers), max_util * len(engineers)
    if demand > capacity:
        raise Infeasible(f"спрос {float(demand)} FTE больше ёмкости {float(capacity)} FTE")
    order = sorted(customers, key=lambda c: (-LOAD[c.phase], c.code))
    load = {e.name: Fraction(0) for e in engineers}
    chosen: dict[str, tuple[str, ...]] = {}

    def place(i: int) -> bool:
        if i == len(order):
            return True
        c = order[i]
        share = LOAD[c.phase] / TEAM
        for team in combinations(sorted(engineers, key=lambda e: (load[e.name], e.name)), TEAM):
            if not covered(team, c) or any(load[e.name] + share > max_util for e in team):
                continue
            for e in team:
                load[e.name] += share
            chosen[c.code] = tuple(sorted(e.name for e in team))
            if place(i + 1):
                return True
            for e in team:
                load[e.name] -= share
            del chosen[c.code]
        return False

    if not place(0):
        raise Infeasible("при заданных ограничениях назначения нет")
    return dict(sorted(chosen.items()))


def utilisation(engineers: list[Engineer], customers: list[Customer],
                assignment: dict[str, tuple[str, ...]]) -> dict[str, Fraction]:
    phase = {c.code: c.phase for c in customers}
    util = {e.name: Fraction(0) for e in engineers}
    for code, team in assignment.items():
        for name in team:
            util[name] += LOAD[phase[code]] / len(team)
    return util


if __name__ == "__main__":
    def skills(*names: str) -> frozenset[str]:
        return frozenset(names)

    squad = [Engineer("Анна", skills("agents", "mcp", "evals")),
             Engineer("Борис", skills("rag", "evals", "security", "voice", "agents")),
             Engineer("Вера", skills("agents", "voice", "security", "rag")),
             Engineer("Глеб", skills("rag", "edge", "mcp", "evals")),
             Engineer("Дина", skills("evals", "observability", "agents", "mcp", "rag")),
             Engineer("Егор", skills("mcp", "observability", "rag", "security"))]
    customers = [Customer("CF1", Phase.RUN, skills("mcp", "evals")),
                 Customer("CF2", Phase.PILOT, skills("voice", "rag")),
                 Customer("CF3", Phase.BUILD, skills("agents", "mcp")),
                 Customer("CF4", Phase.RUN, skills("observability", "rag")),
                 Customer("CF5", Phase.HANDOVER, skills("security", "agents")),
                 Customer("CF6", Phase.BUILD, skills("edge", "rag")),
                 Customer("P1", Phase.PRESALES, skills("agents")),
                 Customer("P2", Phase.PRESALES, skills("evals"))]
    try:
        plan(squad, customers)
        raise AssertionError("план с единственным носителем edge принят")
    except Infeasible as err:
        assert str(err) == "CF6: edge есть у 1 из 2 нужных"
    squad[5] = replace(squad[5], skills=squad[5].skills | {"edge"})   # план обучения: пара с Глебом
    assignment = plan(squad, customers)
    util = utilisation(squad, customers, assignment)
    assert max(util.values()) <= MAX_UTIL and sum(util.values()) == Fraction("4.4")
    assert {"Глеб", "Егор"} <= set(assignment["CF6"])
    try:
        plan(squad, customers, max_util=Fraction("0.7"))
        raise AssertionError("спрос выше ёмкости принят")
    except Infeasible as err:
        assert str(err).startswith("спрос 4.4 FTE")
    print(assignment, {n: f"{float(u):.0%}" for n, u in util.items()})
