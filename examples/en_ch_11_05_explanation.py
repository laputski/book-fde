from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Span(BaseModel):
    span_id: str
    seq: int                                    # order in the run's trace
    kind: Literal["retrieval", "tool", "policy"]
    name: str
    detail: str
    user_may_open: bool = True


class Claim(BaseModel):
    text: str
    evidence: list[str]                         # span ids from the trace


class Explanation(BaseModel):
    run_id: str
    claims: list[Claim]
    sources: list[str]
    tools: list[str]
    policies: list[str]
    withheld: int                               # evidence the user may not open


class Unsupported(ValueError):
    pass


def explain(run_id: str, trace: list[Span], decided_at: int, claims: list[Claim]) -> Explanation:
    """The explanation is assembled from the trace; a claim without evidence in it is rejected."""
    by_id = {span.span_id: span for span in trace}
    used: dict[str, Span] = {}
    for claim in claims:
        if not claim.evidence:
            raise Unsupported(f"no evidence: {claim.text}")
        for span_id in claim.evidence:
            span = by_id.get(span_id)
            if span is None:
                raise Unsupported(f"{claim.text}: {span_id} is not in the trace")
            if span.seq >= decided_at:
                raise Unsupported(f"{claim.text}: {span_id} appeared after the decision")
            used[span_id] = span

    def shown(kind: str) -> list[str]:
        return [f"{s.name}: {s.detail}" for s in used.values() if s.kind == kind and s.user_may_open]

    return Explanation(run_id=run_id, claims=claims, sources=shown("retrieval"), tools=shown("tool"),
                       policies=shown("policy"),
                       withheld=sum(not s.user_may_open for s in used.values()))


if __name__ == "__main__":
    trace = [
        Span(span_id="s1", seq=1, kind="retrieval", name="Protocol 'Sepsis in adults'",
             detail="rev. 2026-03, section 3.2"),
        Span(span_id="s2", seq=2, kind="tool", name="get_allergies", detail="no allergies found"),
        Span(span_id="s3", seq=3, kind="retrieval", name="Psychiatric assessment", detail="2025-11",
             user_may_open=False),
        Span(span_id="s4", seq=4, kind="policy", name="order.medication",
             detail="an order requires clinician approval"),
        Span(span_id="s5", seq=6, kind="retrieval", name="Pharmacy formulary", detail="ceftriaxone"),
    ]
    claims = [
        Claim(text="Antibiotic therapy within the first hour is indicated", evidence=["s1"]),
        Claim(text="No allergy contraindications", evidence=["s2", "s3"]),
        Claim(text="The order awaits your approval", evidence=["s4"]),
    ]
    exp = explain("run-12", trace, decided_at=5, claims=claims)
    assert exp.sources == ["Protocol 'Sepsis in adults': rev. 2026-03, section 3.2"]
    assert exp.tools == ["get_allergies: no allergies found"] and exp.withheld == 1
    assert all(any(s.detail in line for s in trace) for line in exp.sources + exp.tools + exp.policies)

    for bad in (Claim(text="The patient is not pregnant", evidence=[]),
                Claim(text="Renal function is normal", evidence=["s9"]),
                Claim(text="The drug is on the formulary", evidence=["s5"])):
        try:
            explain("run-12", trace, decided_at=5, claims=[bad])
            raise AssertionError(f"let through: {bad.text}")
        except Unsupported:
            pass
    print("the explanation contains only what is in the trace before the decision")
