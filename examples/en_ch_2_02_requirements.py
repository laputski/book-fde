from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ConstraintKind(StrEnum):
    REGULATORY = "regulatory"            # law, supervision, internal policy
    DATA = "data"                        # contents, quality, retention
    INFRASTRUCTURE = "infrastructure"    # networks, maintenance windows, quotas
    ORGANISATIONAL = "organisational"    # approval chain, calendar, budget
    HARDWARE = "hardware"                # where the model physically runs


FIXED = frozenset({ConstraintKind.REGULATORY, ConstraintKind.HARDWARE})


class Constraint(BaseModel):
    id: str
    kind: ConstraintKind
    statement: str
    source: str                          # role and date of the conversation
    verified: bool = False               # confirmed by a document
    mitigation: str = ""                 # how the requirement is met without breaking it

    @property
    def negotiable(self) -> bool:
        return self.kind not in FIXED

    @property
    def blocking(self) -> bool:
        return not self.mitigation


class Requirement(BaseModel):
    id: str
    statement: str
    source: str
    metric: str = ""
    threshold: float | None = None
    dataset: str = ""
    value: int = Field(ge=0, le=5)
    feasibility: int = Field(ge=0, le=5)
    blast_radius: int = Field(ge=1, le=5)
    constrained_by: tuple[str, ...] = ()

    @property
    def missing(self) -> tuple[str, ...]:
        gaps: list[str] = []
        if not self.metric:
            gaps.append("metric")
        if self.threshold is None:
            gaps.append("threshold")
        if not self.dataset:
            gaps.append("dataset")
        return tuple(gaps)

    @property
    def testable(self) -> bool:
        return not self.missing


def score(req: Requirement, limits: dict[str, Constraint]) -> float:
    """Value per unit of blast radius; untestable and blocked candidates are worth zero."""
    if not req.testable:
        return 0.0
    if any(limits[k].blocking for k in req.constrained_by if k in limits):
        return 0.0
    return round(req.value * req.feasibility / req.blast_radius, 2)


def rank(reqs: list[Requirement], limits: list[Constraint]) -> list[Requirement]:
    index = {c.id: c for c in limits}
    return sorted(reqs, key=lambda r: (-score(r, index), r.id))


if __name__ == "__main__":
    limits = [
        Constraint(id="K-1", kind=ConstraintKind.HARDWARE, verified=True,
                   source="chief information security officer, 6 March",
                   statement="personal data is processed inside the region only",
                   mitigation="a regional model endpoint inside the VPC perimeter"),
        Constraint(id="K-2", kind=ConstraintKind.REGULATORY, source="compliance, 7 March", verified=True,
                   statement="a decision visible to the customer is confirmed by a human"),
        Constraint(id="K-3", kind=ConstraintKind.INFRASTRUCTURE, source="platform owner, 6 March",
                   statement="core banking is unavailable from 02:00 to 04:00",
                   mitigation="the tool answers \"unavailable until 04:00\""),
    ]
    candidates = [
        Requirement(id="R-7", source="head of the contact centre, 5 March",
                    statement="suggest an answer to the agent from the knowledge base",
                    metric="average handling time, s", threshold=335.0,
                    dataset="400 calls of the cards queue in March",
                    value=5, feasibility=4, blast_radius=1, constrained_by=("K-1", "K-3")),
        Requirement(id="R-9", source="chief technology officer, 4 March",
                    statement="the assistant must be accurate",
                    value=5, feasibility=3, blast_radius=2),
        Requirement(id="R-12", source="chief technology officer, 4 March",
                    statement="answer the customer without an agent",
                    metric="share of cases closed without an agent", threshold=0.25,
                    dataset="30 days of inbound cases",
                    value=5, feasibility=2, blast_radius=5, constrained_by=("K-2",)),
        Requirement(id="R-15", source="agent, 6 March",
                    statement="store the call summary in the CRM",
                    metric="share of summaries accepted unedited", threshold=0.8,
                    dataset="200 calls labelled by a supervisor",
                    value=3, feasibility=5, blast_radius=2, constrained_by=("K-1",)),
    ]
    index = {c.id: c for c in limits}
    assert candidates[1].missing == ("metric", "threshold", "dataset")
    assert score(candidates[1], index) == 0.0             # an untestable wish
    assert candidates[2].testable and score(candidates[2], index) == 0.0
    assert score(candidates[3], index) == 7.5             # the constraint is named and designed around
    assert [c.id for c in limits if not c.negotiable] == ["K-1", "K-2"]
    order = [r.id for r in rank(candidates, limits)]
    assert order == ["R-7", "R-15", "R-12", "R-9"]
    print("ranked:", order, "· the pilot takes", order[0])
