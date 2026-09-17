from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


class BudgetExceeded(Exception):
    """The common ancestor: the loop must stop working and explain why."""

    resource = "budget"


class StepsExceeded(BudgetExceeded):
    resource = "steps"


class TokensExceeded(BudgetExceeded):
    resource = "tokens"


class TimeExceeded(BudgetExceeded):
    resource = "time"


class SideEffectsExceeded(BudgetExceeded):
    resource = "side effects"


@dataclass
class Budget:
    """The four budgets of one investigation, checked before every transition."""

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
            raise StepsExceeded(f"{self.steps} steps against a ceiling of {self.max_steps}")
        if self.tokens > self.max_tokens:
            raise TokensExceeded(f"{self.tokens} tokens against a ceiling of {self.max_tokens}")
        self.check_time()

    def charge_side_effect(self) -> None:
        self.side_effects += 1
        if self.side_effects > self.max_side_effects:
            raise SideEffectsExceeded(f"{self.side_effects} write actions")

    def check_time(self) -> None:
        if self.now() - self.started_at > self.max_seconds:
            raise TimeExceeded(f"{self.now() - self.started_at:.1f} s against a ceiling of {self.max_seconds}")

    def pressure(self) -> float:
        """The share of the most exhausted budget: 0.0 at the start, 1.0 at the limit."""
        return max(self.steps / self.max_steps, self.tokens / self.max_tokens,
                   (self.now() - self.started_at) / self.max_seconds,
                   self.side_effects / self.max_side_effects)


if __name__ == "__main__":
    clock = {"t": 100.0}
    budget = Budget(now=lambda: clock["t"], max_steps=4, max_tokens=10_000, max_seconds=20.0)

    budget.charge_step(tokens=3_000)
    clock["t"] += 6.0
    budget.charge_step(tokens=3_000)
    assert round(budget.pressure(), 2) == 0.6          # tokens are spent faster than steps

    budget.charge_side_effect()
    try:
        budget.charge_side_effect()
        raise AssertionError("a second write action must be rejected")
    except SideEffectsExceeded as err:
        assert err.resource == "side effects"

    clock["t"] += 15.0
    try:
        budget.charge_step(tokens=10)
        raise AssertionError("exhausted time must stop the step")
    except TimeExceeded:
        pass

    strict = Budget(now=lambda: clock["t"], max_steps=1)
    strict.charge_step()
    try:
        strict.charge_step()
        raise AssertionError("a second step beyond a ceiling of one step")
    except StepsExceeded as err:
        assert isinstance(err, BudgetExceeded)
    print("four budgets, typed exceptions and pressure as a signal to conclude")
