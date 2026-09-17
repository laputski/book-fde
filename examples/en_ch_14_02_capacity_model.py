from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Q:
    """A number with dimensions: only quantities of one dimension can be added."""
    value: float
    dims: tuple[tuple[str, int], ...] = ()

    def _join(self, other: Q, sign: int) -> tuple[tuple[str, int], ...]:
        acc = dict(self.dims)
        for name, power in other.dims:
            acc[name] = acc.get(name, 0) + sign * power
        return tuple(sorted((n, p) for n, p in acc.items() if p))

    def __add__(self, other: Q) -> Q:
        if self.dims != other.dims:
            raise TypeError(f"cannot add {self.dims} and {other.dims}")
        return Q(self.value + other.value, self.dims)

    def __mul__(self, other: Q | float) -> Q:
        if isinstance(other, Q):
            return Q(self.value * other.value, self._join(other, 1))
        return Q(self.value * other, self.dims)

    def __truediv__(self, other: Q) -> Q:
        return Q(self.value / other.value, self._join(other, -1))


def q(value: float, **dims: int) -> Q:
    return Q(value, tuple(sorted(dims.items())))


DAY, MONTH = q(86_400, s=1), q(30 * 86_400, s=1)
# Load by hour of day in tenths of the mean: a night dip and two shift peaks.
PROFILE = (3, 3, 3, 3, 3, 5, 15, 24, 22, 18, 15, 13, 10, 11, 19, 17, 14, 11, 8, 6, 5, 4, 5, 3)


@dataclass(frozen=True)
class Workload:
    docs_per_day: Q            # doc
    input_per_doc: Q           # tok/doc
    output_per_doc: Q          # tok/doc


@dataclass(frozen=True)
class Tariff:
    """An illustrative price list and throughput conversion, not a vendor's prices."""
    input_usd: Q               # usd/tok
    output_usd: Q              # usd/tok
    output_weight: float       # how many input tokens one output token costs
    per_gsu: Q                 # tok/s per unit of provisioned capacity
    gsu_month_usd: Q           # usd per unit per month


def average_rate(w: Workload, t: Tariff) -> Q:
    per_doc = w.input_per_doc + w.output_per_doc * t.output_weight
    return per_doc * w.docs_per_day / DAY


def units_for(rate: Q, t: Tariff) -> int:
    need = rate / t.per_gsu
    assert need.dims == (("gsu", 1),), need.dims
    return math.ceil(need.value)


def monthly_cost(w: Workload, t: Tariff, units: int) -> Q:
    """A subscription of units plus the spillover above it at the per-token price."""
    capacity = t.per_gsu * q(units, gsu=1)
    load = [average_rate(w, t).value * p / 10 for p in PROFILE]
    spill = sum(max(0.0, x - capacity.value) for x in load) / sum(load)
    per_doc = w.input_per_doc * t.input_usd + w.output_per_doc * t.output_usd
    paygo = per_doc * w.docs_per_day / DAY * MONTH
    return t.gsu_month_usd * q(units, gsu=1) + paygo * spill


if __name__ == "__main__":
    online = Workload(q(48_000, doc=1), q(3_200, tok=1, doc=-1), q(300, tok=1, doc=-1))
    tariff = Tariff(q(0.30e-6, usd=1, tok=-1), q(2.50e-6, usd=1, tok=-1), 4.0,
                    q(700, tok=1, s=-1, gsu=-1), q(560, usd=1, gsu=-1))
    avg = average_rate(online, tariff)
    peak, floor = avg * (max(PROFILE) / 10), avg * (min(PROFILE) / 10)
    assert avg.dims == (("s", -1), ("tok", 1)) and round(avg.value) == 2_444
    assert round((peak * q(60, s=1)).value) == 352_000      # tokens in the peak minute
    try:
        mixed = online.docs_per_day + online.input_per_doc
        raise AssertionError(f"documents were added to tokens: {mixed}")
    except TypeError:
        pass
    plans = {"paygo": 0, "floor": units_for(floor, tariff), "peak": units_for(peak, tariff)}
    cost = {name: monthly_cost(online, tariff, n) for name, n in plans.items()}
    assert plans == {"paygo": 0, "floor": 2, "peak": 9}
    assert all(c.dims == (("usd", 1),) for c in cost.values())
    assert cost["floor"].value < cost["paygo"].value < cost["peak"].value
    assert cost["peak"].value > 2 * cost["paygo"].value      # the peak guarantee outprices the tokens
    print("units:", plans, "dollars a month:", {k: round(c.value) for k, c in cost.items()})
