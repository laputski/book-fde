from __future__ import annotations

from dataclasses import dataclass, field

MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR


@dataclass
class ManualClock:
    t: float = 0.0

    def now(self) -> float:
        return self.t


@dataclass(frozen=True)
class Rule:
    long_s: int
    short_s: int
    burn: float
    severity: str


RULES = (
    Rule(1 * HOUR, 5 * MINUTE, 14.4, "page"),       # 2 % месячного бюджета за час
    Rule(6 * HOUR, 30 * MINUTE, 6.0, "page"),       # 5 % за шесть часов
    Rule(3 * DAY, 6 * HOUR, 1.0, "ticket"),         # 10 % за трое суток
)


@dataclass
class BurnRateAlerts:
    clock: ManualClock
    objective: float                                 # доля успешных запусков за 30 дней
    rules: tuple[Rule, ...] = RULES
    minutes: dict[int, tuple[int, int]] = field(default_factory=dict)   # минута: (всего, неудачных)

    def record(self, total: int, bad: int) -> None:
        m = int(self.clock.now() // MINUTE)
        seen, failed = self.minutes.get(m, (0, 0))
        self.minutes[m] = (seen + total, failed + bad)

    def error_ratio(self, window_s: int) -> float:
        now = int(self.clock.now() // MINUTE)
        cells = [self.minutes.get(m, (0, 0)) for m in range(now - window_s // MINUTE + 1, now + 1)]
        total = sum(t for t, _ in cells)
        return sum(b for _, b in cells) / total if total else 0.0

    def burn_rate(self, window_s: int) -> float:
        """1.0 означает, что бюджет кончится ровно к концу 30-дневного окна."""
        return self.error_ratio(window_s) / (1 - self.objective)

    def firing(self) -> list[str]:
        return [r.severity for r in self.rules
                if self.burn_rate(r.long_s) >= r.burn and self.burn_rate(r.short_s) >= r.burn]


def run(alerts: BurnRateAlerts, minutes: int, per_minute: int, bad_share: float) -> None:
    for _ in range(minutes):
        alerts.clock.t += MINUTE
        alerts.record(per_minute, round(per_minute * bad_share))


if __name__ == "__main__":
    day = BurnRateAlerts(ManualClock(), objective=0.99)
    run(day, 6 * 60, per_minute=500, bad_share=0.002)
    assert day.firing() == []                                  # фон: 0.2 % отказов, бюджет почти цел

    detected = 0
    while "page" not in day.firing():                          # MCP-сервер биллинга недоступен: все запуски завершаются ошибкой
        run(day, 1, per_minute=500, bad_share=1.0)
        detected += 1
    assert detected == 9 and day.firing() == ["page", "ticket"]
    run(day, 3, per_minute=500, bad_share=1.0)
    run(day, 6, per_minute=500, bad_share=0.002)               # сбой устранён
    assert day.firing() == ["ticket"] and day.burn_rate(HOUR) > 14.4   # вызов снят, тикет остался

    slow = BurnRateAlerts(ManualClock(), objective=0.99)
    run(slow, 3 * 24 * 60, per_minute=300, bad_share=0.015)   # тихая деградация после смены промпта
    assert slow.firing() == ["ticket"]

    night = BurnRateAlerts(ManualClock(), objective=0.99)
    run(night, 60, per_minute=2, bad_share=0.0)
    night.record(1, 1)                                         # одна неудача из одиннадцати за 5 минут
    assert night.error_ratio(5 * MINUTE) > 0.05                # порог «5 % за 5 минут» разбудил бы дежурного
    assert night.firing() == []                                # правило по бюджету не срабатывает
    print(f"сбой: вызов на {detected}-й минуте; деградация: тикет; ночной шум: тишина")
