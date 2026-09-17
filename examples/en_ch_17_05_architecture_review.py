from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date


@dataclass(frozen=True)
class Binding:
    point: int
    option: str
    hosting: str                    # managed | in_tenancy | on_site
    adr: int | None = None          # the number of the ADR that justifies the choice
    exit_drill: date | None = None  # the last exit drill
    portable: bool = False          # data and evals are kept in the customer's own format


@dataclass(frozen=True)
class Config:
    site: str
    air_gapped: bool
    bindings: tuple[Binding, ...]
    eval_owner: str | None = None   # the owner of the evaluation set on the customer's side


@dataclass(frozen=True, order=True)
class Finding:
    point: int
    check: str
    detail: str


type Check = Callable[[Config, date], list[Finding]]
CHECKS: list[Check] = []


def check(fn: Check) -> Check:
    CHECKS.append(fn)
    return fn


@check
def decision_recorded(cfg: Config, today: date) -> list[Finding]:
    return [Finding(b.point, "adr", f"{b.option} chosen without an ADR") for b in cfg.bindings if b.adr is None]


@check
def reachable_from_site(cfg: Config, today: date) -> list[Finding]:
    return [Finding(b.point, "air_gap", f"{b.option} is unreachable without a cloud connection")
            for b in cfg.bindings if cfg.air_gapped and b.hosting != "on_site"]


@check
def exit_rehearsed(cfg: Config, today: date) -> list[Finding]:
    stale = [b for b in cfg.bindings if b.hosting == "managed"
             and (b.exit_drill is None or (today - b.exit_drill).days > 365)]
    return [Finding(b.point, "exit_drill", f"leaving {b.option} has not been rehearsed for over a year") for b in stale]


@check
def portable_state(cfg: Config, today: date) -> list[Finding]:
    return [Finding(b.point, "portability", f"the state of {b.option} exists only in the vendor's format")
            for b in cfg.bindings if b.hosting == "managed" and not b.portable]


@check
def evaluation_owned(cfg: Config, today: date) -> list[Finding]:
    return [] if cfg.eval_owner else [Finding(5, "eval_owner", "the evaluation set has no owner at the customer")]


def review(cfg: Config, today: date) -> list[Finding]:
    return sorted(f for c in CHECKS for f in c(cfg, today))


if __name__ == "__main__":
    today = date(2026, 9, 14)
    city = Config("Northgate", air_gapped=False, eval_owner="benefits service", bindings=(
        Binding(1, "managed_runtime", "managed", adr=5, exit_drill=date(2026, 3, 2), portable=True),
        Binding(2, "paygo_regional", "managed", adr=7, exit_drill=date(2025, 6, 20), portable=True),
        Binding(4, "managed_index", "managed", adr=8, exit_drill=date(2026, 5, 11)),
        Binding(6, "customer_keys", "managed", adr=9, exit_drill=date(2026, 5, 11), portable=True)))
    found = review(city, today)
    assert [(f.point, f.check) for f in found] == [(2, "exit_drill"), (4, "portability")]
    fixed = replace(city, bindings=tuple(
        replace(b, exit_drill=date(2026, 9, 1), portable=True) if b.point in (2, 4) else b
        for b in city.bindings))
    assert review(fixed, today) == []
    plant = Config("Helix, plant 12", air_gapped=True, bindings=(
        Binding(2, "open_weights_edge", "on_site", adr=21), Binding(5, "managed_traces", "managed", adr=22)))
    at_five = {f.check for f in review(plant, today) if f.point == 5}
    assert at_five == {"air_gap", "exit_drill", "portability", "eval_owner"}
    print(f"checks: {len(CHECKS)}, findings for Northgate: {len(found)}, after the fix: 0")
