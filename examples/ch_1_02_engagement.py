from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

MAX_WEEKS = 16


class Gate(BaseModel):
    """Ворота: проверяемое условие перехода с неделей и владельцем."""

    name: str
    week: int = Field(ge=1, le=MAX_WEEKS)
    owner: str = Field(min_length=3)          # имя конкретного человека
    exit_criteria: list[str] = Field(min_length=1)

    @field_validator("exit_criteria")
    @classmethod
    def measurable(cls, criteria: list[str]) -> list[str]:
        for line in criteria:
            if not any(ch.isdigit() for ch in line):
                raise ValueError(f"условие без числа непроверяемо: {line}")
        return criteria


class Phase(BaseModel):
    name: str
    first_week: int = Field(ge=1, le=MAX_WEEKS)
    last_week: int = Field(ge=1, le=MAX_WEEKS)
    gate: Gate | None = None

    @model_validator(mode="after")
    def gate_required(self) -> Phase:
        if self.gate is None:
            raise ValueError(f"фаза {self.name} не имеет ворот")
        if not self.first_week <= self.gate.week <= self.last_week:
            raise ValueError(f"ворота {self.gate.name} лежат вне своей фазы")
        return self


class RiskEntry(BaseModel):
    risk: str
    probability: float = Field(ge=0.0, le=1.0)
    delay_weeks: int = Field(ge=0)
    owner: str
    mitigation: str

    @property
    def expected_delay(self) -> float:
        return self.probability * self.delay_weeks


class Engagement(BaseModel):
    customer: str
    weeks: int = Field(ge=8, le=MAX_WEEKS)
    sponsor: str
    phases: list[Phase]
    risks: list[RiskEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def phases_cover_the_term(self) -> Engagement:
        week = 1
        for phase in self.phases:
            if phase.first_week != week:
                raise ValueError(f"разрыв в календаре перед фазой {phase.name}")
            week = phase.last_week + 1
        if week != self.weeks + 1:
            raise ValueError("фазы не покрывают срок engagement")
        return self

    def gate(self, name: str) -> Gate:
        for phase in self.phases:
            if phase.gate is not None and phase.gate.name == name:
                return phase.gate
        raise KeyError(name)

    def expected_delay(self) -> float:
        return sum(r.expected_delay for r in self.risks)


def nordbank() -> Engagement:
    """Двенадцать недель в Nordbank: шесть фаз, шесть ворот, три риска."""
    return Engagement(
        customer="Nordbank Regional",
        weeks=12,
        sponsor="Мартин Хаген, технический директор",
        phases=[
            Phase(name="тонкий срез", first_week=1, last_week=1, gate=Gate(
                name="срез на синтетике", week=1, owner="Мартин Хаген",
                exit_criteria=["3 сквозных ответа на синтетических транскриптах",
                               "1 демонстрация спонсору в первую пятницу"])),
            Phase(name="доступ и discovery", first_week=2, last_week=3, gate=Gate(
                name="доступ выдан", week=3, owner="Ева Ланн",
                exit_criteria=["2 учётные записи в тестовом контуре",
                               "выгрузка транскриптов за 30 дней"])),
            Phase(name="интеграция", first_week=4, last_week=5, gate=Gate(
                name="пилот", week=5, owner="Пер Ульсен",
                exit_criteria=["20 операторов работают в пилоте",
                               "p95 ответа ниже 4 секунд"])),
            Phase(name="оценка", first_week=6, last_week=7, gate=Gate(
                name="ворота оценки", week=7, owner="Сив Берг",
                exit_criteria=["набор из 200 размеченных обращений",
                               "доля верных ссылок на источник не ниже 0.9"])),
            Phase(name="production", first_week=8, last_week=9, gate=Gate(
                name="production", week=8, owner="Мартин Хаген",
                exit_criteria=["1 очередь обслуживается в production",
                               "дежурство принято на 2 инженеров банка"])),
            Phase(name="передача", first_week=10, last_week=12, gate=Gate(
                name="передача", week=12, owner="Пер Ульсен",
                exit_criteria=["2 инженера банка ведут выкладку сами",
                               "0 открытых пунктов в журнале решений"])),
        ],
        risks=[
            RiskEntry(risk="ревью DLP затягивается", probability=0.5, delay_weeks=3,
                      owner="Ева Ланн", mitigation="заявка в день 1, работа на синтетике"),
            RiskEntry(risk="ночное окно mainframe закрывает выгрузку", probability=0.3,
                      delay_weeks=1, owner="Сив Берг", mitigation="зеркало за 30 дней"),
            RiskEntry(risk="спонсор меняет очередь пилота", probability=0.2, delay_weeks=2,
                      owner="Мартин Хаген", mitigation="журнал решений, пересмотр на неделе 2"),
        ],
    )


if __name__ == "__main__":
    plan = nordbank()
    assert plan.gate("production").week == 8          # production наступает раньше конца
    assert [p.gate.week for p in plan.phases if p.gate is not None] == [1, 3, 5, 7, 8, 12]
    assert round(plan.expected_delay(), 2) == 2.2     # ожидаемая задержка в неделях
    try:
        Phase(name="демонстрации", first_week=4, last_week=9)
        raise AssertionError("фаза без ворот обязана быть отвергнута")
    except ValidationError as err:
        assert "не имеет ворот" in str(err)
    try:
        Gate(name="успех", week=5, owner="Пер Ульсен", exit_criteria=["агент работает хорошо"])
        raise AssertionError("условие без числа обязано быть отвергнуто")
    except ValidationError as err:
        assert "непроверяемо" in str(err)
    print(len(plan.phases), "фаз, у каждой свои ворота; ожидаемая задержка",
          round(plan.expected_delay(), 1), "недели")
