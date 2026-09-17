from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Evidence:
    engagement: str                   # код досье затронутого заказчика
    workaround_hours: int             # измерено по журналу времени
    links: tuple[str, ...]            # трассы, прогоны оценки, записи журнала решений


@dataclass(frozen=True)
class FeatureRequest:
    title: str
    problem: str
    proposed_interface: str
    if_not_built: str
    evidence: tuple[Evidence, ...] = ()

    def refusals(self) -> list[str]:
        found: list[str] = []
        if not self.evidence:
            found.append("не названы затронутые заказчики")
        found += [f"{e.engagement}: стоимость обхода не измерена"
                  for e in self.evidence if e.workaround_hours <= 0]
        found += [f"{e.engagement}: нет ссылок на трассы или оценки"
                  for e in self.evidence if not e.links]
        return found

    def render(self, hourly_cost: int) -> str:
        if problems := self.refusals():
            raise ValueError("заявка отклонена: " + "; ".join(problems))
        hours = sum(e.workaround_hours for e in self.evidence)
        rows = [f"- {e.engagement}: {e.workaround_hours} ч; {', '.join(e.links)}"
                for e in sorted(self.evidence, key=lambda e: e.engagement)]
        return "\n".join([
            f"# {self.title}",
            f"Проблема: {self.problem}",
            f"Затронуто заказчиков: {len(self.evidence)}",
            f"Стоимость обхода: {hours} ч, {hours * hourly_cost} EUR",
            "Доказательства:", *rows,
            f"Предлагаемый интерфейс: {self.proposed_interface}",
            f"Если не строить: {self.if_not_built}",
        ])


if __name__ == "__main__":
    request = FeatureRequest(
        title="Одобрение, привязанное к аргументам, как примитив платформы",
        problem="прерывание одобрения содержит имя действия, но не его аргументы и срок",
        proposed_interface="interrupt(action, args_hash, approver_role, ttl_s) -> ApprovalToken",
        if_not_built="каждое engagement пишет свою обёртку; дефект обёртки исправляется N раз",
        evidence=(Evidence("CF4", 96, ("trace:or-0412", "eval:or-approvals@3")),
                  Evidence("CF1", 140, ("decision:D-31", "eval:nb-approvals@5")),
                  Evidence("CF5", 120, ("trace:ng-0907", "decision:D-12"))),
    )
    text = request.render(hourly_cost=95)
    assert "Стоимость обхода: 356 ч, 33820 EUR" in text
    assert text.index("- CF1") < text.index("- CF4") < text.index("- CF5")
    for broken, reason in ((FeatureRequest("x", "y", "z", "w"), "не названы"),
                           (FeatureRequest("x", "y", "z", "w", (Evidence("CF1", 0, ("trace:1",)),)),
                            "не измерена")):
        try:
            broken.render(hourly_cost=95)
            raise AssertionError("заявка без доказательств принята")
        except ValueError as err:
            assert reason in str(err)
    print(text.splitlines()[0], "· затронуто 3 заказчика, 356 ч обхода")
