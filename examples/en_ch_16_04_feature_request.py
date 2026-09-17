from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Evidence:
    engagement: str                   # case-file code of the affected customer
    workaround_hours: int             # measured from timesheets
    links: tuple[str, ...]            # traces, eval runs, decision-log entries


@dataclass(frozen=True)
class FeatureRequest:
    title: str
    problem: str
    proposed_interface: str
    if_not_built: str
    evidence: tuple[Evidence, ...] = ()

    def refusals(self) -> list[str]:
        found: list[str] = []
        if not self.evidence:
            found.append("no affected customers named")
        found += [f"{e.engagement}: workaround cost not measured"
                  for e in self.evidence if e.workaround_hours <= 0]
        found += [f"{e.engagement}: no links to traces or evals"
                  for e in self.evidence if not e.links]
        return found

    def render(self, hourly_cost: int) -> str:
        if problems := self.refusals():
            raise ValueError("request refused: " + "; ".join(problems))
        hours = sum(e.workaround_hours for e in self.evidence)
        rows = [f"- {e.engagement}: {e.workaround_hours} h; {', '.join(e.links)}"
                for e in sorted(self.evidence, key=lambda e: e.engagement)]
        return "\n".join([
            f"# {self.title}",
            f"Problem: {self.problem}",
            f"Affected customers: {len(self.evidence)}",
            f"Workaround cost: {hours} h, {hours * hourly_cost} EUR",
            "Evidence:", *rows,
            f"Proposed interface: {self.proposed_interface}",
            f"If not built: {self.if_not_built}",
        ])


if __name__ == "__main__":
    request = FeatureRequest(
        title="Approval bound to arguments as a platform primitive",
        problem="the approval interrupt contains the action name but not its arguments or expiry",
        proposed_interface="interrupt(action, args_hash, approver_role, ttl_s) -> ApprovalToken",
        if_not_built="every engagement writes its own wrapper; a wrapper defect is fixed N times",
        evidence=(Evidence("CF4", 96, ("trace:or-0412", "eval:or-approvals@3")),
                  Evidence("CF1", 140, ("decision:D-31", "eval:nb-approvals@5")),
                  Evidence("CF5", 120, ("trace:ng-0907", "decision:D-12"))),
    )
    text = request.render(hourly_cost=95)
    assert "Workaround cost: 356 h, 33820 EUR" in text
    assert text.index("- CF1") < text.index("- CF4") < text.index("- CF5")
    for broken, reason in ((FeatureRequest("x", "y", "z", "w"), "no affected"),
                           (FeatureRequest("x", "y", "z", "w", (Evidence("CF1", 0, ("trace:1",)),)),
                            "not measured")):
        try:
            broken.render(hourly_cost=95)
            raise AssertionError("a request without evidence was accepted")
        except ValueError as err:
            assert reason in str(err)
    print(text.splitlines()[0], "· 3 customers affected, 356 h of workaround")
