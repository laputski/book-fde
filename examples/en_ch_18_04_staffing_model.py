from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from fractions import Fraction
from itertools import combinations

MAX_UTIL = Fraction("0.8")               # the rest: patterns and modules
TEAM = 2                                 # two per customer: the second removes key-person risk


class Phase(StrEnum):
    PRESALES = "presales"
    BUILD = "build"
    PILOT = "pilot"
    RUN = "run"
    HANDOVER = "handover"


LOAD = {Phase.PRESALES: Fraction("0.2"), Phase.BUILD: Fraction("1.0"), Phase.PILOT: Fraction("0.8"),
        Phase.RUN: Fraction("0.4"), Phase.HANDOVER: Fraction("0.4")}   # FTE per customer


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
    """The plan is impossible; the message names the reason."""


def covered(team: tuple[Engineer, ...], customer: Customer) -> bool:
    """No single point of failure: every skill is held by at least two."""
    return all(sum(skill in e.skills for e in team) >= 2 for skill in customer.skills)


def gaps(engineers: list[Engineer], customers: list[Customer]) -> list[str]:
    return [f"{c.code}: {skill} held by {n} of the 2 needed" for c in customers
            for skill in sorted(c.skills) if (n := sum(skill in e.skills for e in engineers)) < 2]


def plan(engineers: list[Engineer], customers: list[Customer],
         max_util: Fraction = MAX_UTIL) -> dict[str, tuple[str, ...]]:
    if found := gaps(engineers, customers):
        raise Infeasible("; ".join(found))
    demand, capacity = sum(LOAD[c.phase] for c in customers), max_util * len(engineers)
    if demand > capacity:
        raise Infeasible(f"demand of {float(demand)} FTE exceeds capacity of {float(capacity)} FTE")
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
        raise Infeasible("no assignment satisfies the constraints")
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

    squad = [Engineer("Anna", skills("agents", "mcp", "evals")),
             Engineer("Boris", skills("rag", "evals", "security", "voice", "agents")),
             Engineer("Vera", skills("agents", "voice", "security", "rag")),
             Engineer("Gleb", skills("rag", "edge", "mcp", "evals")),
             Engineer("Dina", skills("evals", "observability", "agents", "mcp", "rag")),
             Engineer("Egor", skills("mcp", "observability", "rag", "security"))]
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
        raise AssertionError("a plan with a single holder of edge was accepted")
    except Infeasible as err:
        assert str(err) == "CF6: edge held by 1 of the 2 needed"
    squad[5] = replace(squad[5], skills=squad[5].skills | {"edge"})   # learning plan: pair with Gleb
    assignment = plan(squad, customers)
    util = utilisation(squad, customers, assignment)
    assert max(util.values()) <= MAX_UTIL and sum(util.values()) == Fraction("4.4")
    assert {"Gleb", "Egor"} <= set(assignment["CF6"])
    try:
        plan(squad, customers, max_util=Fraction("0.7"))
        raise AssertionError("demand above capacity was accepted")
    except Infeasible as err:
        assert str(err).startswith("demand of 4.4 FTE")
    print(assignment, {n: f"{float(u):.0%}" for n, u in util.items()})
