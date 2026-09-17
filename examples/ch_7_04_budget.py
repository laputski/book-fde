from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


class BudgetExceeded(Exception):
    """Общий предок: цикл обязан прекратить работу и объяснить причину."""

    resource = "бюджет"


class StepsExceeded(BudgetExceeded):
    resource = "шаги"


class TokensExceeded(BudgetExceeded):
    resource = "токены"


class TimeExceeded(BudgetExceeded):
    resource = "время"


class SideEffectsExceeded(BudgetExceeded):
    resource = "побочные эффекты"


@dataclass
class Budget:
    """Четыре бюджета одного расследования, проверяемые перед каждым переходом."""

    now: Callable[[], float]
    max_steps: int = 8
    max_tokens: int = 60_000
    max_seconds: float = 25.0
    max_side_effects: int = 1
    steps: int = 0
    tokens: int = 0
    side_effects: int = 0
    started_at: float = field(default=0.0)

    def __post_init__(self) -> None:
        self.started_at = self.now()

    def charge_step(self, tokens: int = 0) -> None:
        self.steps += 1
        self.tokens += tokens
        if self.steps > self.max_steps:
            raise StepsExceeded(f"{self.steps} шагов при потолке {self.max_steps}")
        if self.tokens > self.max_tokens:
            raise TokensExceeded(f"{self.tokens} токенов при потолке {self.max_tokens}")
        self.check_time()

    def charge_side_effect(self) -> None:
        self.side_effects += 1
        if self.side_effects > self.max_side_effects:
            raise SideEffectsExceeded(f"{self.side_effects} действий записи")

    def check_time(self) -> None:
        if self.now() - self.started_at > self.max_seconds:
            raise TimeExceeded(f"{self.now() - self.started_at:.1f} с при потолке {self.max_seconds}")

    def pressure(self) -> float:
        """Доля самого исчерпанного из бюджетов: 0.0 в начале, 1.0 на пределе."""
        return max(self.steps / self.max_steps, self.tokens / self.max_tokens,
                   (self.now() - self.started_at) / self.max_seconds,
                   self.side_effects / self.max_side_effects)


if __name__ == "__main__":
    clock = {"t": 100.0}
    budget = Budget(now=lambda: clock["t"], max_steps=4, max_tokens=10_000, max_seconds=20.0)

    budget.charge_step(tokens=3_000)
    clock["t"] += 6.0
    budget.charge_step(tokens=3_000)
    assert round(budget.pressure(), 2) == 0.6          # токены израсходованы быстрее шагов

    budget.charge_side_effect()
    try:
        budget.charge_side_effect()
        raise AssertionError("второе действие записи обязано быть отвергнуто")
    except SideEffectsExceeded as err:
        assert err.resource == "побочные эффекты"

    clock["t"] += 15.0
    try:
        budget.charge_step(tokens=10)
        raise AssertionError("исчерпанное время обязано остановить шаг")
    except TimeExceeded:
        pass

    strict = Budget(now=lambda: clock["t"], max_steps=1)
    strict.charge_step()
    try:
        strict.charge_step()
        raise AssertionError("второй шаг за потолком в один шаг")
    except StepsExceeded as err:
        assert isinstance(err, BudgetExceeded)
    print("четыре бюджета, типизированные исключения и давление как сигнал завершать разбор")
