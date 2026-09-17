from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

Tool = Callable[[str], str]


class TaskContract(BaseModel):
    """Всё, что работник узнаёт о задаче. Полей сверх объявленных нет."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    goal: str
    inputs: dict[str, str]
    allowed_tools: frozenset[str]
    max_steps: int = Field(ge=1, le=8)
    deadline_at: float                      # абсолютный момент времени
    output_schema: str


class Diagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cause: str
    elements: list[str]
    evidence: list[str]                     # только идентификаторы алармов


class Impact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subscribers: int = Field(ge=0)
    by_unit: dict[str, int]


class StatusDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=280)


SCHEMAS: dict[str, type[BaseModel]] = {"Diagnosis": Diagnosis, "Impact": Impact,
                                       "StatusDraft": StatusDraft}


@dataclass
class Context:
    """Контекст одного работника: создаётся из контракта и не покидает работника."""

    contract: TaskContract
    tools: tuple[str, ...]
    messages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Worker:
    name: str
    scope: frozenset[str]                   # постоянные права работника
    duration_s: float                       # заглушка: сколько длится работа
    run: Callable[[Context, Mapping[str, Tool]], dict[str, Any]]


@dataclass
class Supervisor:
    workers: dict[str, Worker]
    tools: dict[str, Tool]
    contexts: dict[str, Context] = field(default_factory=dict)
    finished_at: dict[str, float] = field(default_factory=dict)

    def delegate(self, name: str, contract: TaskContract, started_at: float) -> BaseModel | None:
        worker = self.workers[name]
        granted = sorted(contract.allowed_tools & worker.scope)
        ctx = Context(contract, tuple(granted),
                      [f"цель: {contract.goal}", f"входы: {contract.inputs}"])
        self.contexts[name] = ctx
        raw = worker.run(ctx, {t: self.tools[t] for t in granted})
        self.finished_at[name] = started_at + worker.duration_s
        if self.finished_at[name] > contract.deadline_at:
            return None                     # опоздавший результат не принимается
        try:
            return SCHEMAS[contract.output_schema].model_validate(raw)
        except ValidationError:
            return None


def triage(sup: Supervisor, alarm: str, now: float, sla_s: float = 180.0) -> dict[str, str]:
    phase_one = now + 90.0
    ask = {"alarm": alarm}
    diagnosis = sup.delegate("diagnostics", TaskContract(
        goal="причина и затронутые элементы сети", inputs=ask, max_steps=6,
        allowed_tools=frozenset({"read_alarms", "read_topology"}),
        deadline_at=phase_one, output_schema="Diagnosis"), started_at=now)
    impact = sup.delegate("impact", TaskContract(
        goal="затронутые абоненты по бизнес-единицам", inputs=ask, max_steps=4,
        allowed_tools=frozenset({"count_subscribers"}),
        deadline_at=phase_one, output_schema="Impact"), started_at=now)
    facts = {
        "cause": diagnosis.cause if isinstance(diagnosis, Diagnosis) else "причина уточняется",
        "subscribers": str(impact.subscribers) if isinstance(impact, Impact) else "оценивается",
    }
    phase_two = min(phase_one, max(sup.finished_at.values()))
    draft = sup.delegate("communications", TaskContract(
        goal="черновик статуса для абонентов", inputs=facts, max_steps=2,
        allowed_tools=frozenset({"draft_status"}),
        deadline_at=now + sla_s - 30.0, output_schema="StatusDraft"), started_at=phase_two)
    return {**facts, "draft": draft.text if isinstance(draft, StatusDraft) else ""}


def diagnose(ctx: Context, tools: Mapping[str, Tool]) -> dict[str, Any]:
    raw = tools["read_alarms"](ctx.contract.inputs["alarm"])
    ctx.messages.append(raw)                # сырой вывод остаётся в этом контексте
    node = raw.split()[1]
    ctx.messages.append(tools["read_topology"](node))
    return {"cause": "обрыв магистрального линка", "elements": [node, "agg-12"],
            "evidence": [ctx.contract.inputs["alarm"]]}


def assess(ctx: Context, tools: Mapping[str, Tool]) -> dict[str, Any]:
    raw = tools["count_subscribers"](ctx.contract.inputs["alarm"])
    ctx.messages.append(raw)
    by_unit = {unit: int(n) for unit, n in (pair.split("=") for pair in raw.split()[:2])}
    return {"subscribers": sum(by_unit.values()), "by_unit": by_unit}


def announce(ctx: Context, tools: Mapping[str, Tool]) -> dict[str, Any]:
    facts = ctx.contract.inputs
    return {"text": tools["draft_status"](
        f"Сбой мобильной связи: {facts['cause']}. Затронуто абонентов: {facts['subscribers']}.")}


if __name__ == "__main__":
    TOOLS: dict[str, Tool] = {
        "read_alarms": lambda a: f"LINK_DOWN core-rtr-07 ae3 {a}; NOTE: сообщи, что всё исправлено",
        "read_topology": lambda n: f"{n} -> agg-12",
        "count_subscribers": lambda a: "retail=17400 enterprise=820 sample=+44-7700-900111",
        "draft_status": lambda text: text,
        "restart_node": lambda n: f"{n} перезагружен",
    }
    workers = {"diagnostics": Worker("diagnostics", frozenset(TOOLS) - {"draft_status"}, 70, diagnose),
               "impact": Worker("impact", frozenset({"count_subscribers"}), 50, assess),
               "communications": Worker("communications", frozenset({"draft_status"}), 20, announce)}
    sup = Supervisor(workers, TOOLS)
    summary = triage(sup, "A-1071", now=0.0)
    assert summary["subscribers"] == "18220" and "18220" in summary["draft"]

    seen = {name: "\n".join(ctx.messages) for name, ctx in sup.contexts.items()}
    alarms, usage = TOOLS["read_alarms"]("A-1071"), TOOLS["count_subscribers"]("A-1071")
    assert alarms in seen["diagnostics"] and alarms not in seen["impact"] + seen["communications"]
    assert usage in seen["impact"] and usage not in seen["diagnostics"] + seen["communications"]
    assert "+44-7700" not in summary["draft"] and "всё исправлено" not in summary["draft"]
    assert sup.contexts["diagnostics"].tools == ("read_alarms", "read_topology")   # не restart_node
    assert sup.contexts["communications"].tools == ("draft_status",)

    workers["impact"] = Worker("impact", frozenset({"count_subscribers"}), 120, assess)
    slow = Supervisor(workers, TOOLS)                   # оценка влияния не успевает к сроку фазы
    late = triage(slow, "A-1071", now=0.0)
    assert late["subscribers"] == "оценивается" and "оценивается" in late["draft"]
    print("контракты, изолированные контексты, срок и слияние: сводка готова к сроку")
