from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ConstraintKind(StrEnum):
    REGULATORY = "regulatory"            # закон, надзор, внутренняя политика
    DATA = "data"                        # состав, качество, срок хранения
    INFRASTRUCTURE = "infrastructure"    # сети, окна обслуживания, лимиты
    ORGANISATIONAL = "organisational"    # цепочка одобрения, календарь, бюджет
    HARDWARE = "hardware"                # где физически исполняется модель


FIXED = frozenset({ConstraintKind.REGULATORY, ConstraintKind.HARDWARE})


class Constraint(BaseModel):
    id: str
    kind: ConstraintKind
    statement: str
    source: str                          # роль и дата разговора
    verified: bool = False               # подтверждено документом
    mitigation: str = ""                 # как требование выполняется, не нарушая ограничение

    @property
    def negotiable(self) -> bool:
        return self.kind not in FIXED

    @property
    def blocking(self) -> bool:
        return not self.mitigation


class Requirement(BaseModel):
    id: str
    statement: str
    source: str
    metric: str = ""
    threshold: float | None = None
    dataset: str = ""
    value: int = Field(ge=0, le=5)
    feasibility: int = Field(ge=0, le=5)
    blast_radius: int = Field(ge=1, le=5)
    constrained_by: tuple[str, ...] = ()

    @property
    def missing(self) -> tuple[str, ...]:
        gaps: list[str] = []
        if not self.metric:
            gaps.append("метрика")
        if self.threshold is None:
            gaps.append("порог")
        if not self.dataset:
            gaps.append("набор данных")
        return tuple(gaps)

    @property
    def testable(self) -> bool:
        return not self.missing


def score(req: Requirement, limits: dict[str, Constraint]) -> float:
    """Ценность на единицу радиуса поражения; непроверяемое и заблокированное стоит нуль."""
    if not req.testable:
        return 0.0
    if any(limits[k].blocking for k in req.constrained_by if k in limits):
        return 0.0
    return round(req.value * req.feasibility / req.blast_radius, 2)


def rank(reqs: list[Requirement], limits: list[Constraint]) -> list[Requirement]:
    index = {c.id: c for c in limits}
    return sorted(reqs, key=lambda r: (-score(r, index), r.id))


if __name__ == "__main__":
    limits = [
        Constraint(id="K-1", kind=ConstraintKind.HARDWARE, verified=True,
                   source="директор по информационной безопасности, 6 марта",
                   statement="персональные данные обрабатываются только в регионе",
                   mitigation="региональный эндпоинт модели внутри периметра VPC"),
        Constraint(id="K-2", kind=ConstraintKind.REGULATORY, source="комплаенс, 7 марта", verified=True,
                   statement="решение, видимое клиенту, подтверждает человек"),
        Constraint(id="K-3", kind=ConstraintKind.INFRASTRUCTURE, source="владелец платформы, 6 марта",
                   statement="core banking недоступен с 02:00 до 04:00",
                   mitigation="инструмент отвечает «система недоступна до 04:00»"),
    ]
    candidates = [
        Requirement(id="R-7", source="руководитель контакт-центра, 5 марта",
                    statement="подсказывать оператору ответ по базе знаний",
                    metric="средняя длительность обработки, с", threshold=335.0,
                    dataset="400 звонков очереди «карты» за март",
                    value=5, feasibility=4, blast_radius=1, constrained_by=("K-1", "K-3")),
        Requirement(id="R-9", source="технический директор, 4 марта",
                    statement="ассистент должен быть точным",
                    value=5, feasibility=3, blast_radius=2),
        Requirement(id="R-12", source="технический директор, 4 марта",
                    statement="отвечать клиенту без участия оператора",
                    metric="доля обращений, закрытых без оператора", threshold=0.25,
                    dataset="30 дней входящих обращений",
                    value=5, feasibility=2, blast_radius=5, constrained_by=("K-2",)),
        Requirement(id="R-15", source="оператор, 6 марта",
                    statement="сохранять резюме звонка в CRM",
                    metric="доля резюме, принятых без правки", threshold=0.8,
                    dataset="200 звонков с разметкой супервизора",
                    value=3, feasibility=5, blast_radius=2, constrained_by=("K-1",)),
    ]
    index = {c.id: c for c in limits}
    assert candidates[1].missing == ("метрика", "порог", "набор данных")
    assert score(candidates[1], index) == 0.0             # непроверяемое пожелание
    assert candidates[2].testable and score(candidates[2], index) == 0.0
    assert score(candidates[3], index) == 7.5             # ограничение названо и снято проектом
    assert [c.id for c in limits if not c.negotiable] == ["K-1", "K-2"]
    order = [r.id for r in rank(candidates, limits)]
    assert order == ["R-7", "R-15", "R-12", "R-9"]
    print("ранжировано:", order, "· в пилот идёт", order[0])
