from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace

MAX_QUALITY_DROP = 0.02                  # абсолютная доля задач
MAX_GROWTH = 0.10                        # относительный рост p95 и стоимости


@dataclass(frozen=True)
class Task:
    id: str
    steps: int                           # сколько шагов рассуждения требует задача
    needs_citation: bool


@dataclass(frozen=True)
class Config:
    engagement: str
    model: str
    reach: int                           # до какого числа шагов модель справляется
    top_k: int
    eur_per_1k_tokens: float


@dataclass(frozen=True)
class Run:
    correct: bool
    latency_ms: int
    tokens: int


@dataclass(frozen=True)
class Row:
    engagement: str
    quality: float
    p95_ms: int
    cost_eur: float
    regressions: tuple[str, ...] = ()


def fake_system(cfg: Config, task: Task) -> Run:
    """Детерминированная замена системы engagement: механизм вместо случайности."""
    grounded = cfg.top_k >= 3 or not task.needs_citation
    tokens = 500 + 300 * cfg.top_k + 150 * task.steps
    latency = 200 + 60 * cfg.top_k + (350 if cfg.model == "model-pro" else 120) * task.steps
    return Run(task.steps <= cfg.reach and grounded, latency, tokens)


def p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]     # метод ближайшего ранга


def benchmark(tasks: list[Task], configs: list[Config], system: Callable[[Config, Task], Run],
              baseline: dict[str, Row] | None = None) -> list[Row]:
    rows = []
    for cfg in configs:
        runs = [system(cfg, t) for t in tasks]
        row = Row(cfg.engagement, round(sum(r.correct for r in runs) / len(runs), 3),
                  p95([r.latency_ms for r in runs]),
                  round(sum(r.tokens for r in runs) / 1000 * cfg.eur_per_1k_tokens, 2))
        old = (baseline or {}).get(cfg.engagement)
        if old is not None:
            checks = ((old.quality - row.quality > MAX_QUALITY_DROP,
                       f"качество {old.quality:.2f} → {row.quality:.2f}"),
                      (row.p95_ms > old.p95_ms * (1 + MAX_GROWTH),
                       f"p95 {old.p95_ms} → {row.p95_ms} мс"),
                      (row.cost_eur > old.cost_eur * (1 + MAX_GROWTH),
                       f"стоимость {old.cost_eur} → {row.cost_eur} EUR"))
            row = replace(row, regressions=tuple(text for failed, text in checks if failed))
        rows.append(row)
    return rows


if __name__ == "__main__":
    tasks = [Task(f"t{i:02d}", steps=1 + i % 4, needs_citation=i % 2 == 0) for i in range(40)]
    v24 = [Config("CF1", "model-pro", reach=4, top_k=5, eur_per_1k_tokens=0.012),
           Config("CF4", "model-flash", reach=3, top_k=3, eur_per_1k_tokens=0.003),
           Config("CF5", "model-pro", reach=4, top_k=4, eur_per_1k_tokens=0.012)]
    baseline = {row.engagement: row for row in benchmark(tasks, v24, fake_system)}
    assert baseline["CF1"].quality == 1.0 and baseline["CF4"].quality == 0.75

    # модуль v2.5 снижает top_k по умолчанию до 2; CF1 закрепил своё значение
    v25 = [c if c.engagement == "CF1" else replace(c, top_k=2) for c in v24]
    report = {row.engagement: row for row in benchmark(tasks, v25, fake_system, baseline)}
    assert report["CF1"].regressions == ()
    assert report["CF4"].regressions == ("качество 0.75 → 0.25",)
    assert report["CF5"].regressions == ("качество 1.00 → 0.50",)
    assert report["CF4"].cost_eur < baseline["CF4"].cost_eur          # дешевле, но хуже
    print("модуль v2.5:", {e: list(r.regressions) or "без регрессий" for e, r in report.items()})
