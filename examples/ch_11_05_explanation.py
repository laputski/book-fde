from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Span(BaseModel):
    span_id: str
    seq: int                                    # порядок в трассе запуска
    kind: Literal["retrieval", "tool", "policy"]
    name: str
    detail: str
    user_may_open: bool = True


class Claim(BaseModel):
    text: str
    evidence: list[str]                         # идентификаторы span из трассы


class Explanation(BaseModel):
    run_id: str
    claims: list[Claim]
    sources: list[str]
    tools: list[str]
    policies: list[str]
    withheld: int                               # опоры, которые пользователь не вправе открыть


class Unsupported(ValueError):
    pass


def explain(run_id: str, trace: list[Span], decided_at: int, claims: list[Claim]) -> Explanation:
    """Объяснение собирается из трассы; утверждение без опоры в ней отвергается."""
    by_id = {span.span_id: span for span in trace}
    used: dict[str, Span] = {}
    for claim in claims:
        if not claim.evidence:
            raise Unsupported(f"нет опоры: {claim.text}")
        for span_id in claim.evidence:
            span = by_id.get(span_id)
            if span is None:
                raise Unsupported(f"{claim.text}: в трассе нет {span_id}")
            if span.seq >= decided_at:
                raise Unsupported(f"{claim.text}: {span_id} появился после решения")
            used[span_id] = span

    def shown(kind: str) -> list[str]:
        return [f"{s.name}: {s.detail}" for s in used.values() if s.kind == kind and s.user_may_open]

    return Explanation(run_id=run_id, claims=claims, sources=shown("retrieval"), tools=shown("tool"),
                       policies=shown("policy"),
                       withheld=sum(not s.user_may_open for s in used.values()))


if __name__ == "__main__":
    trace = [
        Span(span_id="s1", seq=1, kind="retrieval", name="Протокол «Сепсис у взрослых»",
             detail="ред. 2026-03, раздел 3.2"),
        Span(span_id="s2", seq=2, kind="tool", name="get_allergies", detail="аллергий не найдено"),
        Span(span_id="s3", seq=3, kind="retrieval", name="Заключение психиатра", detail="2025-11",
             user_may_open=False),
        Span(span_id="s4", seq=4, kind="policy", name="order.medication",
             detail="назначение требует одобрения врача"),
        Span(span_id="s5", seq=6, kind="retrieval", name="Формуляр аптеки", detail="цефтриаксон"),
    ]
    claims = [
        Claim(text="Показана антибактериальная терапия в первый час", evidence=["s1"]),
        Claim(text="Противопоказаний по аллергиям нет", evidence=["s2", "s3"]),
        Claim(text="Назначение ждёт вашего одобрения", evidence=["s4"]),
    ]
    exp = explain("run-12", trace, decided_at=5, claims=claims)
    assert exp.sources == ["Протокол «Сепсис у взрослых»: ред. 2026-03, раздел 3.2"]
    assert exp.tools == ["get_allergies: аллергий не найдено"] and exp.withheld == 1
    assert all(any(s.detail in line for s in trace) for line in exp.sources + exp.tools + exp.policies)

    for bad in (Claim(text="Пациентка не беременна", evidence=[]),
                Claim(text="Функция почек в норме", evidence=["s9"]),
                Claim(text="Препарат есть в формуляре", evidence=["s5"])):
        try:
            explain("run-12", trace, decided_at=5, claims=[bad])
            raise AssertionError(f"пропущено: {bad.text}")
        except Unsupported:
            pass
    print("объяснение состоит только из того, что есть в трассе до решения")
