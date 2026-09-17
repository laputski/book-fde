from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

N = 6                                   # длина n-граммы в словах
FLAG_AT = 0.5                           # доля совпавших n-грамм примера


def ngrams(text: str, n: int = N) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", text.lower())
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


@dataclass(frozen=True)
class EvalItem:
    id: str
    question: str
    reference: str


@dataclass
class Split:
    kept: list[str] = field(default_factory=list)
    excluded: dict[str, str] = field(default_factory=dict)      # id -> источник совпадения


def check(items: Sequence[EvalItem], sources: Mapping[str, str]) -> Split:
    index: dict[tuple[str, ...], set[str]] = {}
    for name, text in sources.items():
        for gram in ngrams(text):
            index.setdefault(gram, set()).add(name)
    split = Split()
    for item in items:
        grams = ngrams(f"{item.question} {item.reference}")
        hits: dict[str, int] = {}
        for gram in grams:
            for name in index.get(gram, ()):
                hits[name] = hits.get(name, 0) + 1
        worst = max(hits.items(), key=lambda kv: (kv[1], kv[0]), default=("", 0))
        if grams and worst[1] / len(grams) >= FLAG_AT:
            split.excluded[item.id] = worst[0]
        else:
            split.kept.append(item.id)
    return split


if __name__ == "__main__":
    items = [
        EvalItem("e1", "Сколько банк рассматривает спорную операцию по карте?",
                 "Спорная операция по карте рассматривается не дольше 45 дней с даты обращения."),
        EvalItem("e2", "Можно ли снять блокировку карты без визита в отделение?",
                 "Да, блокировку снимает оператор после проверки личности по кодовому слову."),
        EvalItem("e3", "Какой лимит оплаты без PIN?", "Без PIN можно оплатить покупку до 50 евро."),
    ]
    sources = {
        "prompt:few-shot-3": ("Пример. Вопрос: сколько банк рассматривает спорную операцию по карте? "
                              "Ответ: спорная операция по карте рассматривается не дольше 45 дней "
                              "с даты обращения."),
        "kb:incident-0412": ("Разбор инцидента. Можно ли снять блокировку карты без визита в "
                             "отделение? Да, блокировку снимает оператор после проверки личности "
                             "по кодовому слову."),
        "kb:cards-tariff": ("Бесконтактная оплата без ввода PIN допускается для покупок "
                            "на сумму до 50 евро включительно."),
    }
    split = check(items, sources)
    assert split.excluded == {"e1": "prompt:few-shot-3", "e2": "kb:incident-0412"}
    assert split.kept == ["e3"]                 # общий факт в тарифе не является утечкой
    print("исключены из прогона:", split.excluded)
