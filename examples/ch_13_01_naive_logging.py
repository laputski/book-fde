import heapq
import io
from collections.abc import Iterator
from contextlib import redirect_stdout

NOW = [0.0]


def log(message: str) -> None:
    print(f"[{NOW[0]:4.1f}] {message}")


def handle(tenant: str, question: str, tool_s: float) -> Iterator[float]:
    """Обработчик подсказки: yield отдаёт управление на время ожидания."""
    log(f"запрос от {tenant}: {question}")
    yield 0.3
    log("поиск: ok")
    yield 1.1
    log("модель: ok, 5060 токенов")
    yield tool_s
    log("инструмент: ok")
    yield 2.3
    log("модель: ok, 13470 токенов")


def serve(handlers: list[Iterator[float]]) -> None:
    """Два запроса одновременно: будим того, чьё ожидание кончается раньше."""
    wake = [(i * 0.2, i) for i in range(len(handlers))]
    while wake:
        NOW[0], i = heapq.heappop(wake)
        wait = next(handlers[i], None)
        if wait is not None:
            heapq.heappush(wake, (round(NOW[0] + wait, 1), i))


if __name__ == "__main__":
    out = io.StringIO()
    with redirect_stdout(out):
        serve([handle("consumer", "почему списали 300 рублей?", tool_s=2.5),
               handle("enterprise", "статус канала 4471", tool_s=0.3)])
    lines = out.getvalue().splitlines()
    starts = [float(x[1:5]) for x in lines if "запрос от" in x]
    tools = [float(x[1:5]) for x in lines if "инструмент" in x]
    assert len(starts) == len(tools) == 2
    assert all(s < t for s in starts for t in tools)      # любая строка подходит любому запросу
    assert sum("consumer" in x for x in lines) == 1          # арендатор только в первой строке
    assert "300 рублей" in out.getvalue()                     # при этом вопрос абонента записан в журнал
    print("по журналу не понять, чей инструмент был медленным и кто за что платит")
