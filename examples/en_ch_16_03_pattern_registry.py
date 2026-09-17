from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum

EVIDENCE_KINDS = ("decision:", "commit:", "trace:", "eval:")


class Kind(StrEnum):
    PROBLEM = "problem"           # a recurring user need
    CONSTRAINT = "constraint"     # a recurring constraint of the environment
    SOLUTION = "solution"         # a recurring shape of the solution


@dataclass(frozen=True)
class Occurrence:
    engagement: str               # case-file code: "CF1"
    kind: Kind
    evidence: str                 # decision-log entry, commit, trace or eval run
    workaround_hours: int = 0     # hours spent working around the product, from timesheets


@dataclass
class Pattern:
    id: str
    title: str
    occurrences: list[Occurrence] = field(default_factory=list)

    def engagements(self, kind: Kind) -> set[str]:
        return {o.engagement for o in self.occurrences if o.kind == kind}

    def promotion_blockers(self, threshold: int = 3) -> list[str]:
        """An empty list means the pattern is ready to become a module."""
        blockers = [f"{kind}: {len(self.engagements(kind))} of {threshold}"
                    for kind in Kind if len(self.engagements(kind)) < threshold]
        unverifiable = [o.engagement for o in self.occurrences
                        if not o.evidence.startswith(EVIDENCE_KINDS)]
        if unverifiable:
            blockers.append(f"occurrences without a verifiable link: {sorted(set(unverifiable))}")
        return blockers


@dataclass
class PatternRegistry:
    patterns: dict[str, Pattern] = field(default_factory=dict)

    def record(self, pattern_id: str, title: str, occurrence: Occurrence) -> None:
        pattern = self.patterns.setdefault(pattern_id, Pattern(pattern_id, title))
        if occurrence not in pattern.occurrences:          # re-reading does not double the count
            pattern.occurrences.append(occurrence)

    def promotable(self) -> list[str]:
        return sorted(pid for pid, p in self.patterns.items() if not p.promotion_blockers())

    def workaround_hours(self, pattern_id: str) -> dict[str, int]:
        hours: defaultdict[str, int] = defaultdict(int)
        for o in self.patterns[pattern_id].occurrences:
            hours[o.engagement] += o.workaround_hours
        return dict(hours)


if __name__ == "__main__":
    reg = PatternRegistry()
    approval, residency = "approval bound to arguments", "data stays in region"
    for cf, action, hours in (("CF1", "create_dispute", 140), ("CF4", "publish_status", 96),
                              ("CF5", "submit_request", 120)):
        reg.record("approval", approval, Occurrence(cf, Kind.PROBLEM, f"decision:{cf}-{action}"))
        reg.record("approval", approval, Occurrence(cf, Kind.CONSTRAINT, f"eval:{cf}-approvals"))
        reg.record("approval", approval, Occurrence(cf, Kind.SOLUTION, f"commit:{cf}-{action}", hours))
    reg.record("approval", approval, Occurrence("CF1", Kind.PROBLEM, "decision:CF1-create_dispute"))
    for cf in ("CF1", "CF5"):
        reg.record("residency", residency, Occurrence(cf, Kind.CONSTRAINT, f"decision:{cf}-dpo"))
        reg.record("residency", residency, Occurrence(cf, Kind.SOLUTION, f"commit:{cf}-region"))
    reg.record("residency", residency, Occurrence("CF4", Kind.PROBLEM, "the team says so"))

    assert len(reg.patterns["approval"].occurrences) == 9 and reg.promotable() == ["approval"]
    assert reg.workaround_hours("approval") == {"CF1": 140, "CF4": 96, "CF5": 120}
    blockers = reg.patterns["residency"].promotion_blockers()
    assert "problem: 1 of 3" in blockers and "constraint: 2 of 3" in blockers
    assert any("CF4" in b for b in blockers)
    print("ready for a module:", reg.promotable(), "· residency waits on:", blockers)
