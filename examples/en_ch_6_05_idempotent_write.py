from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


def idempotency_key(session_id: str, step: int, tool: str, args: dict[str, Any]) -> str:
    payload = json.dumps({"s": session_id, "n": step, "t": tool, "a": args},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


@dataclass
class IdempotencyStore:
    """Stored results by key, expiring with time."""
    now: Callable[[], float]
    ttl_s: float = 24 * 3600
    rows: dict[str, tuple[float, str]] = field(default_factory=dict)
    in_flight: set[str] = field(default_factory=set)

    def run(self, key: str, action: Callable[[], str]) -> str:
        entry = self.rows.get(key)
        if entry and self.now() - entry[0] < self.ttl_s:
            return entry[1]                          # a retry: a read instead of the action
        if key in self.in_flight:
            raise RuntimeError("the action is still running: wait for its outcome")
        self.in_flight.add(key)
        try:
            result = action()
        finally:
            self.in_flight.discard(key)
        self.rows[key] = (self.now(), result)
        return result


if __name__ == "__main__":
    clock = {"t": 0.0}
    created: list[str] = []

    def create_dispute() -> str:
        created.append(f"D-{len(created) + 1}")
        return created[-1]

    store = IdempotencyStore(now=lambda: clock["t"])
    key = idempotency_key("sess-9", 4, "create_dispute", {"tx": "tx-42", "reason": "double charge"})
    first = store.run(key, create_dispute)
    second = store.run(key, create_dispute)             # a retry after a timeout
    assert first == second == "D-1" and created == ["D-1"]
    other = idempotency_key("sess-9", 5, "create_dispute", {"tx": "tx-42", "reason": "double charge"})
    assert store.run(other, create_dispute) == "D-2"    # a new step: a new intent
    clock["t"] += 25 * 3600
    assert store.run(key, create_dispute) == "D-3"      # the key expired: the action runs again
    print("a retry within the term returns the stored result")
