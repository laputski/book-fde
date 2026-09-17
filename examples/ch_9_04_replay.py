from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Event:
    seq: int
    kind: str                           # "model" или "tool"
    name: str
    args: dict[str, Any]
    result: str


class ReplayDivergence(Exception):
    """Код на повторе запросил не то, что записано в журнале."""


class AgentIO(Protocol):
    def call_model(self, prompt: str) -> str: ...
    def call_tool(self, name: str, args: dict[str, Any]) -> str: ...


@dataclass
class LiveIO:
    """Исполнение: вызывает модель и инструменты и записывает каждый исход."""
    model: Callable[[str], str]
    tools: dict[str, Callable[[dict[str, Any]], str]]
    log: list[Event] = field(default_factory=list)

    def _append(self, kind: str, name: str, args: dict[str, Any], result: str) -> str:
        self.log.append(Event(len(self.log), kind, name, args, result))
        return result

    def call_model(self, prompt: str) -> str:
        return self._append("model", "generate", {"prompt": prompt}, self.model(prompt))

    def call_tool(self, name: str, args: dict[str, Any]) -> str:
        return self._append("tool", name, args, self.tools[name](args))


@dataclass
class ReplayIO:
    """Повтор: отдаёт записанные исходы по порядку и ничего не вызывает."""
    log: list[Event]
    position: int = 0

    def _next(self, kind: str, name: str, args: dict[str, Any]) -> str:
        if self.position >= len(self.log):
            raise ReplayDivergence(f"журнал кончился на событии {self.position}")
        event = self.log[self.position]
        if (event.kind, event.name, event.args) != (kind, name, args):
            raise ReplayDivergence(f"событие {self.position}: записан {event.name}, запрошен {name}")
        self.position += 1
        return event.result

    def call_model(self, prompt: str) -> str:
        return self._next("model", "generate", {"prompt": prompt})

    def call_tool(self, name: str, args: dict[str, Any]) -> str:
        return self._next("tool", name, args)


def assess_file(io: AgentIO, customer: str) -> dict[str, str]:
    """Код агента: один и тот же при исполнении и при повторе."""
    docs = io.call_tool("search_documents", {"customer": customer})
    screening = io.call_tool("screen_sanctions", {"customer": customer})
    decision = io.call_model(f"documents: {docs}\nscreening: {screening}")
    return {"customer": customer, "decision": decision}


if __name__ == "__main__":
    documents = {"C-104233": "паспорт 2019, подтверждения адреса нет"}
    sanctions = {"C-104233": "совпадений нет"}
    calls = {"tools": 0, "model": 0}

    def table_tool(table: dict[str, str]) -> Callable[[dict[str, Any]], str]:
        def handler(args: dict[str, Any]) -> str:
            calls["tools"] += 1
            return table[args["customer"]]
        return handler

    def sampled_model(prompt: str) -> str:
        calls["model"] += 1
        return f"request_proof_of_address (выборка {calls['model']})"

    live = LiveIO(sampled_model, {"search_documents": table_tool(documents),
                                  "screen_sanctions": table_tool(sanctions)})
    decided = assess_file(live, "C-104233")
    stored = json.dumps([asdict(e) for e in live.log], ensure_ascii=False)

    documents["C-104233"] = "паспорт 2026, счёт за электричество"   # данные изменились
    sanctions["C-104233"] = "возможное совпадение"
    log = [Event(**row) for row in json.loads(stored)]
    assert assess_file(ReplayIO(log), "C-104233") == decided
    assert calls == {"tools": 2, "model": 1}                        # повтор ничего не вызвал

    def changed_agent(io: AgentIO, customer: str) -> dict[str, str]:
        io.call_tool("get_account", {"customer": customer})          # шаг новой версии кода
        return assess_file(io, customer)

    try:
        changed_agent(ReplayIO(log), "C-104233")
        raise AssertionError("расхождение кода с журналом обязано обнаружиться")
    except ReplayDivergence:
        pass
    print("решение восстановлено из журнала без вызова модели и инструментов")
