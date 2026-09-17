from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Crm:
    """External system: keeps its data across a restart of the worker."""
    letters: list[str] = field(default_factory=list)


@dataclass
class Worker:
    crm: Crm
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)   # kept in process memory

    def advance(self, customer: str) -> str:
        run = self.runs.setdefault(customer, {"step": "assess"})
        if run["step"] == "assess":
            run["missing"] = ["proof_of_address"]
            run["step"] = "request"
        elif run["step"] == "request":
            self.crm.letters.append(customer)          # document request to the customer
            run["step"] = "wait_for_customer"
        return str(run["step"])


if __name__ == "__main__":
    crm = Crm()
    worker = Worker(crm)
    worker.advance("C-104233")
    assert worker.advance("C-104233") == "wait_for_customer" and len(crm.letters) == 1

    worker = Worker(crm)                               # a deploy: a new process
    assert worker.runs == {}                           # files in progress are forgotten
    worker.advance("C-104233")
    worker.advance("C-104233")
    assert len(crm.letters) == 2                       # the customer got a second request
    print("the restart erased the state, and the customer was asked twice")
