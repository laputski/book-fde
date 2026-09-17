from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Baseline:
    """Измерено до пилота: источник каждого числа назван."""
    agents: int = 400
    calls_per_agent_day: int = 38
    aht_s: float = 372.0                 # средняя длительность обработки
    loaded_cost_per_hour: float = 31.0   # полная стоимость часа оператора
    working_days: int = 21

    @property
    def calls_per_month(self) -> int:
        return self.agents * self.calls_per_agent_day * self.working_days

    @property
    def cost_per_call(self) -> float:
        return self.aht_s / 3600.0 * self.loaded_cost_per_hour


@dataclass(frozen=True)
class Hypothesis:
    aht_reduction: float = 0.12          # доля, на которую падает длительность
    deflection: float = 0.05             # доля повторных обращений, которых удалось избежать
    cost_per_request: float = 0.014      # модель, retrieval, инфраструктура
    build_cost: float = 240_000.0
    run_cost_month: float = 11_000.0
    ramp: tuple[float, ...] = (0.15, 0.40, 0.70, 1.0)   # охват по месяцам


def net_month(base: Baseline, hyp: Hypothesis, month: int) -> float:
    adoption = hyp.ramp[min(month, len(hyp.ramp)) - 1]
    covered = base.calls_per_month * adoption
    deflected = covered * hyp.deflection
    handled = covered - deflected
    saved = deflected * base.cost_per_call + handled * base.cost_per_call * hyp.aht_reduction
    spent = covered * hyp.cost_per_request + hyp.run_cost_month
    return saved - spent


def break_even(base: Baseline, hyp: Hypothesis, horizon: int = 24) -> int | None:
    cumulative = -hyp.build_cost
    for month in range(1, horizon + 1):
        cumulative += net_month(base, hyp, month)
        if cumulative >= 0:
            return month
    return None


def sensitivity(base: Baseline, hyp: Hypothesis, factor: float) -> dict[str, int | None]:
    """Что станет с окупаемостью, если каждое допущение окажется слабее в factor раз."""
    return {
        "aht_reduction": break_even(base, replace(hyp, aht_reduction=hyp.aht_reduction * factor)),
        "deflection": break_even(base, replace(hyp, deflection=hyp.deflection * factor)),
        "run_cost_month": break_even(base, replace(hyp, run_cost_month=hyp.run_cost_month / factor)),
    }


if __name__ == "__main__":
    base, hyp = Baseline(), Hypothesis()
    assert base.calls_per_month == 319_200
    assert round(base.cost_per_call, 4) == 3.2033
    assert break_even(base, hyp) == 4
    weak = sensitivity(base, hyp, factor=0.5)
    assert weak["aht_reduction"] == 5 and weak["deflection"] == 4
    assert break_even(base, replace(hyp, aht_reduction=0.0, deflection=0.0)) is None
    print("окупаемость на месяце", break_even(base, hyp), "· при половинных допущениях", weak)
