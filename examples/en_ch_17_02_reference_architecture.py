from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator


class Layer(StrEnum):
    CHANNELS = "channels"
    RUNTIME = "agent runtime"
    TOOLS = "tools and integration"
    DATA = "data and retrieval"
    EVALUATION = "evaluation and observability"
    GOVERNANCE = "security and governance"


class Hosting(StrEnum):
    MANAGED = "managed"          # a vendor service, operated by the vendor
    TENANT = "in_tenancy"        # the customer's cloud project, operated by the customer
    ON_SITE = "on_site"          # a site with no connection to the cloud


class Driver(StrEnum):
    RESIDENCY = "residency"
    VOLUME = "volume stability"
    LATENCY = "latency"
    OPERATIONS = "operations"
    REGULATION = "regulation"


@dataclass(frozen=True)
class Option:
    name: str
    hosting: Hosting
    ops_fte: float = 0.0         # operations on the customer's side, in FTE
    residency: bool = True       # processing and keys stay in the customer's jurisdiction
    commitment: bool = False     # capacity is paid for a term in advance


@dataclass(frozen=True)
class Point:
    number: int
    component: str
    layer: Layer
    drivers: frozenset[Driver]
    options: tuple[Option, ...]


M, T, S = Hosting.MANAGED, Hosting.TENANT, Hosting.ON_SITE
D = Driver
FIXED = {Layer.CHANNELS: "one agent API", Layer.TOOLS: "policy outside the model",
         Layer.DATA: "systems of record", Layer.EVALUATION: "evaluation gate", Layer.GOVERNANCE: "audit log"}
POINTS = {p.number: p for p in (
    Point(1, "agent loop", Layer.RUNTIME, frozenset({D.OPERATIONS, D.RESIDENCY}),
          (Option("managed_runtime", M), Option("container", T, 0.5), Option("edge_container", S, 0.5))),
    Point(2, "model endpoint", Layer.RUNTIME, frozenset({D.VOLUME, D.LATENCY, D.RESIDENCY}),
          (Option("paygo_regional", M), Option("paygo_global", M, residency=False),
           Option("provisioned", M, commitment=True), Option("open_weights", T, 1.5),
           Option("open_weights_edge", S, 1.0))),
    Point(3, "MCP servers", Layer.TOOLS, frozenset({D.REGULATION}),
          (Option("mcp_in_perimeter", T, 0.5), Option("mcp_on_site", S, 0.5))),
    Point(4, "retrieval index", Layer.DATA, frozenset({D.RESIDENCY, D.VOLUME}),
          (Option("managed_index", M), Option("pgvector", T, 0.3), Option("local_index", S, 0.3))),
    Point(5, "traces and evals", Layer.EVALUATION, frozenset({D.REGULATION, D.OPERATIONS}),
          (Option("managed_traces", M), Option("self_hosted_traces", T, 0.4), Option("outbox_sync", S, 0.2))),
    Point(6, "keys and perimeter", Layer.GOVERNANCE, frozenset({D.RESIDENCY, D.REGULATION}),
          (Option("provider_keys", M, residency=False), Option("customer_keys", M),
           Option("site_keys", S, 0.2))),
)}


def driven_by(driver: Driver) -> list[int]:
    """Which decisions are reopened when a driver changes."""
    return sorted(n for n, p in POINTS.items() if driver in p.drivers)


@dataclass(frozen=True)
class Site:
    name: str
    air_gapped: bool
    residency: bool
    ops_fte: float               # how much operations the customer can sustain
    stable_volume: bool


class Blueprint(BaseModel):
    model_config = ConfigDict(frozen=True)
    site: Site
    choices: dict[int, str]

    def problems(self) -> list[str]:
        out: list[str] = []
        ops = 0.0
        for n, point in POINTS.items():
            chosen = self.choices.get(n)
            option = next((o for o in point.options if o.name == chosen), None)
            where = f"point {n} ({point.component})"
            if option is None:
                out.append(f"{where}: option {chosen!r} is not in the catalogue")
                continue
            ops += option.ops_fte
            if self.site.air_gapped and option.hosting is not Hosting.ON_SITE:
                out.append(f"{where}: {option.name} requires a cloud connection")
            if self.site.residency and not option.residency:
                out.append(f"{where}: {option.name} does not guarantee residency")
            if option.commitment and not self.site.stable_volume:
                out.append(f"{where}: a capacity commitment without a stable base")
        if ops > self.site.ops_fte:
            out.append(f"operations of {ops:.1f} FTE against {self.site.ops_fte:.1f} available")
        return out

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if problems := self.problems():
            raise ValueError("; ".join(problems))
        return self


def rebind(base: Blueprint, number: int, option: str) -> Blueprint:
    """model_copy skips validation, so the variant is assembled anew."""
    return Blueprint.model_validate({"site": base.site, "choices": base.choices | {number: option}})


if __name__ == "__main__":
    northgate = Site("Northgate", air_gapped=False, residency=True, ops_fte=1.5, stable_volume=False)
    helix = Site("Helix, plant 12", air_gapped=True, residency=True, ops_fte=3.0, stable_volume=True)
    city = Blueprint(site=northgate, choices={1: "managed_runtime", 2: "paygo_regional", 3: "mcp_in_perimeter",
                                              4: "managed_index", 5: "managed_traces", 6: "customer_keys"})
    plant = Blueprint(site=helix, choices={1: "edge_container", 2: "open_weights_edge", 3: "mcp_on_site",
                                           4: "local_index", 5: "outbox_sync", 6: "site_keys"})
    assert set(FIXED) | {p.layer for p in POINTS.values()} == set(Layer)   # no layer is forgotten
    assert driven_by(Driver.RESIDENCY) == [1, 2, 4, 6]        # the question the slide cannot answer
    rejected = [(plant, 1, "managed_runtime", "point 1 (agent loop): managed_runtime requires a cloud"),
                (city, 2, "paygo_global", "does not guarantee residency"),
                (city, 2, "provisioned", "without a stable base"),
                (city, 2, "open_weights", "operations of 2.0 FTE against 1.5 available")]
    for base, number, option, reason in rejected:
        try:
            rebind(base, number, option)
        except ValidationError as err:
            assert reason in str(err), str(err)
        else:
            raise AssertionError(f"{option} at point {number} must be rejected")
    print("two bindings accepted, four rejected with the point named")
