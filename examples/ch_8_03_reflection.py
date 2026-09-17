from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel


class Facts(BaseModel):
    """Установленное работниками: единственный источник чисел и сроков для черновика."""

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
              "уберите внутренние имена узлов"),
    Criterion("numbers_match_facts", lambda text, f: str(f.subscribers) in text,
              "число абонентов берётся из оценки влияния"),
    Criterion("no_unfounded_eta", lambda text, f: f.eta_known or "восстановим к" not in text,
              "не называйте срок, которого нет в диагнозе"),
    Criterion("district_named", lambda text, f: f.district in text, "назовите район"),
)


@dataclass(frozen=True)
class Draft:
    text: str
    rationale: str                          # рассуждение автора: критику не передаётся


@dataclass(frozen=True)
class Verdict:
    passed: bool
    violations: tuple[str, ...]


def critique(text: str, facts: Facts, rubric: Sequence[Criterion] = RUBRIC) -> Verdict:
    """Критик видит текст, факты и рубрику. Рассуждений автора он не видит."""
    failed = tuple(c.code for c in rubric if not c.check(text, facts))
    return Verdict(not failed, failed)


@dataclass
class ScriptedAuthor:
    """Заглушка автора: очередная ревизия по сценарию и запись полученных замечаний."""

    drafts: list[str]
    feedback_seen: list[tuple[str, ...]] = field(default_factory=list)

    def write(self, facts: Facts, feedback: tuple[str, ...]) -> Draft:
        self.feedback_seen.append(feedback)
        n = min(len(self.feedback_seen), len(self.drafts)) - 1
        return Draft(self.drafts[n], rationale="черновик соответствует всем требованиям")


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
    return Outcome(best, max_revisions, unresolved)     # лучшая версия и список недочётов


if __name__ == "__main__":
    facts = Facts(subscribers=18220, district="Заречье", eta_known=False)
    author = ScriptedAuthor([
        "Отказ core-rtr-07, восстановим к 15:00.",
        "Сбой связи в Заречье: затронуто 18220 абонентов, восстановим к 15:00.",
        "Сбой мобильной связи в Заречье: затронуто 18220 абонентов. Работы идут.",
    ])
    out = reflect(author, facts)
    assert out.revisions == 2 and out.unresolved == ()
    assert author.feedback_seen[1] == ("уберите внутренние имена узлов",
                                       "число абонентов берётся из оценки влияния",
                                       "не называйте срок, которого нет в диагнозе",
                                       "назовите район")
    assert author.feedback_seen[2] == ("не называйте срок, которого нет в диагнозе",)

    stubborn = ScriptedAuthor(["Отказ core-rtr-07, восстановим к 15:00."])
    capped = reflect(stubborn, facts, max_revisions=2)
    assert len(stubborn.feedback_seen) == 3                # одна попытка и две ревизии, не больше
    assert capped.unresolved == tuple(c.code for c in RUBRIC)
    print("рубрика, независимый критик и потолок ревизий: черновик исправлен за две ревизии")
