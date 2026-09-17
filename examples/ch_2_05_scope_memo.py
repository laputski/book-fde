from __future__ import annotations

from dataclasses import dataclass

WORD_LIMIT = 320          # одна страница, которую спонсор прочитает целиком


@dataclass(frozen=True)
class Metric:
    name: str
    baseline: str         # измеренное значение до пилота
    target: str           # порог приёмки
    dataset: str          # на чём измеряем, чтобы результат был воспроизводим

    def line(self) -> str:
        return f"{self.name}: {self.baseline} → {self.target}; набор: {self.dataset}"


@dataclass(frozen=True)
class Memo:
    customer: str
    decision: str
    in_scope: tuple[str, ...]
    out_of_scope: tuple[str, ...]
    metrics: tuple[Metric, ...]
    constraints: tuple[str, ...]
    money: tuple[str, ...]
    approvers: tuple[str, ...]


def section(title: str, items: tuple[str, ...]) -> str:
    return title + "\n" + "\n".join(f"- {item}" for item in items)


def render(memo: Memo) -> str:
    return "\n\n".join([
        f"{memo.customer}. Решение: {memo.decision}",
        section("Входит в пилот:", memo.in_scope),
        section("Не входит:", memo.out_of_scope),
        section("Как проверим:", tuple(m.line() for m in memo.metrics)),
        section("Ограничения:", memo.constraints),
        section("Деньги:", memo.money),
        section("Подписывают:", memo.approvers),
    ])


def words(text: str) -> int:
    return sum(1 for w in text.split() if any(c.isalnum() for c in w))


if __name__ == "__main__":
    memo = Memo(
        customer="Nordbank Regional",
        decision="пилот подсказок оператору в очереди «карты», 10 недель",
        in_scope=("подсказка ответа по базе знаний в интерфейсе оператора",
                  "чтение счетов и истории обращений от имени оператора",
                  "резюме звонка, которое оператор правит и сохраняет в CRM"),
        out_of_scope=("ответы клиенту без оператора", "изменение данных в core banking",
                      "очереди «блокировки», «ипотека» и «бизнес»"),
        metrics=(
            Metric("средняя длительность обработки", "372 с", "не выше 335 с",
                   "400 звонков очереди «карты» за март"),
            Metric("доля резюме без правки", "0", "не ниже 0,80",
                   "200 звонков с разметкой супервизора"),
            Metric("стоимость обращения", "3,20 €", "не выше 3,00 €",
                   "биллинг пилота за четвёртый месяц"),
        ),
        constraints=("персональные данные обрабатываются только в регионе "
                     "(директор по информационной безопасности)",
                     "видимое клиенту решение подтверждает человек (комплаенс)",
                     "core banking недоступен с 02:00 до 04:00 (владелец платформы)"),
        money=("построение 240 000 €, эксплуатация 11 000 € в месяц",
               "окупаемость на четвёртом месяце при охвате 70 % к третьему"),
        approvers=("технический директор как спонсор",
                   "директор по информационной безопасности как владелец периметра",
                   "руководитель контакт-центра как владелец метрики"),
    )
    text = render(memo)
    assert words(text) <= WORD_LIMIT, words(text)
    for m in memo.metrics:
        assert m.name in text and m.baseline in text and m.target in text and m.dataset in text
    assert text.count("→") == len(memo.metrics)          # база и порог у каждой метрики
    assert all(memo.in_scope) and all(memo.out_of_scope)
    print(words(text), "слов, метрик", len(memo.metrics), "· границы пилота названы с обеих сторон")
