from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


class Crash(Exception):
    """The worker process stopped: a deploy, node preemption, out of memory."""


@dataclass(frozen=True)
class Checkpoint:
    run_id: str
    next_step: int
    state: dict[str, Any]
    version: int


class CheckpointStore(Protocol):
    def load(self, run_id: str) -> Checkpoint | None: ...
    def save(self, checkpoint: Checkpoint) -> None: ...


@dataclass
class InMemoryCheckpointStore:
    rows: dict[str, Checkpoint] = field(default_factory=dict)

    def load(self, run_id: str) -> Checkpoint | None:
        return self.rows.get(run_id)

    def save(self, checkpoint: Checkpoint) -> None:
        current = self.rows.get(checkpoint.run_id)
        if checkpoint.version != (current.version if current else 0) + 1:
            raise RuntimeError("the run was already advanced by another worker")
        self.rows[checkpoint.run_id] = checkpoint


@dataclass
class SideEffectLedger:
    """Intents and outcomes of side effects by idempotency key."""
    intents: dict[str, dict[str, Any]] = field(default_factory=dict)
    outcomes: dict[str, str] = field(default_factory=dict)

    def intend(self, key: str, tool: str, args: dict[str, Any]) -> None:
        self.intents.setdefault(key, {"tool": tool, "args": args})

    def record(self, key: str, outcome: str) -> None:
        self.outcomes[key] = outcome

    def pending(self) -> list[str]:
        return [k for k in self.intents if k not in self.outcomes]


@dataclass
class FakeCrm:
    """Tools of the Chapter 6 MCP server: the document request remembers keys."""
    letters: list[str] = field(default_factory=list)
    by_key: dict[str, str] = field(default_factory=dict)
    calls: int = 0
    reads: int = 0

    def documents(self, customer: str) -> list[str]:
        self.reads += 1
        return ["passport"]

    def request_documents(self, key: str, customer: str, missing: list[str]) -> str:
        self.calls += 1
        if key not in self.by_key:
            self.letters.append(customer)
            self.by_key[key] = f"REQ-{len(self.letters)}"
        return self.by_key[key]


def effect_key(run_id: str, step: int, tool: str, args: dict[str, Any]) -> str:
    raw = json.dumps([run_id, step, tool, args], sort_keys=True, ensure_ascii=False)
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=12).hexdigest()


Step = Callable[[str, int, dict[str, Any]], dict[str, Any]]
REQUIRED = {"passport", "proof_of_address"}


@dataclass
class Runner:
    store: CheckpointStore
    ledger: SideEffectLedger
    crm: FakeCrm
    crash_at: str = ""                  # fault injection point for the check

    def run(self, run_id: str, customer: str) -> dict[str, Any]:
        steps: list[Step] = [self.read, self.assess, self.request, self.close]
        cp = self.store.load(run_id) or Checkpoint(run_id, 0, {"customer": customer}, 0)
        state, version = dict(cp.state), cp.version
        for n in range(cp.next_step, len(steps)):
            state = steps[n](run_id, n, state)
            version += 1
            self.store.save(Checkpoint(run_id, n + 1, state, version))
        return state

    def read(self, run_id: str, n: int, state: dict[str, Any]) -> dict[str, Any]:
        return {**state, "docs": self.crm.documents(state["customer"])}

    def assess(self, run_id: str, n: int, state: dict[str, Any]) -> dict[str, Any]:
        return {**state, "missing": sorted(REQUIRED - set(state["docs"]))}

    def request(self, run_id: str, n: int, state: dict[str, Any]) -> dict[str, Any]:
        args = {"customer": state["customer"], "missing": state["missing"]}
        key = effect_key(run_id, n, "request_documents", args)
        if key in self.ledger.outcomes:                      # outcome recorded: do not call
            return {**state, "request": self.ledger.outcomes[key]}
        self.ledger.intend(key, "request_documents", args)   # before the side effect
        outcome = self.crm.request_documents(key, args["customer"], args["missing"])
        if self.crash_at == "after_call":
            raise Crash("the outcome of the call was not recorded")
        self.ledger.record(key, outcome)                     # after the side effect
        if self.crash_at == "after_record":
            raise Crash("the checkpoint was not advanced")
        return {**state, "request": outcome}

    def close(self, run_id: str, n: int, state: dict[str, Any]) -> dict[str, Any]:
        return {**state, "status": "waiting_for_customer"}


if __name__ == "__main__":
    for crash_at, calls in (("after_call", 2), ("after_record", 1)):
        store, ledger, crm = InMemoryCheckpointStore(), SideEffectLedger(), FakeCrm()
        try:
            Runner(store, ledger, crm, crash_at=crash_at).run("run-1", "C-104233")
            raise AssertionError("the failure must happen")
        except Crash:
            pass
        saved = store.load("run-1")
        assert saved is not None and saved.next_step == 2       # reads and assessment are saved
        assert len(ledger.pending()) == (1 if crash_at == "after_call" else 0)
        final = Runner(store, ledger, crm).run("run-1", "C-104233")   # a new process
        assert final["status"] == "waiting_for_customer" and final["request"] == "REQ-1"
        assert crm.letters == ["C-104233"] and crm.calls == calls and crm.reads == 1
        assert ledger.pending() == []
    print("the run resumed from its checkpoint, the customer got one letter")
