from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

MAX_WEEKS = 16


class Gate(BaseModel):
    """A gate: a checkable condition for crossing, with a week and an owner."""

    name: str
    week: int = Field(ge=1, le=MAX_WEEKS)
    owner: str = Field(min_length=3)          # the name of a specific person
    exit_criteria: list[str] = Field(min_length=1)

    @field_validator("exit_criteria")
    @classmethod
    def measurable(cls, criteria: list[str]) -> list[str]:
        for line in criteria:
            if not any(ch.isdigit() for ch in line):
                raise ValueError(f"a criterion without a number is uncheckable: {line}")
        return criteria


class Phase(BaseModel):
    name: str
    first_week: int = Field(ge=1, le=MAX_WEEKS)
    last_week: int = Field(ge=1, le=MAX_WEEKS)
    gate: Gate | None = None

    @model_validator(mode="after")
    def gate_required(self) -> Phase:
        if self.gate is None:
            raise ValueError(f"phase {self.name} has no gate")
        if not self.first_week <= self.gate.week <= self.last_week:
            raise ValueError(f"gate {self.gate.name} lies outside its phase")
        return self


class RiskEntry(BaseModel):
    risk: str
    probability: float = Field(ge=0.0, le=1.0)
    delay_weeks: int = Field(ge=0)
    owner: str
    mitigation: str

    @property
    def expected_delay(self) -> float:
        return self.probability * self.delay_weeks


class Engagement(BaseModel):
    customer: str
    weeks: int = Field(ge=8, le=MAX_WEEKS)
    sponsor: str
    phases: list[Phase]
    risks: list[RiskEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def phases_cover_the_term(self) -> Engagement:
        week = 1
        for phase in self.phases:
            if phase.first_week != week:
                raise ValueError(f"a gap in the calendar before phase {phase.name}")
            week = phase.last_week + 1
        if week != self.weeks + 1:
            raise ValueError("the phases do not cover the term of the engagement")
        return self

    def gate(self, name: str) -> Gate:
        for phase in self.phases:
            if phase.gate is not None and phase.gate.name == name:
                return phase.gate
        raise KeyError(name)

    def expected_delay(self) -> float:
        return sum(r.expected_delay for r in self.risks)


def nordbank() -> Engagement:
    """Twelve weeks at Nordbank: six phases, six gates, three risks."""
    return Engagement(
        customer="Nordbank Regional",
        weeks=12,
        sponsor="Martin Hagen, chief technology officer",
        phases=[
            Phase(name="thin slice", first_week=1, last_week=1, gate=Gate(
                name="slice on synthetic data", week=1, owner="Martin Hagen",
                exit_criteria=["3 end-to-end answers on synthetic transcripts",
                               "1 demo to the sponsor on the first Friday"])),
            Phase(name="access and discovery", first_week=2, last_week=3, gate=Gate(
                name="access granted", week=3, owner="Eva Lann",
                exit_criteria=["2 accounts in the test environment",
                               "an export of 30 days of transcripts"])),
            Phase(name="integration", first_week=4, last_week=5, gate=Gate(
                name="pilot", week=5, owner="Per Ulsen",
                exit_criteria=["20 operators working in the pilot",
                               "p95 answer latency under 4 seconds"])),
            Phase(name="evaluation", first_week=6, last_week=7, gate=Gate(
                name="evaluation gate", week=7, owner="Siv Berg",
                exit_criteria=["a set of 200 labelled cases",
                               "share of correct source citations at least 0.9"])),
            Phase(name="production", first_week=8, last_week=9, gate=Gate(
                name="production", week=8, owner="Martin Hagen",
                exit_criteria=["1 queue served in production",
                               "on-call accepted by 2 of the bank's engineers"])),
            Phase(name="handover", first_week=10, last_week=12, gate=Gate(
                name="handover", week=12, owner="Per Ulsen",
                exit_criteria=["2 of the bank's engineers release on their own",
                               "0 open items in the decision log"])),
        ],
        risks=[
            RiskEntry(risk="the DLP review drags on", probability=0.5, delay_weeks=3,
                      owner="Eva Lann", mitigation="file on day 1, work on synthetic data"),
            RiskEntry(risk="the mainframe night window blocks the export", probability=0.3,
                      delay_weeks=1, owner="Siv Berg", mitigation="a 30-day mirror"),
            RiskEntry(risk="the sponsor changes the pilot queue", probability=0.2, delay_weeks=2,
                      owner="Martin Hagen", mitigation="decision log, review in week 2"),
        ],
    )


if __name__ == "__main__":
    plan = nordbank()
    assert plan.gate("production").week == 8          # production arrives before the end
    assert [p.gate.week for p in plan.phases if p.gate is not None] == [1, 3, 5, 7, 8, 12]
    assert round(plan.expected_delay(), 2) == 2.2     # expected delay in weeks
    try:
        Phase(name="demos", first_week=4, last_week=9)
        raise AssertionError("a phase without a gate must be rejected")
    except ValidationError as err:
        assert "has no gate" in str(err)
    try:
        Gate(name="success", week=5, owner="Per Ulsen", exit_criteria=["the agent works well"])
        raise AssertionError("a criterion without a number must be rejected")
    except ValidationError as err:
        assert "uncheckable" in str(err)
    print(len(plan.phases), "phases, each with its own gate; expected delay",
          round(plan.expected_delay(), 1), "weeks")
