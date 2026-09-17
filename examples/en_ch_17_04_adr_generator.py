from __future__ import annotations

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class Alternative(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    rejected_because: str = Field(min_length=20)


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True)
    number: int
    title: str
    status: Literal["proposed", "accepted", "superseded"] = "proposed"
    decided_on: date
    point: int | None = None                  # the variation point whose value the decision fixes
    context: str
    drivers: tuple[str, ...]
    decision: str
    alternatives: tuple[Alternative, ...]
    consequences: tuple[str, ...]
    reversal_weeks: int = Field(ge=0)         # what undoing the decision costs
    reversal_usd: int = Field(ge=0)
    review_on: date

    @model_validator(mode="after")
    def is_a_choice(self) -> Self:
        problems: list[str] = []
        if not self.alternatives:
            problems.append("no alternatives: the options of the choice are unknown")
        if not self.drivers:
            problems.append("no drivers: nobody knows when the decision expires")
        if not self.consequences:
            problems.append("no consequences: the price of the decision is hidden")
        if self.review_on <= self.decided_on:
            problems.append("the review date must follow the decision date")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def render(d: Decision) -> str:
    point = f" · variation point {d.point}" if d.point is not None else ""
    lines = [f"# ADR-{d.number:03d}: {d.title}",
             f"Status: {d.status} · {d.decided_on} · review {d.review_on}{point}",
             "", "## Context", d.context, "", "## Drivers", *[f"- {x}" for x in d.drivers],
             "", "## Decision", d.decision, "", "## Alternatives considered",
             *[f"- {a.name}: rejected because {a.rejected_because}" for a in d.alternatives],
             "", "## Consequences", *[f"- {x}" for x in d.consequences],
             "", "## Reversal cost", f"{d.reversal_weeks} weeks, about {d.reversal_usd:,} dollars"]
    return "\n".join(lines)


def due(decisions: list[Decision], today: date) -> list[int]:
    return [d.number for d in decisions if d.status == "accepted" and d.review_on <= today]


if __name__ == "__main__":
    adr = Decision(
        number=7, title="Model endpoint for resident cases", status="accepted",
        decided_on=date(2026, 9, 14), point=2,
        context="Volume grows by 12% a month; the city's operations team is 1.5 FTE.",
        drivers=("volume stability", "residency", "operations"),
        decision="A regional pay-per-token endpoint inside the service perimeter.",
        alternatives=(Alternative(name="provisioned", rejected_because="there is no stable volume base yet, "
                                  "the crossover is expected in month ten"),
                      Alternative(name="open_weights", rejected_because="it needs 1.5 FTE of on-call "
                                  "that the city does not have")),
        consequences=("the bill grows with volume until the review", "prompts are tuned to one model"),
        reversal_weeks=6, reversal_usd=60_000, review_on=date(2027, 5, 14))
    text = render(adr)
    assert text.startswith("# ADR-007:") and "variation point 2" in text
    assert text.count("rejected because") == 2
    assert due([adr], date(2027, 5, 1)) == [] and due([adr], date(2027, 5, 14)) == [7]
    try:
        Decision.model_validate(adr.model_dump() | {"alternatives": (), "review_on": date(2026, 9, 1)})
    except ValidationError as err:
        assert "no alternatives" in str(err) and "review date" in str(err)
    else:
        raise AssertionError("a decision without alternatives must be rejected")
    print(text.splitlines()[0], "· lines in the record:", len(text.splitlines()))
