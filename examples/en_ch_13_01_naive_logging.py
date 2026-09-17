import heapq
import io
from collections.abc import Iterator
from contextlib import redirect_stdout

NOW = [0.0]


def log(message: str) -> None:
    print(f"[{NOW[0]:4.1f}] {message}")


def handle(tenant: str, question: str, tool_s: float) -> Iterator[float]:
    """The hint handler: yield hands control back for the duration of a wait."""
    log(f"request from {tenant}: {question}")
    yield 0.3
    log("retrieval: ok")
    yield 1.1
    log("model: ok, 5060 tokens")
    yield tool_s
    log("tool: ok")
    yield 2.3
    log("model: ok, 13470 tokens")


def serve(handlers: list[Iterator[float]]) -> None:
    """Two requests at once: wake the one whose wait ends first."""
    wake = [(i * 0.2, i) for i in range(len(handlers))]
    while wake:
        NOW[0], i = heapq.heappop(wake)
        wait = next(handlers[i], None)
        if wait is not None:
            heapq.heappush(wake, (round(NOW[0] + wait, 1), i))


if __name__ == "__main__":
    out = io.StringIO()
    with redirect_stdout(out):
        serve([handle("consumer", "why were 300 roubles charged?", tool_s=2.5),
               handle("enterprise", "status of circuit 4471", tool_s=0.3)])
    lines = out.getvalue().splitlines()
    starts = [float(x[1:5]) for x in lines if "request from" in x]
    tools = [float(x[1:5]) for x in lines if "tool: ok" in x]
    assert len(starts) == len(tools) == 2
    assert all(s < t for s in starts for t in tools)      # any line fits any request
    assert sum("consumer" in x for x in lines) == 1          # the tenant is only in the first line
    assert "300 roubles" in out.getvalue()                    # the subscriber's question is written to the log
    print("the log cannot tell whose tool was slow or who pays for what")
