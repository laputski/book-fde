from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def ramp(values: str) -> tuple[Decimal, ...]:
    return tuple(Decimal(v) for v in values.split())


@dataclass(frozen=True)
class Baseline:
    """Измерено в discovery до любых изменений; размер выборки входит в базу."""
    sample_orders: int = 212
    diagnoses_per_month: int = 9_000
    minutes_per_diagnosis: Decimal = Decimal(38)
    loaded_cost_per_hour: Decimal = Decimal(58)
    counterfactual_drift: Decimal = Decimal("0.04")    # улучшение, которое случится и без системы


@dataclass(frozen=True)
class Scenario:
    name: str
    time_reduction: Decimal           # доля времени диагностики, которую снимает ассистент
    adoption: tuple[Decimal, ...]     # охват по месяцам; последнее значение держится дальше
    run_cost_month: Decimal
    build_cost: Decimal = Decimal(370_000)


def cash_flows(base: Baseline, s: Scenario, horizon: int = 24) -> list[Decimal]:
    if base.sample_orders < 200:
        raise ValueError("базовая линия не измерена: бизнес-кейс не считается")
    counterfactual = base.minutes_per_diagnosis * (1 - base.counterfactual_drift)
    flows = [-s.build_cost]
    for month in range(1, horizon + 1):
        adoption = s.adoption[min(month, len(s.adoption)) - 1]
        saved_hours = base.diagnoses_per_month * counterfactual * s.time_reduction * adoption / 60
        flows.append(saved_hours * base.loaded_cost_per_hour - s.run_cost_month)
    return flows


def payback_month(flows: list[Decimal]) -> int | None:
    total = Decimal(0)
    for month, flow in enumerate(flows):
        total += flow
        if month and total >= 0:
            return month
    return None


def npv(flows: list[Decimal], monthly_rate: Decimal = Decimal("0.008")) -> Decimal:
    value = sum((f / (1 + monthly_rate) ** m for m, f in enumerate(flows)), Decimal(0))
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def adoption_sensitivity(base: Baseline, s: Scenario) -> dict[str, tuple[Decimal, int | None]]:
    out: dict[str, tuple[Decimal, int | None]] = {}
    for factor in ("0.5", "0.75", "1"):
        scaled = replace(s, adoption=tuple(a * Decimal(factor) for a in s.adoption))
        flows = cash_flows(base, scaled)
        out[factor] = (npv(flows), payback_month(flows))
    return out


SCENARIOS = (
    Scenario("низкий", Decimal("0.15"), ramp("0.1 0.3 0.5 0.6"), Decimal(22_000)),
    Scenario("ожидаемый", Decimal("0.25"), ramp("0.2 0.5 0.75 0.9"), Decimal(21_000)),
    Scenario("высокий", Decimal("0.35"), ramp("0.3 0.6 0.9 1"), Decimal(19_000)),
)

if __name__ == "__main__":
    base = Baseline()
    low, expected, high = (cash_flows(base, s) for s in SCENARIOS)
    assert [payback_month(f) for f in (low, expected, high)] == [None, 10, 6]
    assert npv(expected) == Decimal("628845.79") and npv(low) < 0 < npv(high)
    assert expected[12] == Decimal("50409.60")          # месяц на полном охвате, до цента
    by_adoption = adoption_sensitivity(base, SCENARIOS[1])
    assert by_adoption["0.75"] == (Decimal("264905.88"), 14)
    assert by_adoption["0.5"][0] < 0 and by_adoption["0.5"][1] is None
    try:
        cash_flows(replace(base, sample_orders=30), SCENARIOS[1])
        raise AssertionError("бизнес-кейс без измеренной базы посчитан")
    except ValueError:
        pass
    print("окупаемость: низкий нет, ожидаемый 10, высокий 6 мес.; NPV при охвате 50 %:", by_adoption["0.5"][0])
