from __future__ import annotations

from dataclasses import dataclass

POINTS_PER_CUSTOMER = 30                 # breadth of a problem outweighs one large customer
EUR_PER_POINT = 10_000                   # revenue at risk: renewals and expansions
HOURS_PER_POINT = 20                     # workaround from the time log
TOP = 3                                  # the brief carries the top three


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    customers: frozenset[str]
    revenue_at_risk_eur: int
    workaround_hours: int
    evidence: tuple[str, ...]            # links to pattern-registry records

    def points(self) -> int:
        return (POINTS_PER_CUSTOMER * len(self.customers)
                + self.revenue_at_risk_eur // EUR_PER_POINT
                + self.workaround_hours // HOURS_PER_POINT)


def rank(entries: list[Entry]) -> tuple[list[Entry], list[str]]:
    ranked = [e for e in entries if e.evidence]
    skipped = [f"{e.id}: no evidence" for e in entries if not e.evidence]
    ranked.sort(key=lambda e: (-e.points(), -len(e.customers), e.id))   # tie-breaker
    return ranked, skipped


def eur(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def brief(entries: list[Entry], quarter: str) -> str:
    ranked, skipped = rank(entries)
    lines = [f"Roadmap input from the regional squad, {quarter}",
             f"Decision: take {', '.join(e.id for e in ranked[:TOP])} into the quarter",
             f"Rule: {POINTS_PER_CUSTOMER} points per customer, 1 per {eur(EUR_PER_POINT)} EUR "
             f"at risk, 1 per {HOURS_PER_POINT} h of workaround; on a tie, more customers first", ""]
    for n, e in enumerate(ranked[:TOP], 1):
        lines += [f"{n}. {e.title} [{e.id}], {e.points()} points",
                  f"   {', '.join(sorted(e.customers))}; {eur(e.revenue_at_risk_eur)} EUR; "
                  f"{e.workaround_hours} h; {', '.join(e.evidence)}"]
    lines += ["", "Below the line: " + ", ".join(f"{e.id} ({e.points()})" for e in ranked[TOP:]),
              "Not ranked: " + ("; ".join(skipped) or "none")]
    return "\n".join(lines)


if __name__ == "__main__":
    registry = [
        Entry("approval", "Approval bound to arguments", frozenset({"CF1", "CF4", "CF5"}),
              420_000, 356, ("pattern:approval", "fr:approval-primitive")),
        Entry("residency", "Data stays in the region", frozenset({"CF1", "CF5"}),
              600_000, 180, ("pattern:residency",)),
        Entry("offline-eval", "Evaluation at an air-gapped site", frozenset({"CF6"}),
              870_000, 240, ("pattern:offline-eval",)),
        Entry("voice-barge-in", "Barge-in on the voice channel", frozenset({"CF2"}),
              150_000, 90, ("trace:mh-0311",)),
        Entry("sap-adapter", "SAP adapter", frozenset({"CF3"}), 300_000, 400, ()),
    ]
    ranked, skipped = rank(registry)
    assert [e.points() for e in ranked] == [149, 129, 129, 49]
    assert [e.id for e in ranked[:TOP]] == ["approval", "residency", "offline-eval"]
    assert skipped == ["sap-adapter: no evidence"]
    text = brief(registry, "Q4 2026")
    assert text.splitlines()[1] == "Decision: take approval, residency, offline-eval into the quarter"
    assert len(text.splitlines()) <= 40                                 # one page
    print(text.splitlines()[1], "·", len(text.splitlines()), "lines in the brief")
