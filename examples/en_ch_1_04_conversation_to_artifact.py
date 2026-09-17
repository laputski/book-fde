from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

CONFIDENCE = {"+": 0.9, "!": 0.5, "?": 0.2}   # measured, stated from memory, assumed

NOTE = """
source: Per Ulsen, head of the contact centre, week 1, day 2

A conversation about why an operator keeps three windows open at once.

+ 412 operators work across three shifts
! an operator spends up to 4 minutes collecting history from three systems
? average handling time equals 6 minutes 40 seconds @ AHT export for a quarter | Siv Berg
? half of the cases close without core banking @ labelling of 200 cases | Siv Berg
"""


class RequirementCandidate(BaseModel):
    """A requirement candidate: a claim with a source and a next step."""

    text: str = Field(min_length=8)
    source: str = Field(min_length=3)         # who said it and when
    confidence: float = Field(ge=0.0, le=1.0)
    follow_up: str = ""
    follow_up_owner: str = ""

    @model_validator(mode="after")
    def weak_claims_need_an_owner(self) -> RequirementCandidate:
        if self.confidence < 0.5 and not self.follow_up_owner:
            raise ValueError(f"a weak claim without a verification owner: {self.text}")
        return self


def read_note(note: str) -> list[RequirementCandidate]:
    """Parse the note: a "source:" line, then claims marked with + ! or ?."""
    source = ""
    rows: list[RequirementCandidate] = []
    for raw in note.strip().splitlines():
        line = raw.strip()
        if line.startswith("source:"):
            source = line.removeprefix("source:").strip()
            continue
        marker, _, rest = line.partition(" ")
        if marker not in CONFIDENCE:
            continue                          # the prose of the note yields no artifact
        claim, _, tail = rest.partition("@")
        follow_up, _, owner = tail.partition("|")
        rows.append(RequirementCandidate(
            text=claim.strip(),
            source=source,
            confidence=CONFIDENCE[marker],
            follow_up=follow_up.strip(),
            follow_up_owner=owner.strip(),
        ))
    return rows


if __name__ == "__main__":
    rows = read_note(NOTE)
    assert len(rows) == 4                     # four claims, the prose skipped
    assert all(r.source.startswith("Per Ulsen") for r in rows)
    assert [r.confidence for r in rows] == [0.9, 0.5, 0.2, 0.2]
    assert all(r.follow_up_owner == "Siv Berg" for r in rows if r.confidence < 0.5)
    try:
        RequirementCandidate(text="the operators dislike their tools",
                             source="a corridor conversation, week 1", confidence=0.2)
        raise AssertionError("a weak claim must be given a verification owner")
    except ValueError:
        pass
    print(len(rows), "requirement candidates: each with a source and a next step")
