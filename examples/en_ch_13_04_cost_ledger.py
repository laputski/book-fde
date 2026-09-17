from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class Price:
    """Dollars per million tokens from the effective date on."""
    since: date
    input: Decimal
    cache_read: Decimal
    cache_write: Decimal
    output: Decimal


def usd(*values: str) -> tuple[Decimal, ...]:
    return tuple(Decimal(v) for v in values)


PRICES: dict[str, tuple[Price, ...]] = {
    "model-flash": (Price(date(2026, 2, 1), *usd("0.15", "0.0375", "0.1875", "0.60")),
                    Price(date(2026, 8, 1), *usd("0.12", "0.03", "0.15", "0.50"))),
    "model-pro": (Price(date(2026, 2, 1), *usd("1.25", "0.3125", "1.5625", "5.00")),),
}


class UsageEvent(BaseModel):
    """A usage event: emitted when a span with usage closes, and never sampled."""
    model_config = ConfigDict(frozen=True)

    span_id: str
    day: date
    tenant: str = "unattributed"
    feature: str
    user: str
    model: str
    input_tokens: int                 # includes cache_read and cache_write, as in the OTel conventions
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0

    @model_validator(mode="after")
    def cached_within_input(self) -> UsageEvent:
        if self.cache_read_tokens + self.cache_write_tokens > self.input_tokens:
            raise ValueError("more cached tokens than input tokens")
        return self


def price_for(model: str, day: date) -> Price:
    versions = [p for p in PRICES[model] if p.since <= day]
    if not versions:
        raise LookupError(f"no price for {model} on {day}")
    return versions[-1]


def cost(e: UsageEvent) -> Decimal:
    p = price_for(e.model, e.day)
    fresh = e.input_tokens - e.cache_read_tokens - e.cache_write_tokens
    return (fresh * p.input + e.cache_read_tokens * p.cache_read
            + e.cache_write_tokens * p.cache_write + e.output_tokens * p.output) / MILLION


class Ledger:
    def __init__(self) -> None:
        self.rows: dict[str, tuple[UsageEvent, Decimal]] = {}

    def add(self, event: UsageEvent) -> bool:
        """Export delivers at least once: a repeated event does not double the bill."""
        if event.span_id in self.rows:
            return False
        self.rows[event.span_id] = (event, cost(event))
        return True

    def rollup(self, *keys: str) -> dict[tuple[str, ...], Decimal]:
        out: defaultdict[tuple[str, ...], Decimal] = defaultdict(Decimal)
        for event, amount in self.rows.values():
            out[tuple(str(getattr(event, k)) for k in keys)] += amount
        return dict(out)

    def total(self) -> Decimal:
        return sum((amount for _, amount in self.rows.values()), Decimal(0))

    def gap(self, invoice: Decimal) -> Decimal:
        """The relative gap to the provider's invoice for the same period."""
        return abs(self.total() - invoice) / invoice


if __name__ == "__main__":
    aug, jul = date(2026, 8, 14), date(2026, 7, 30)
    hint = UsageEvent(span_id="a1", day=aug, tenant="consumer", feature="agent_assist", user="u-5f2a",
                      model="model-flash", input_tokens=5_000, cache_read_tokens=4_200, output_tokens=60)
    events = [
        hint,
        UsageEvent(span_id="a2", day=aug, tenant="consumer", feature="agent_assist", user="u-5f2a",
                   model="model-flash", input_tokens=13_290, cache_read_tokens=4_200, output_tokens=180),
        UsageEvent(span_id="t1", day=aug, tenant="netops", feature="incident_triage", user="u-duty",
                   model="model-pro", input_tokens=41_000, cache_write_tokens=12_000, output_tokens=900),
        UsageEvent(span_id="e1", day=jul, tenant="enterprise", feature="agent_assist", user="u-9c01",
                   model="model-flash", input_tokens=5_000, cache_read_tokens=4_200, output_tokens=60),
        UsageEvent(span_id="x1", day=aug, feature="agent_assist", user="u-0000",
                   model="model-flash", input_tokens=1_000, output_tokens=100),
    ]
    ledger = Ledger()
    assert all(ledger.add(e) for e in events) and not ledger.add(hint)   # a repeated export is discarded

    assert cost(hint) == Decimal("0.000252")
    assert cost(hint.model_copy(update={"cache_read_tokens": 0})) == Decimal("0.00063")   # 2.5 times dearer without the cache
    assert cost(events[3]) == Decimal("0.0003135")          # the July price list: the same work costs more
    by_tenant = ledger.rollup("tenant")
    assert by_tenant[("consumer",)] == Decimal("0.0015588") and by_tenant[("netops",)] == Decimal("0.0595")
    assert sum(by_tenant.values()) == ledger.total()
    assert ledger.rollup("tenant", "feature", "user")[("consumer", "agent_assist", "u-5f2a")] == Decimal("0.0015588")
    assert by_tenant[("unattributed",)] / ledger.total() < Decimal("0.01")
    assert ledger.gap(invoice=Decimal("0.0619")) < Decimal("0.01")
    try:
        UsageEvent(span_id="bad", day=aug, feature="f", user="u", model="model-flash",
                   input_tokens=100, cache_read_tokens=200)
        raise AssertionError("a cache larger than the input was accepted")
    except ValidationError:
        pass
    try:
        price_for("model-pro", date(2026, 1, 31))
        raise AssertionError("a cost without a price record")
    except LookupError:
        pass
    print(f"cost ledger: {len(ledger.rows)} events, ${ledger.total()} in total, consumer ${by_tenant[('consumer',)]}")
