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
    provenance: str                                 # инцидент и трасса, откуда пришёл пример


class ActionItem(BaseModel):
    title: str = Field(min_length=10)
    owner: str = Field(min_length=3)                # роль или имя владельца действия
    due: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class Postmortem(BaseModel):
    incident_id: str
    causes: tuple[str, ...]                         # способствующие причины в системе и процессе
    findings: tuple[Finding, ...]
    actions: tuple[ActionItem, ...] = Field(min_length=1)

    def blameless(self, staff: Sequence[str]) -> bool:
        return not any(name.lower() in cause.lower() for name in staff for cause in self.causes)


def to_cases(pm: Postmortem) -> list[EvalCase]:
    first: dict[str, Finding] = {}
    for f in pm.findings:                           # один вопрос из разных трасс: один пример
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
    """Нулевой допуск: любой проваленный пример из инцидента блокирует выпуск."""
    return [case.id for case in cases if not passes(case, ask)]


if __name__ == "__main__":
    questions = ["дозирование по G-12, группа A", "дозирование по G-12, группа B", "кратность по G-12"]
    traces = [(f"tr-{n:03d}", questions[n % 3]) for n in range(7)]
    pm = Postmortem(
        incident_id="INC-0914",
        causes=("пример ответа в промпте составлен по отменённой редакции",
                "в оценочном наборе нет вопросов по редакциям младше 30 дней",
                "золотые пробы не проверяли номер редакции в цитате"),
        findings=tuple(Finding(incident_id="INC-0914", trace_id=t, question=q,
                               bad_citation="G-12@7#4.2", expected_citation="G-12@8#4.2",
                               facts=("группа",)) for t, q in traces),
        actions=(ActionItem(title="проверять редакции в примерах промпта при сборке bundle",
                            owner="руководитель платформы", due="2026-09-21"),))
    assert pm.blameless(staff=["Петров", "Сидорова"])
    assert not pm.model_copy(update={"causes": ("ошибка Петрова при правке промпта",)}).blameless(["Петров"])
    try:
        ActionItem(title="разобраться с промптами", owner="", due="скоро")
        raise AssertionError("действие без владельца и срока принято")
    except ValidationError:
        pass

    cases = to_cases(pm)
    assert len(cases) == 3 and cases[0].provenance == "INC-0914/tr-000"

    def r119(question: str) -> tuple[str, tuple[str, ...]]:
        return f"{question}: группа A, см. источник", ("G-12@7#4.2",)

    def r120(question: str) -> tuple[str, tuple[str, ...]]:
        return f"{question}: группа A, см. источник", ("G-12@8#4.2",)

    assert regression_gate(cases, r119) == [case.id for case in cases]     # промпт R-119 не пройдёт
    assert regression_gate(cases, r120) == []
    print("находки стали примерами с происхождением, регрессионный срез держит нулевой допуск")
