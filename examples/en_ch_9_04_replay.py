from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Event:
    seq: int
    kind: str                           # "model" or "tool"
    name: str
    args: dict[str, Any]
    result: str


class ReplayDivergence(Exception):
    """On replay the code asked for something other than what the log records."""


class AgentIO(Protocol):
    def call_model(self, prompt: str) -> str: ...
    def call_tool(self, name: str, args: dict[str, Any]) -> str: ...


@dataclass
class LiveIO:
    """Execution: calls the model and the tools and records every outcome."""
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
    """Replay: returns the recorded outcomes in order and calls nothing."""
    log: list[Event]
    position: int = 0

    def _next(self, kind: str, name: str, args: dict[str, Any]) -> str:
        if self.position >= len(self.log):
            raise ReplayDivergence(f"the log ended at event {self.position}")
        event = self.log[self.position]
        if (event.kind, event.name, event.args) != (kind, name, args):
            raise ReplayDivergence(f"event {self.position}: recorded {event.name}, requested {name}")
        self.position += 1
        return event.result

    def call_model(self, prompt: str) -> str:
        return self._next("model", "generate", {"prompt": prompt})

    def call_tool(self, name: str, args: dict[str, Any]) -> str:
        return self._next("tool", name, args)


def assess_file(io: AgentIO, customer: str) -> dict[str, str]:
    """Agent code: the same in execution and on replay."""
    docs = io.call_tool("search_documents", {"customer": customer})
    screening = io.call_tool("screen_sanctions", {"customer": customer})
    decision = io.call_model(f"documents: {docs}\nscreening: {screening}")
    return {"customer": customer, "decision": decision}


if __name__ == "__main__":
    documents = {"C-104233": "passport 2019, no proof of address"}
    sanctions = {"C-104233": "no match"}
    calls = {"tools": 0, "model": 0}

    def table_tool(table: dict[str, str]) -> Callable[[dict[str, Any]], str]:
        def handler(args: dict[str, Any]) -> str:
            calls["tools"] += 1
            return table[args["customer"]]
        return handler

    def sampled_model(prompt: str) -> str:
        calls["model"] += 1
        return f"request_proof_of_address (sample {calls['model']})"

    live = LiveIO(sampled_model, {"search_documents": table_tool(documents),
                                  "screen_sanctions": table_tool(sanctions)})
    decided = assess_file(live, "C-104233")
    stored = json.dumps([asdict(e) for e in live.log], ensure_ascii=False)

    documents["C-104233"] = "passport 2026, electricity bill"        # the data has changed
    sanctions["C-104233"] = "possible match"
    log = [Event(**row) for row in json.loads(stored)]
    assert assess_file(ReplayIO(log), "C-104233") == decided
    assert calls == {"tools": 2, "model": 1}                        # the replay called nothing

    def changed_agent(io: AgentIO, customer: str) -> dict[str, str]:
        io.call_tool("get_account", {"customer": customer})          # a step of the new code version
        return assess_file(io, customer)

    try:
        changed_agent(ReplayIO(log), "C-104233")
        raise AssertionError("a divergence between code and log must be detected")
    except ReplayDivergence:
        pass
    print("the decision was restored from the log without calling the model or tools")
