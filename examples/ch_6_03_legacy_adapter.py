from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import partial


class LegacyDown(Exception):
    """Адаптер отказал сам, не дожидаясь системы."""


@dataclass
class Clock:
    t: float = 0.0

    def now(self) -> float:
        return self.t


@dataclass
class CircuitBreaker:
    clock: Clock
    threshold: int = 3          # отказов подряд до размыкания
    cooldown: float = 30.0      # секунд до пробного обращения
    failures: int = 0
    opened_at: float | None = None

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        if self.clock.now() - self.opened_at >= self.cooldown:
            return "half_open"
        return "open"

    def call[T](self, fn: Callable[[], T]) -> T:
        if self.state == "open":
            raise LegacyDown("цепь разомкнута")
        try:
            result = fn()
        except (TimeoutError, ConnectionError):
            self.failures += 1
            if self.failures >= self.threshold or self.state == "half_open":
                self.opened_at = self.clock.now()
            raise
        self.failures = 0
        self.opened_at = None
        return result


@dataclass
class SoapAccounts:
    """Заглушка SOAP-слоя: страницы по 50 записей, иногда молчит."""
    rows: list[dict[str, str]]
    fail_next: int = 0
    calls: int = 0

    def page(self, cursor: int, size: int = 50) -> tuple[list[dict[str, str]], int | None]:
        self.calls += 1
        if self.fail_next:
            self.fail_next -= 1
            raise TimeoutError("SOAP не ответил за 5 с")
        chunk = self.rows[cursor:cursor + size]
        nxt = cursor + size if cursor + size < len(self.rows) else None
        return chunk, nxt


@dataclass
class TransactionsAdapter:
    soap: SoapAccounts
    breaker: CircuitBreaker
    max_pages: int = 4          # не более 200 операций за один вызов инструмента
    deadline_s: float = 8.0

    def transactions(self, started_at: float) -> Iterator[dict[str, str]]:
        cursor: int | None = 0
        pages = 0
        while cursor is not None and pages < self.max_pages:
            if self.breaker.clock.now() - started_at > self.deadline_s:
                raise TimeoutError("бюджет времени инструмента исчерпан")
            chunk, cursor = self.breaker.call(partial(self.soap.page, cursor))
            pages += 1
            yield from chunk


if __name__ == "__main__":
    clock = Clock()
    soap = SoapAccounts(rows=[{"id": str(i)} for i in range(320)])
    adapter = TransactionsAdapter(soap, CircuitBreaker(clock))
    got = list(adapter.transactions(started_at=clock.now()))
    assert len(got) == 200 and soap.calls == 4         # пагинация с потолком

    soap.fail_next = 3
    for _ in range(3):
        try:
            list(adapter.transactions(clock.now()))
        except TimeoutError:
            pass
    assert adapter.breaker.state == "open"
    try:
        list(adapter.transactions(clock.now()))
        raise AssertionError("разомкнутая цепь обязана отказать сразу")
    except LegacyDown:
        pass
    assert soap.calls == 7                              # система не тронута
    clock.t += 31
    assert adapter.breaker.state == "half_open"
    assert len(list(adapter.transactions(clock.now()))) == 200
    assert adapter.breaker.state == "closed"
    print("адаптер пагинирует, укладывается в бюджет и размыкает цепь")
