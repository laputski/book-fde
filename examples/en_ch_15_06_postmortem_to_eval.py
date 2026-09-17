from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)
    incident_id: str
    trace_id: str
    question: str
    bad_citation: str
    expected_citation: str
    facts: tuple[str, ...]


class EvalCase(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    question: str
    expected_citation: str
    forbidden_citations: tuple[str, ...]
    facts: tuple[str, ...]
    slice: str
    provenance: str                                 # the incident and trace the case came from


class ActionItem(BaseModel):
    title: str = Field(min_length=10)
    owner: str = Field(min_length=3)                # the role or name of the action's owner
    due: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class Postmortem(BaseModel):
    incident_id: str
    causes: tuple[str, ...]                         # contributing causes in the system and process
    findings: tuple[Finding, ...]
    actions: tuple[ActionItem, ...] = Field(min_length=1)

    def blameless(self, staff: Sequence[str]) -> bool:
        return not any(name.lower() in cause.lower() for name in staff for cause in self.causes)


def to_cases(pm: Postmortem) -> list[EvalCase]:
    first: dict[str, Finding] = {}
    for f in pm.findings:                           # one question from many traces: one case
        first.setdefault(f"{f.question}|{f.expected_citation}", f)
    return [EvalCase(id="reg-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:8],
                     question=f.question, expected_citation=f.expected_citation,
                     forbidden_citations=(f.bad_citation,), facts=f.facts,
                     slice=f"regression/{f.incident_id}", provenance=f"{f.incident_id}/{f.trace_id}")
            for key, f in first.items()]


Ask = Callable[[str], tuple[str, tuple[str, ...]]]


def passes(case: EvalCase, ask: Ask) -> bool:
    text, citations = ask(case.question)
    return (case.expected_citation in citations
            and not set(case.forbidden_citations) & set(citations)
            and all(fact.lower() in text.lower() for fact in case.facts))


def regression_gate(cases: Sequence[EvalCase], ask: Ask) -> list[str]:
    """Zero tolerance: any failed case from an incident blocks the release."""
    return [case.id for case in cases if not passes(case, ask)]


if __name__ == "__main__":
    questions = ["dosing under G-12, group A", "dosing under G-12, group B", "frequency under G-12"]
    traces = [(f"tr-{n:03d}", questions[n % 3]) for n in range(7)]
    pm = Postmortem(
        incident_id="INC-0914",
        causes=("the example answer in the prompt was written from a superseded edition",
                "the eval set has no questions on editions younger than 30 days",
                "the golden probes did not check the edition number in citations"),
        findings=tuple(Finding(incident_id="INC-0914", trace_id=t, question=q,
                               bad_citation="G-12@7#4.2", expected_citation="G-12@8#4.2",
                               facts=("group",)) for t, q in traces),
        actions=(ActionItem(title="check the editions in prompt examples when building a bundle",
                            owner="platform lead", due="2026-09-21"),))
    assert pm.blameless(staff=["Petrov", "Sidorova"])
    assert not pm.model_copy(update={"causes": ("Petrov's mistake while editing the prompt",)}).blameless(["Petrov"])
    try:
        ActionItem(title="sort out the prompts", owner="", due="soon")
        raise AssertionError("an action without an owner and a date was accepted")
    except ValidationError:
        pass

    cases = to_cases(pm)
    assert len(cases) == 3 and cases[0].provenance == "INC-0914/tr-000"

    def r119(question: str) -> tuple[str, tuple[str, ...]]:
        return f"{question}: group A, see the source", ("G-12@7#4.2",)

    def r120(question: str) -> tuple[str, tuple[str, ...]]:
        return f"{question}: group A, see the source", ("G-12@8#4.2",)

    assert regression_gate(cases, r119) == [case.id for case in cases]     # the R-119 prompt fails
    assert regression_gate(cases, r120) == []
    print("findings became cases with provenance; the regression slice holds zero tolerance")
