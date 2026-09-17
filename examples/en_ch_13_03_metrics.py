from __future__ import annotations

import bisect
import functools
import random
from dataclasses import dataclass, field

SECONDS = (0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92)
TOKENS_PER_S = (5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 320.0, 640.0)
STEPS = (1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0)
LABELS = frozenset({"tenant", "feature", "model"})     # bounded cardinality: no user, no request_id


@dataclass
class Histogram:
    bounds: tuple[float, ...]
    counts: list[int] = field(default_factory=list)
    total: float = 0.0
    n: int = 0

    def __post_init__(self) -> None:
        self.counts = self.counts or [0] * (len(self.bounds) + 1)   # the last bucket: above the bounds

    def record(self, value: float) -> None:
        self.counts[bisect.bisect_left(self.bounds, value)] += 1
        self.total += value
        self.n += 1

    def merge(self, other: Histogram) -> Histogram:
        if other.bounds != self.bounds:
            raise ValueError("only histograms with identical bounds can be merged")
        counts = [a + b for a, b in zip(self.counts, other.counts, strict=True)]
        return Histogram(self.bounds, counts, self.total + other.total, self.n + other.n)

    def mean(self) -> float:
        return self.total / self.n

    def quantile(self, q: float) -> float:
        """Interpolation inside the bucket: the accuracy is bounded by its width."""
        rank, seen = q * self.n, 0
        for i, c in enumerate(self.counts):
            if c and seen + c >= rank:
                if i == len(self.bounds):
                    return self.bounds[-1]
                low = self.bounds[i - 1] if i else 0.0
                return low + (self.bounds[i] - low) * (rank - seen) / c
            seen += c
        return self.bounds[-1]


@dataclass
class Metrics:
    series: dict[tuple[str, tuple[tuple[str, str], ...]], Histogram] = field(default_factory=dict)

    def observe(self, name: str, bounds: tuple[float, ...], value: float, **labels: str) -> None:
        if extra := set(labels) - LABELS:
            raise ValueError(f"label of unbounded cardinality: {sorted(extra)}")
        key = (name, tuple(sorted(labels.items())))
        if key not in self.series:
            self.series[key] = Histogram(bounds)
        self.series[key].record(value)

    def query(self, name: str, **match: str) -> Histogram:
        found = [h for (n, labels), h in self.series.items()
                 if n == name and match.items() <= dict(labels).items()]
        return functools.reduce(Histogram.merge, found)


def record_call(m: Metrics, *, stream: bool, ttft_s: float, total_s: float, output_tokens: int,
                **labels: str) -> None:
    m.observe("gen_ai.client.operation.duration", SECONDS, total_s, **labels)
    if stream:                                         # no stream: neither a first token nor a speed
        m.observe("orion.ttft", SECONDS, ttft_s, **labels)
        m.observe("orion.output_tokens_per_s", TOKENS_PER_S, output_tokens / (total_s - ttft_s), **labels)


if __name__ == "__main__":
    rng = random.Random(13)
    pods = {"pod-a": Metrics(), "pod-b": Metrics()}
    raw: list[float] = []
    for pod, calls, slow_share in (("pod-a", 1_500, 0.08), ("pod-b", 500, 0.0)):
        for _ in range(calls):
            ttft = rng.uniform(3.0, 5.0) if rng.random() < slow_share else rng.uniform(0.4, 0.9)
            raw.append(ttft)
            record_call(pods[pod], stream=True, ttft_s=ttft, total_s=ttft + 1.4, output_tokens=400,
                        tenant="consumer", feature="agent_assist", model="model-flash")
    record_call(pods["pod-b"], stream=False, ttft_s=0.0, total_s=38.0, output_tokens=9_000,
                tenant="netops", feature="incident_triage", model="model-pro")

    a, b = (pods[p].query("orion.ttft", tenant="consumer") for p in ("pod-a", "pod-b"))
    fleet = a.merge(b)
    exact_p95 = sorted(raw)[int(0.95 * len(raw))]
    assert fleet.mean() < 1.0 < 2.56 < fleet.quantile(0.95)        # the mean is below a second, p95 above 2.56
    assert 2.56 < exact_p95 <= 5.12                                 # the same bucket as the estimate
    assert fleet.quantile(0.95) - (a.quantile(0.95) + b.quantile(0.95)) / 2 > 0.5    # p95 values are not averaged
    tps = pods["pod-a"].query("orion.output_tokens_per_s")
    assert tps.n == 1_500 and 160 < tps.quantile(0.5) <= 320
    assert pods["pod-b"].query("gen_ai.client.operation.duration", tenant="netops").n == 1

    runs = Metrics()
    for steps in (2, 2, 3, 2, 4, 2, 9, 2, 3, 2, 2, 17):
        runs.observe("orion.agent.steps", STEPS, steps, feature="incident_triage")
    per_run = runs.query("orion.agent.steps")
    assert per_run.quantile(0.5) <= 2 and per_run.quantile(0.95) > 8     # a median of two steps, a tail of loops
    try:
        runs.observe("orion.agent.steps", STEPS, 3, user="u-5f2a")
        raise AssertionError("a user label was accepted")
    except ValueError:
        pass
    print(f"TTFT: mean {fleet.mean():.2f} s, p95 {fleet.quantile(0.95):.2f} s, exact p95 {exact_p95:.2f} s")
