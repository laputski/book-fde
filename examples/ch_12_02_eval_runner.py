from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict


class Example(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    question: str
    facts: tuple[str, ...]          # что обязано прозвучать в ответе
    sources: tuple[str, ...]        # документы, на которые разрешено ссылаться
    slice: str                      # очередь контакт-центра
    trace_id: str                   # происхождение: трасса production
    rubric: str                     # версия инструкции разметчика


class EvalSet(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    version: str
    examples: tuple[Example, ...]

    def digest(self) -> str:
        rows = [e.model_dump(mode="json") for e in self.examples]
        payload = json.dumps(rows, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class Manifest(BaseModel):
    model_config = ConfigDict(frozen=True)
    model_version: str
    prompt_hash: str
    index_version: str
    toolset_version: str
    eval_set: str                   # имя@версия
    eval_digest: str


class Response(BaseModel):
    text: str
    citations: tuple[str, ...]
    latency_ms: float


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^\w%€]+", " ", text.lower()).split())


Metric = Callable[[Example, Response], float]
METRICS: dict[str, tuple[Metric, str]] = {}          # имя -> (функция, агрегат)


def metric(name: str, aggregate: str = "mean") -> Callable[[Metric], Metric]:
    def register(fn: Metric) -> Metric:
        METRICS[name] = (fn, aggregate)
        return fn
    return register


@metric("fact_recall")
def fact_recall(ex: Example, r: Response) -> float:
    text = normalize(r.text)
    return sum(normalize(f) in text for f in ex.facts) / len(ex.facts)


@metric("grounded")
def grounded(ex: Example, r: Response) -> float:
    return float(bool(r.citations) and set(r.citations) <= set(ex.sources))


@metric("policy")
def policy(ex: Example, r: Response) -> float:
    return float(re.search(r"рекоменду\w* (вложить|инвестировать)", r.text.lower()) is None)


@metric("latency_ms", aggregate="p95")
def latency(ex: Example, r: Response) -> float:
    return r.latency_ms


def aggregate(values: Sequence[float], how: str) -> float:
    if how == "p95":
        ordered = sorted(values)
        return ordered[math.ceil(0.95 * len(ordered)) - 1]
    return sum(values) / len(values)


@dataclass(frozen=True)
class Threshold:
    metric: str
    bound: float
    upper: bool = False             # True: значение не должно превышать bound
    slice: str = "*"                # "*" означает весь набор


@dataclass
class Report:
    manifest: Manifest
    items: dict[str, dict[str, float]] = field(default_factory=dict)
    scores: dict[tuple[str, str], float] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations


def run(eval_set: EvalSet, system: Callable[[Example], Response], manifest: Manifest,
        thresholds: Sequence[Threshold]) -> Report:
    if manifest.eval_digest != eval_set.digest():
        raise ValueError("набор изменён без новой версии")
    report = Report(manifest)
    outputs = [(ex, system(ex)) for ex in eval_set.examples]
    for ex, r in outputs:
        report.items[ex.id] = {name: fn(ex, r) for name, (fn, _) in METRICS.items()}
    slices = [*sorted({ex.slice for ex in eval_set.examples}), "*"]
    for name, (_, how) in METRICS.items():
        for s in slices:
            rows = [report.items[ex.id][name] for ex in eval_set.examples if s in ("*", ex.slice)]
            report.scores[(s, name)] = aggregate(rows, how)
    for t in thresholds:
        value = report.scores[(t.slice, t.metric)]
        if (value > t.bound) if t.upper else (value < t.bound):
            report.violations.append(f"{t.metric}[{t.slice}] = {value:.2f}, порог {t.bound}")
    return report


if __name__ == "__main__":
    def ex(i: str, q: str, facts: tuple[str, ...], src: str, s: str) -> Example:
        return Example(id=i, question=q, facts=facts, sources=(src,), slice=s,
                       trace_id=f"tr-{i}", rubric="r3")

    def said(text: str, src: str, ms: float) -> Response:
        return Response(text=text, citations=(src,), latency_ms=ms)

    ev = EvalSet(name="nordbank-assist", version="2026.09.1", examples=(
        ex("e1", "Сколько рассматривается спор?", ("45 дней",), "kb/disputes", "cards"),
        ex("e2", "Лимит оплаты без PIN?", ("50 €",), "kb/cards", "cards"),
        ex("e3", "Что нужно для ипотеки?", ("справка о доходах", "договор"), "kb/mortgage", "mortgage"),
        ex("e4", "Лимит зарплатного реестра?", ("200 000 €",), "kb/business", "business"),
        ex("e5", "Куда вложить остаток?", ("не консультирует",), "kb/advice", "business"),
    ))
    answers = {
        "e1": said("Спор рассматривается не дольше 45 дней.", "kb/disputes", 900),
        "e2": said("Без PIN можно оплатить до 50 € за покупку.", "kb/cards", 700),
        "e3": said("Нужны паспорт, справка о доходах и договор.", "kb/mortgage", 1400),
        "e4": said("Реестр принимается до 200 000 € в сутки.", "kb/business", 1100),
        "e5": said("Рекомендую вложить остаток в фонд.", "kb/advice", 1800),
    }
    prompt = "Вы помощник оператора Nordbank. Отвечайте только по источникам."
    manifest = Manifest(model_version="model-pro-2026-06",
                        prompt_hash=hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12],
                        index_version="kb-idx-0914", toolset_version="tools-v7",
                        eval_set=f"{ev.name}@{ev.version}", eval_digest=ev.digest())
    thresholds = [Threshold("fact_recall", 0.75), Threshold("fact_recall", 0.75, slice="business"),
                  Threshold("grounded", 0.95), Threshold("policy", 1.0),
                  Threshold("latency_ms", 2500, upper=True)]
    report = run(ev, lambda e: answers[e.id], manifest, thresholds)

    assert report.items["e1"]["fact_recall"] == 1.0            # пересказ засчитан
    assert report.scores[("*", "fact_recall")] == 0.8          # весь набор проходит порог
    assert report.scores[("business", "fact_recall")] == 0.5   # срез не проходит
    assert report.scores[("*", "latency_ms")] == 1800
    assert not report.passed and len(report.violations) == 2
    shrunk = ev.model_copy(update={"examples": ev.examples[:4]})
    try:
        run(shrunk, lambda e: answers[e.id], manifest, thresholds)
        raise AssertionError("изменённый набор обязан быть отвергнут")
    except ValueError:
        pass
    print("ворота закрыты:", "; ".join(report.violations))
