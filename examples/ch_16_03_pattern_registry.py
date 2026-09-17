from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum

EVIDENCE_KINDS = ("decision:", "commit:", "trace:", "eval:")


class Kind(StrEnum):
    PROBLEM = "проблема"          # повторяющаяся задача пользователя
    CONSTRAINT = "ограничение"    # повторяющееся ограничение среды
    SOLUTION = "решение"          # повторяющаяся форма решения


@dataclass(frozen=True)
class Occurrence:
    engagement: str               # код досье: "CF1"
    kind: Kind
    evidence: str                 # запись журнала, коммит, трасса или прогон оценки
    workaround_hours: int = 0     # часы на обход ограничения продукта, по журналу времени


@dataclass
class Pattern:
    id: str
    title: str
    occurrences: list[Occurrence] = field(default_factory=list)

    def engagements(self, kind: Kind) -> set[str]:
        return {o.engagement for o in self.occurrences if o.kind == kind}

    def promotion_blockers(self, threshold: int = 3) -> list[str]:
        """Пустой список означает, что паттерн готов стать модулем."""
        blockers = [f"{kind}: {len(self.engagements(kind))} из {threshold}"
                    for kind in Kind if len(self.engagements(kind)) < threshold]
        unverifiable = [o.engagement for o in self.occurrences
                        if not o.evidence.startswith(EVIDENCE_KINDS)]
        if unverifiable:
            blockers.append(f"вхождения без проверяемой ссылки: {sorted(set(unverifiable))}")
        return blockers


@dataclass
class PatternRegistry:
    patterns: dict[str, Pattern] = field(default_factory=dict)

    def record(self, pattern_id: str, title: str, occurrence: Occurrence) -> None:
        pattern = self.patterns.setdefault(pattern_id, Pattern(pattern_id, title))
        if occurrence not in pattern.occurrences:          # повторный разбор не удваивает счёт
            pattern.occurrences.append(occurrence)

    def promotable(self) -> list[str]:
        return sorted(pid for pid, p in self.patterns.items() if not p.promotion_blockers())

    def workaround_hours(self, pattern_id: str) -> dict[str, int]:
        hours: defaultdict[str, int] = defaultdict(int)
        for o in self.patterns[pattern_id].occurrences:
            hours[o.engagement] += o.workaround_hours
        return dict(hours)


if __name__ == "__main__":
    reg = PatternRegistry()
    approval, residency = "одобрение, привязанное к аргументам", "данные только в регионе"
    for cf, action, hours in (("CF1", "create_dispute", 140), ("CF4", "publish_status", 96),
                              ("CF5", "submit_request", 120)):
        reg.record("approval", approval, Occurrence(cf, Kind.PROBLEM, f"decision:{cf}-{action}"))
        reg.record("approval", approval, Occurrence(cf, Kind.CONSTRAINT, f"eval:{cf}-approvals"))
        reg.record("approval", approval, Occurrence(cf, Kind.SOLUTION, f"commit:{cf}-{action}", hours))
    reg.record("approval", approval, Occurrence("CF1", Kind.PROBLEM, "decision:CF1-create_dispute"))
    for cf in ("CF1", "CF5"):
        reg.record("residency", residency, Occurrence(cf, Kind.CONSTRAINT, f"decision:{cf}-dpo"))
        reg.record("residency", residency, Occurrence(cf, Kind.SOLUTION, f"commit:{cf}-region"))
    reg.record("residency", residency, Occurrence("CF4", Kind.PROBLEM, "по словам команды"))

    assert len(reg.patterns["approval"].occurrences) == 9 and reg.promotable() == ["approval"]
    assert reg.workaround_hours("approval") == {"CF1": 140, "CF4": 96, "CF5": 120}
    blockers = reg.patterns["residency"].promotion_blockers()
    assert "проблема: 1 из 3" in blockers and "ограничение: 2 из 3" in blockers
    assert any("CF4" in b for b in blockers)
    print("к модулю готов:", reg.promotable(), "· residency ждёт:", blockers)
