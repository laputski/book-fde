from __future__ import annotations

from dataclasses import dataclass

POINTS_PER_CUSTOMER = 30                 # ширина проблемы важнее одного крупного заказчика
EUR_PER_POINT = 10_000                   # выручка под риском: продления и расширения
HOURS_PER_POINT = 20                     # обход по журналу времени
TOP = 3                                  # в бриф попадают первые три


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    customers: frozenset[str]
    revenue_at_risk_eur: int
    workaround_hours: int
    evidence: tuple[str, ...]            # ссылки на записи реестра паттернов

    def points(self) -> int:
        return (POINTS_PER_CUSTOMER * len(self.customers)
                + self.revenue_at_risk_eur // EUR_PER_POINT
                + self.workaround_hours // HOURS_PER_POINT)


def rank(entries: list[Entry]) -> tuple[list[Entry], list[str]]:
    ranked = [e for e in entries if e.evidence]
    skipped = [f"{e.id}: нет доказательств" for e in entries if not e.evidence]
    ranked.sort(key=lambda e: (-e.points(), -len(e.customers), e.id))   # правило равенства
    return ranked, skipped


def eur(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def brief(entries: list[Entry], quarter: str) -> str:
    ranked, skipped = rank(entries)
    lines = [f"Вход в roadmap от регионального squad, {quarter}",
             f"Решение: взять в квартал {', '.join(e.id for e in ranked[:TOP])}",
             f"Правило: {POINTS_PER_CUSTOMER} баллов за заказчика, 1 за {eur(EUR_PER_POINT)} EUR "
             f"под риском, 1 за {HOURS_PER_POINT} ч обхода; при равенстве больше заказчиков", ""]
    for n, e in enumerate(ranked[:TOP], 1):
        lines += [f"{n}. {e.title} [{e.id}], {e.points()} баллов",
                  f"   {', '.join(sorted(e.customers))}; {eur(e.revenue_at_risk_eur)} EUR; "
                  f"{e.workaround_hours} ч; {', '.join(e.evidence)}"]
    lines += ["", "Ниже черты: " + ", ".join(f"{e.id} ({e.points()})" for e in ranked[TOP:]),
              "Не ранжировано: " + ("; ".join(skipped) or "нет")]
    return "\n".join(lines)


if __name__ == "__main__":
    registry = [
        Entry("approval", "Одобрение, привязанное к аргументам", frozenset({"CF1", "CF4", "CF5"}),
              420_000, 356, ("pattern:approval", "fr:approval-primitive")),
        Entry("residency", "Данные только в регионе", frozenset({"CF1", "CF5"}),
              600_000, 180, ("pattern:residency",)),
        Entry("offline-eval", "Оценка на площадке без сети", frozenset({"CF6"}),
              870_000, 240, ("pattern:offline-eval",)),
        Entry("voice-barge-in", "Перебивание в голосовом канале", frozenset({"CF2"}),
              150_000, 90, ("trace:mh-0311",)),
        Entry("sap-adapter", "Адаптер SAP", frozenset({"CF3"}), 300_000, 400, ()),
    ]
    ranked, skipped = rank(registry)
    assert [e.points() for e in ranked] == [149, 129, 129, 49]
    assert [e.id for e in ranked[:TOP]] == ["approval", "residency", "offline-eval"]
    assert skipped == ["sap-adapter: нет доказательств"]
    text = brief(registry, "Q4 2026")
    assert text.splitlines()[1] == "Решение: взять в квартал approval, residency, offline-eval"
    assert len(text.splitlines()) <= 40                                 # одна страница
    print(text.splitlines()[1], "·", len(text.splitlines()), "строк брифа")
