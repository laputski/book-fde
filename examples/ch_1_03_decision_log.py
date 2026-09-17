from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    """Запись журнала: принимается один раз и больше не правится."""

    id: str
    week: int
    question: str
    choice: str
    because: str
    supersedes: str | None = None


class DecisionLog:
    """Журнал только на добавление: статус вычисляется из ссылок."""

    def __init__(self) -> None:
        self._rows: list[Decision] = []
        self._by_id: dict[str, Decision] = {}

    def append(self, row: Decision) -> Decision:
        if row.id in self._by_id:
            raise ValueError(f"идентификатор {row.id} уже занят")
        if self._rows and row.week < self._rows[-1].week:
            raise ValueError(f"запись задним числом: неделя {row.week}")
        if row.supersedes is not None:
            old = self._by_id.get(row.supersedes)
            if old is None:
                raise ValueError(f"решения {row.supersedes} в журнале нет")
            if old.week > row.week:
                raise ValueError("нельзя отменить решение из будущего")
        self._rows.append(row)
        self._by_id[row.id] = row
        return row

    def __len__(self) -> int:
        return len(self._rows)

    def superseded_by(self, decision_id: str) -> str | None:
        return next((r.id for r in self._rows if r.supersedes == decision_id), None)

    def status(self, decision_id: str) -> str:
        return "отменено" if self.superseded_by(decision_id) else "в силе"

    def in_force(self) -> list[Decision]:
        return [r for r in self._rows if self.superseded_by(r.id) is None]

    def problems(self) -> list[str]:
        """Согласованность: без самоссылок, висящих ссылок и двойных отмен."""
        found: list[str] = []
        replaced: dict[str, int] = {}
        for row in self._rows:
            if row.supersedes is None:
                continue
            replaced[row.supersedes] = replaced.get(row.supersedes, 0) + 1
            if row.supersedes == row.id:
                found.append(f"{row.id} отменяет само себя")
            if row.supersedes not in self._by_id:
                found.append(f"{row.id} ссылается на неизвестное {row.supersedes}")
        found += [f"{k} отменено дважды и более" for k, n in replaced.items() if n > 1]
        return found


if __name__ == "__main__":
    log = DecisionLog()
    log.append(Decision("D-1", 1, "на чём строить срез до выдачи доступа",
                        "синтетические транскрипты", "доступ ожидается к неделе 3"))
    log.append(Decision("D-2", 2, "объём пилота",
                        "одна очередь: карты", "прочие очереди требуют другой онтологии"))
    log.append(Decision("D-3", 5, "объём пилота",
                        "две очереди: карты и блокировки", "вторая очередь берёт те же инструменты",
                        supersedes="D-2"))
    assert log.status("D-2") == "отменено" and log.status("D-3") == "в силе"
    assert [d.id for d in log.in_force()] == ["D-1", "D-3"]
    assert log.problems() == []
    try:
        log.append(Decision("D-4", 4, "объём пилота", "вернуть одну очередь",
                            "так было в SOW", supersedes="D-1"))
        raise AssertionError("запись задним числом обязана быть отвергнута")
    except ValueError:
        pass
    print(len(log.in_force()), "решения в силе из", len(log), "записей журнала")
