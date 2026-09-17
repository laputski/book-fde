from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Probe:
    id: str
    question: str
    expected_citation: str              # документ@редакция#раздел
    facts: tuple[str, ...]


@dataclass(frozen=True)
class Answer:
    text: str
    citations: tuple[str, ...]


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", text.lower()).split())


def parse(citation: str) -> tuple[str, str, str]:
    doc, rest = citation.split("@", 1)
    edition, section = rest.split("#", 1)
    return doc, edition, section


def fingerprint(probe: Probe, answer: Answer) -> str:
    """Класс ответа: не текст целиком, а то, что обязано совпасть."""
    doc, edition, _ = parse(probe.expected_citation)
    cited = [parse(c) for c in answer.citations]
    if not cited:
        return "no_citation"
    if any(d == doc and e != edition for d, e, _ in cited):
        return "wrong_edition"
    if probe.expected_citation not in answer.citations:
        return "wrong_source"
    text = normalize(answer.text)
    return "ok" if all(normalize(f) in text for f in probe.facts) else "facts_missing"


def shift(baseline: Counter[str], current: Counter[str]) -> float:
    """Расстояние полной вариации между двумя распределениями отпечатков."""
    nb, nc = sum(baseline.values()), sum(current.values())
    keys = baseline.keys() | current.keys()
    return sum(abs(baseline[k] / nb - current[k] / nc) for k in keys) / 2


@dataclass
class Canary:
    probes: Sequence[Probe]
    ask: Callable[[str], Answer]                    # тот же путь, что у вопроса клинициста
    now: Callable[[], float]
    baseline: Counter[str]                          # отпечатки на прогоне ворот этого bundle
    every_s: float = 900.0
    threshold: float = 0.10
    last_run: float = float("-inf")
    alerts: list[str] = field(default_factory=list)

    def tick(self, bundle_id: str) -> float | None:
        if self.now() - self.last_run < self.every_s:
            return None
        self.last_run = self.now()
        prints = {p.id: fingerprint(p, self.ask(p.question)) for p in self.probes}
        current = Counter(prints.values())
        distance = shift(self.baseline, current)
        if distance > self.threshold:
            classes = ", ".join(f"{k}={v}" for k, v in sorted(current.items()))
            broken = ", ".join(sorted(pid for pid, fp in prints.items() if fp != "ok"))
            self.alerts.append(f"{bundle_id}: сдвиг {distance:.2f}; {classes}; пробы {broken}")
        return distance


if __name__ == "__main__":
    probes = [Probe(f"p{i:02d}", f"вопрос {i} о дозировании по G-{10 + i % 4}",
                    f"G-{10 + i % 4}@8#4.{i % 3}", (f"факт {i}",)) for i in range(20)]
    by_question = {p.question: p for p in probes}
    live = {"prompt": "p-3f2a"}

    def ask(question: str) -> Answer:
        probe = by_question[question]
        citation = probe.expected_citation
        if live["prompt"] == "p-9c41" and citation.startswith("G-12@"):
            citation = citation.replace("@8#", "@7#")      # пример в промпте из редакции 7
        return Answer(f"Согласно источнику: {probe.facts[0]}.", (citation,))

    clock = {"t": 0.0}
    canary = Canary(probes, ask, now=lambda: clock["t"], baseline=Counter({"ok": 20}))
    assert canary.tick("R-118") == 0.0 and not canary.alerts
    live["prompt"] = "p-9c41"
    clock["t"] = 300.0
    assert canary.tick("R-119") is None                    # по расписанию ещё рано
    clock["t"] = 900.0
    assert canary.tick("R-119") == 0.25
    assert canary.alerts == ["R-119: сдвиг 0.25; ok=15, wrong_edition=5; пробы p02, p06, p10, p14, p18"]
    print("пробы по расписанию заметили сдвиг отпечатков и назвали пробы")
