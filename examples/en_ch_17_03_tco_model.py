from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from itertools import accumulate

HORIZON = 36
FTE_MONTH = Decimal(12_000)          # notional fully loaded cost of one FTE per month, dollars
ZERO = Decimal(0)


@dataclass(frozen=True)
class Scenario:
    """Volume in millions of tokens per month, list price in dollars per million tokens."""
    volume0: Decimal
    growth: Decimal                  # monthly volume multiplier while volume is below the cap
    cap: Decimal
    price0: Decimal
    cuts: tuple[tuple[int, Decimal], ...] = ((13, Decimal("0.85")), (25, Decimal("0.85")))

    def volume(self, month: int) -> Decimal:
        return min(self.cap, self.volume0 * self.growth ** (month - 1))

    def price(self, month: int) -> Decimal:
        factor = Decimal(1)
        for since, cut in self.cuts:
            if month >= since:
                factor *= cut
        return self.price0 * factor


def units(amount: Decimal, size: Decimal, rounding: str) -> int:
    return int((amount / size).to_integral_value(rounding=rounding))


@dataclass(frozen=True)
class Option:
    name: str
    setup: Decimal                   # once, in the first month
    people_fte: Decimal              # operations, evaluation, security reviews
    exit_cost: Decimal               # the cost of leaving at the end of the horizon

    def usage(self, s: Scenario, month: int) -> Decimal:
        raise NotImplementedError

    def monthly(self, s: Scenario, month: int) -> Decimal:
        one_off = self.setup if month == 1 else ZERO
        return one_off + self.usage(s, month) + self.people_fte * FTE_MONTH


@dataclass(frozen=True)
class ManagedApi(Option):
    def usage(self, s: Scenario, month: int) -> Decimal:
        return s.volume(month) * s.price(month)


@dataclass(frozen=True)
class Provisioned(Option):
    block: Decimal = Decimal(5_000)   # millions of tokens per month per capacity block
    min_blocks: int = 3
    rate: Decimal = Decimal("0.6")    # share of the term-start list price paid for a block
    cover: Decimal = Decimal("0.7")   # share of term-start volume under commitment
    term: int = 12

    def usage(self, s: Scenario, month: int) -> Decimal:
        start = month - (month - 1) % self.term          # blocks and price are fixed for the whole term
        blocks = max(self.min_blocks, units(s.volume(start) * self.cover, self.block, ROUND_FLOOR))
        committed = blocks * self.block * s.price(start) * self.rate
        spill = max(ZERO, s.volume(month) - blocks * self.block)
        return committed + spill * s.price(month)


@dataclass(frozen=True)
class SelfHosted(Option):
    node_capacity: Decimal = Decimal(40_000)   # millions of tokens per month per node
    node_month: Decimal = Decimal(8_000)
    min_nodes: int = 2
    peak: Decimal = Decimal("1.6")             # nodes are bought for the peak load

    def usage(self, s: Scenario, month: int) -> Decimal:
        need = units(s.volume(month) * self.peak, self.node_capacity, ROUND_CEILING)
        return max(self.min_nodes, need) * self.node_month


def cumulative(option: Option, s: Scenario) -> list[Decimal]:
    return list(accumulate(option.monthly(s, m) for m in range(1, HORIZON + 1)))


def tco(option: Option, s: Scenario) -> Decimal:
    return cumulative(option, s)[-1] + option.exit_cost


def crossover(a: Option, b: Option, s: Scenario) -> int | None:
    """The first month from which a costs no more than b until the end of the horizon."""
    ca, cb = cumulative(a, s), cumulative(b, s)
    month: int | None = None
    for m in range(HORIZON, 0, -1):
        if ca[m - 1] > cb[m - 1]:
            break
        month = m
    return month


def cheapest(options: list[Option], s: Scenario, month: int) -> str:
    return min((cumulative(o, s)[month - 1], o.name) for o in options)[1]


if __name__ == "__main__":
    api = ManagedApi("managed_api", ZERO, Decimal("0.5"), Decimal(60_000))
    prov = Provisioned("provisioned", Decimal(40_000), Decimal("0.7"), Decimal(60_000))
    own = SelfHosted("self_hosted", Decimal(300_000), Decimal("2.5"), Decimal(150_000))
    options: list[Option] = [api, prov, own]
    base = Scenario(Decimal(8_000), Decimal("1.12"), Decimal(50_000), Decimal("2.00"))
    assert [cheapest(options, base, m) for m in (6, 18, 34)] == ["managed_api", "provisioned", "self_hosted"]
    assert crossover(prov, api, base) == 10 and crossover(own, prov, base) == 32
    assert tco(prov, base) < tco(own, base)            # with the exit cost the commitment is cheaper again

    scenarios = [replace(base, growth=Decimal("1.08"), cap=Decimal(35_000)), base,
                 replace(base, growth=Decimal("1.15"), cap=Decimal(60_000), cuts=())]
    ranges = {o.name: (min(tco(o, s) for s in scenarios), max(tco(o, s) for s in scenarios))
              for o in options}
    (p_lo, p_hi), (s_lo, s_hi) = ranges["provisioned"], ranges["self_hosted"]
    assert p_lo < s_lo < s_hi < p_hi                   # own serving barely depends on volume and price

    falling = replace(base, cuts=((13, Decimal("0.6")), (25, Decimal("0.6"))))
    assert crossover(own, prov, falling) is None       # with fast price cuts own serving never pays back
    sharp = replace(base, cuts=((7, Decimal("0.5")),))
    assert all(prov.monthly(sharp, m) > api.monthly(sharp, m) for m in range(7, 13))
    print("36-month TCO, thousand dollars:",
          {n: f"{lo / 1000:,.0f}–{hi / 1000:,.0f}" for n, (lo, hi) in ranges.items()})
