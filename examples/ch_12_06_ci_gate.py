from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

REGRESSION, NON_INFERIOR, INCONCLUSIVE = "regression", "non_inferior", "inconclusive"


@dataclass(frozen=True)
class Interval:
    mean: float
    lo: float
    hi: float


def bootstrap(diffs: Sequence[float], seed: int, rounds: int = 1000,
              level: float = 0.95) -> Interval:
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(rounds))
    tail = (1 - level) / 2
    lo, hi = means[int(tail * rounds)], means[int((1 - tail) * rounds) - 1]
    return Interval(sum(diffs) / n, lo, hi)


@dataclass(frozen=True)
class Decision:
    metric: str
    interval: Interval
    verdict: str

    @property
    def blocks(self) -> bool:
        return self.verdict == REGRESSION


def compare(metric: str, base: Mapping[str, float], cand: Mapping[str, float],
            tolerated_drop: float, excluded: frozenset[str] = frozenset(),
            seed: int = 12) -> Decision:
    if base.keys() != cand.keys():
        raise ValueError("прогоны на разных примерах: парное сравнение невозможно")
    ids = sorted(base.keys() - excluded)
    ci = bootstrap([cand[i] - base[i] for i in ids], seed)
    if ci.hi < -tolerated_drop:
        verdict = REGRESSION                # весь интервал хуже допустимого падения
    elif ci.lo >= -tolerated_drop:
        verdict = NON_INFERIOR
    else:
        verdict = INCONCLUSIVE              # данных недостаточно, чтобы решить
    return Decision(metric, ci, verdict)


def gate(decisions: Sequence[Decision]) -> tuple[bool, list[str]]:
    reasons = [f"{d.metric}: {d.interval.mean:+.3f} "
               f"[{d.interval.lo:+.3f}; {d.interval.hi:+.3f}]" for d in decisions if d.blocks]
    return not reasons, reasons


if __name__ == "__main__":
    ids = [f"e{i:04d}" for i in range(1200)]
    base = {i: 1.0 if k < 1080 else 0.0 for k, i in enumerate(ids)}    # 90 % обоснованных
    cand = dict(base)
    for i in ids[:48]:
        cand[i] = 0.0                       # 48 ответов ухудшились
    for i in ids[1080:1104]:
        cand[i] = 1.0                       # 24 ответа улучшились: итог минус 2 п. п.

    strict = compare("grounded", base, cand, tolerated_drop=0.0)
    lenient = compare("grounded", base, cand, tolerated_drop=0.01)
    assert round(strict.interval.mean, 3) == -0.02
    assert strict.blocks and lenient.verdict == INCONCLUSIVE and not lenient.blocks

    rng = random.Random(7)                  # непарное сравнение тех же данных
    b, c = list(base.values()), list(cand.values())
    unpaired = sorted(sum(rng.choices(c, k=1200)) / 1200 - sum(rng.choices(b, k=1200)) / 1200
                      for _ in range(1000))
    assert unpaired[24] < -0.03 and unpaired[974] > 0.0     # интервал накрывает ноль

    ok, reasons = gate([strict, compare("policy", base, base, tolerated_drop=0.0)])
    assert not ok and reasons[0].startswith("grounded")
    try:
        compare("grounded", base, {i: cand[i] for i in ids[:1100]}, tolerated_drop=0.0)
        raise AssertionError("прогоны на разных наборах не сравниваются")
    except ValueError:
        pass
    print("выкладка заблокирована:", reasons[0])
