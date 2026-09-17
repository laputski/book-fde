from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel


class Facts(BaseModel):
    """What the workers established: the only source of numbers and times for the draft."""

    subscribers: int
    district: str
    eta_known: bool


@dataclass(frozen=True)
class Criterion:
    code: str
    check: Callable[[str, Facts], bool]
    hint: str


RUBRIC: tuple[Criterion, ...] = (
    Criterion("no_internal_names", lambda text, f: re.search(r"\b(?:core|agg)-\S+", text) is None,
              "remove internal node names"),
    Criterion("numbers_match_facts", lambda text, f: str(f.subscribers) in text,
              "take the subscriber count from the impact assessment"),
    Criterion("no_unfounded_eta", lambda text, f: f.eta_known or "restored by" not in text,
              "do not promise a time the diagnosis does not contain"),
    Criterion("district_named", lambda text, f: f.district in text, "name the district"),
)


@dataclass(frozen=True)
class Draft:
    text: str
    rationale: str                          # the author's reasoning: never sent to the critic


@dataclass(frozen=True)
class Verdict:
    passed: bool
    violations: tuple[str, ...]


def critique(text: str, facts: Facts, rubric: Sequence[Criterion] = RUBRIC) -> Verdict:
    """The critic sees the text, the facts and the rubric. It never sees the author's reasoning."""
    failed = tuple(c.code for c in rubric if not c.check(text, facts))
    return Verdict(not failed, failed)


@dataclass
class ScriptedAuthor:
    """An author stub: the next scripted revision, and a record of the feedback received."""

    drafts: list[str]
    feedback_seen: list[tuple[str, ...]] = field(default_factory=list)

    def write(self, facts: Facts, feedback: tuple[str, ...]) -> Draft:
        self.feedback_seen.append(feedback)
        n = min(len(self.feedback_seen), len(self.drafts)) - 1
        return Draft(self.drafts[n], rationale="the draft satisfies every requirement")


@dataclass(frozen=True)
class Outcome:
    text: str
    revisions: int
    unresolved: tuple[str, ...]


def reflect(author: ScriptedAuthor, facts: Facts, max_revisions: int = 2) -> Outcome:
    feedback: tuple[str, ...] = ()
    best, unresolved = "", tuple(c.code for c in RUBRIC)
    for revision in range(max_revisions + 1):
        draft = author.write(facts, feedback)
        verdict = critique(draft.text, facts)
        if len(verdict.violations) < len(unresolved) or not best:
            best, unresolved = draft.text, verdict.violations
        if verdict.passed:
            return Outcome(draft.text, revision, ())
        feedback = tuple(c.hint for c in RUBRIC if c.code in verdict.violations)
    return Outcome(best, max_revisions, unresolved)     # the best version and its open issues


if __name__ == "__main__":
    facts = Facts(subscribers=18220, district="Riverside", eta_known=False)
    author = ScriptedAuthor([
        "core-rtr-07 failure, service restored by 15:00.",
        "Outage in Riverside: 18220 subscribers affected, service restored by 15:00.",
        "Mobile service outage in Riverside: 18220 subscribers affected. Work is under way.",
    ])
    out = reflect(author, facts)
    assert out.revisions == 2 and out.unresolved == ()
    assert author.feedback_seen[1] == ("remove internal node names",
                                       "take the subscriber count from the impact assessment",
                                       "do not promise a time the diagnosis does not contain",
                                       "name the district")
    assert author.feedback_seen[2] == ("do not promise a time the diagnosis does not contain",)

    stubborn = ScriptedAuthor(["core-rtr-07 failure, service restored by 15:00."])
    capped = reflect(stubborn, facts, max_revisions=2)
    assert len(stubborn.feedback_seen) == 3                # one attempt and two revisions, no more
    assert capped.unresolved == tuple(c.code for c in RUBRIC)
    print("a rubric, an independent critic and a revision cap: the draft is fixed in two revisions")
