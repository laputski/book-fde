from __future__ import annotations

from dataclasses import dataclass

FAST_LANGUAGES = frozenset({"de", "en", "nl", "pl"})   # латиница, короткие формы
TIERS = ("batch", "flash", "pro")


@dataclass(frozen=True)
class Shipment:
    doc_id: str
    pages: int
    language: str
    ocr_confidence: float      # 0..1, уверенность распознавания страницы
    deadline_s: float          # сколько времени есть у документа
    attempt: int = 1


def route(doc: Shipment) -> str:
    """Детерминированный выбор уровня: одинаковый вход даёт одинаковый уровень."""
    if doc.attempt > 1:
        return "pro"           # повтор уходит на старший уровень
    if doc.deadline_s > 3_600:
        return "batch"         # ночная партия платит меньше за ту же работу
    if doc.pages > 4 or doc.ocr_confidence < 0.75:
        return "pro"
    if doc.language not in FAST_LANGUAGES:
        return "pro"
    return "flash"


def mix(docs: list[Shipment]) -> dict[str, float]:
    """Доли уровней на корпусе: из них считается стоимость суток."""
    counts: dict[str, int] = dict.fromkeys(TIERS, 0)
    for doc in docs:
        counts[route(doc)] += 1
    return {tier: round(n / len(docs), 3) for tier, n in counts.items()}


if __name__ == "__main__":
    corpus = [
        Shipment("d1", 2, "de", 0.95, 8.0),
        Shipment("d2", 2, "pl", 0.92, 8.0),
        Shipment("d3", 6, "de", 0.95, 8.0),
        Shipment("d4", 2, "zh", 0.90, 8.0),
        Shipment("d5", 3, "en", 0.60, 8.0),
        Shipment("d6", 1, "nl", 0.99, 7_200.0),
        Shipment("d7", 2, "de", 0.95, 8.0, attempt=2),
        Shipment("d8", 3, "en", 0.88, 8.0),
    ]
    assert route(corpus[0]) == "flash" and route(corpus[7]) == "flash"
    assert route(corpus[2]) == "pro"        # шесть страниц
    assert route(corpus[3]) == "pro"        # язык вне быстрого набора
    assert route(corpus[4]) == "pro"        # плохое распознавание
    assert route(corpus[5]) == "batch"      # результат нужен через два часа
    assert route(corpus[6]) == "pro"        # повтор дороже, но точнее
    assert route(corpus[0]) == route(corpus[0])
    shares = mix(corpus)
    assert shares == {"batch": 0.125, "flash": 0.375, "pro": 0.5}
    print("доли уровней на корпусе:", shares)
