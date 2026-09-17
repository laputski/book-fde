from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    """A log entry: taken once and never edited afterwards."""

    id: str
    week: int
    question: str
    choice: str
    because: str
    supersedes: str | None = None


class DecisionLog:
    """An append-only log: status is computed from the links."""

    def __init__(self) -> None:
        self._rows: list[Decision] = []
        self._by_id: dict[str, Decision] = {}

    def append(self, row: Decision) -> Decision:
        if row.id in self._by_id:
            raise ValueError(f"identifier {row.id} is already taken")
        if self._rows and row.week < self._rows[-1].week:
            raise ValueError(f"a backdated entry: week {row.week}")
        if row.supersedes is not None:
            old = self._by_id.get(row.supersedes)
            if old is None:
                raise ValueError(f"decision {row.supersedes} is not in the log")
            if old.week > row.week:
                raise ValueError("a decision from the future cannot be superseded")
        self._rows.append(row)
        self._by_id[row.id] = row
        return row

    def __len__(self) -> int:
        return len(self._rows)

    def superseded_by(self, decision_id: str) -> str | None:
        return next((r.id for r in self._rows if r.supersedes == decision_id), None)

    def status(self, decision_id: str) -> str:
        return "superseded" if self.superseded_by(decision_id) else "in force"

    def in_force(self) -> list[Decision]:
        return [r for r in self._rows if self.superseded_by(r.id) is None]

    def problems(self) -> list[str]:
        """Consistency: no self-references, no dangling links, no double supersession."""
        found: list[str] = []
        replaced: dict[str, int] = {}
        for row in self._rows:
            if row.supersedes is None:
                continue
            replaced[row.supersedes] = replaced.get(row.supersedes, 0) + 1
            if row.supersedes == row.id:
                found.append(f"{row.id} supersedes itself")
            if row.supersedes not in self._by_id:
                found.append(f"{row.id} refers to unknown {row.supersedes}")
        found += [f"{k} is superseded more than once" for k, n in replaced.items() if n > 1]
        return found


if __name__ == "__main__":
    log = DecisionLog()
    log.append(Decision("D-1", 1, "what to build the slice on before access",
                        "synthetic transcripts", "access is expected by week 3"))
    log.append(Decision("D-2", 2, "scope of the pilot",
                        "one queue: cards", "other queues need a different ontology"))
    log.append(Decision("D-3", 5, "scope of the pilot",
                        "two queues: cards and card blocks", "the second queue takes the same tools",
                        supersedes="D-2"))
    assert log.status("D-2") == "superseded" and log.status("D-3") == "in force"
    assert [d.id for d in log.in_force()] == ["D-1", "D-3"]
    assert log.problems() == []
    try:
        log.append(Decision("D-4", 4, "scope of the pilot", "back to one queue",
                            "that is what the SOW said", supersedes="D-1"))
        raise AssertionError("a backdated entry must be rejected")
    except ValueError:
        pass
    print(len(log.in_force()), "decisions in force out of", len(log), "log entries")
