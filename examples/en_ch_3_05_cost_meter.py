from __future__ import annotations

from dataclasses import dataclass, field

DOCS_PER_DAY = 40_000


@dataclass(frozen=True)
class Price:
    """A tier's price per million tokens, tied to the date it took effect."""

    input_usd: float
    output_usd: float
    cached_input_usd: float


PRICES: dict[tuple[str, str], Price] = {
    ("flash", "2026-02"): Price(0.15, 0.60, 0.0375),
    ("flash", "2026-08"): Price(0.12, 0.50, 0.0300),
    ("pro", "2026-02"): Price(1.25, 5.00, 0.3125),
}


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0


@dataclass(frozen=True)
class Call:
    tier: str
    price_date: str
    usage: Usage
    ttft_s: float
    total_s: float


def cost_usd(call: Call) -> float:
    price = PRICES[(call.tier, call.price_date)]
    fresh = call.usage.input_tokens - call.usage.cached_tokens
    return (fresh * price.input_usd
            + call.usage.cached_tokens * price.cached_input_usd
            + call.usage.output_tokens * price.output_usd) / 1_000_000


def output_tps(call: Call) -> float:
    """Output tokens per second after the first token: the speed of the stream."""
    streaming = max(call.total_s - call.ttft_s, 1e-6)
    return call.usage.output_tokens / streaming


@dataclass
class Meter:
    """The counter of one document: every call its processing required."""

    calls: list[Call] = field(default_factory=list)

    def record(self, call: Call) -> None:
        self.calls.append(call)

    def per_document(self) -> float:
        return sum(cost_usd(c) for c in self.calls)

    def daily_usd(self, docs: int = DOCS_PER_DAY) -> float:
        return self.per_document() * docs


if __name__ == "__main__":
    first = Call("flash", "2026-02", Usage(3_100, 420, 1_800), ttft_s=0.9, total_s=2.3)
    fixed = Call("flash", "2026-02", Usage(3_900, 380, 1_800), ttft_s=0.8, total_s=2.1)
    assert round(output_tps(first), 1) == 300.0
    assert cost_usd(first) < 0.02

    cold = Call("flash", "2026-02", Usage(3_100, 420), ttft_s=1.4, total_s=2.9)
    assert cost_usd(cold) > cost_usd(first) * 1.35      # without the cache the document costs over 35% more

    newer = Call("flash", "2026-08", first.usage, first.ttft_s, first.total_s)
    assert cost_usd(newer) < cost_usd(first)            # the price changed, the code did not

    meter = Meter()
    meter.record(first)
    meter.record(fixed)
    assert meter.per_document() < 0.02
    assert round(meter.daily_usd(), 0) == 45.0
    try:
        cost_usd(Call("pro", "2026-08", first.usage, 0.9, 2.3))
        raise AssertionError("a cost must not be computed without a price record")
    except KeyError:
        pass
    print(f"document with a repair: ${meter.per_document():.6f}, a day: ${meter.daily_usd():.0f}")
