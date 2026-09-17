from __future__ import annotations

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class Alternative(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    rejected_because: str = Field(min_length=20)


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True)
    number: int
    title: str
    status: Literal["proposed", "accepted", "superseded"] = "proposed"
    decided_on: date
    point: int | None = None                  # точка вариации, значение которой фиксирует решение
    context: str
    drivers: tuple[str, ...]
    decision: str
    alternatives: tuple[Alternative, ...]
    consequences: tuple[str, ...]
    reversal_weeks: int = Field(ge=0)         # сколько стоит отменить решение
    reversal_usd: int = Field(ge=0)
    review_on: date

    @model_validator(mode="after")
    def is_a_choice(self) -> Self:
        problems: list[str] = []
        if not self.alternatives:
            problems.append("нет альтернатив: неизвестно, из чего делался выбор")
        if not self.drivers:
            problems.append("нет драйверов: неизвестно, когда решение устареет")
        if not self.consequences:
            problems.append("нет последствий: цена решения скрыта")
        if self.review_on <= self.decided_on:
            problems.append("дата пересмотра должна быть позже даты решения")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def render(d: Decision) -> str:
    point = f" · точка вариации {d.point}" if d.point is not None else ""
    lines = [f"# ADR-{d.number:03d}: {d.title}",
             f"Статус: {d.status} · {d.decided_on} · пересмотр {d.review_on}{point}",
             "", "## Контекст", d.context, "", "## Драйверы", *[f"- {x}" for x in d.drivers],
             "", "## Решение", d.decision, "", "## Рассмотренные альтернативы",
             *[f"- {a.name}: отвергнута, потому что {a.rejected_because}" for a in d.alternatives],
             "", "## Последствия", *[f"- {x}" for x in d.consequences],
             "", "## Цена отмены", f"{d.reversal_weeks} недель, около {d.reversal_usd:,} долларов"]
    return "\n".join(lines)


def due(decisions: list[Decision], today: date) -> list[int]:
    return [d.number for d in decisions if d.status == "accepted" and d.review_on <= today]


if __name__ == "__main__":
    adr = Decision(
        number=7, title="Эндпоинт модели для дел жителей", status="accepted",
        decided_on=date(2026, 9, 14), point=2,
        context="Объём растёт на 12 % в месяц; команда эксплуатации города составляет 1.5 ставки.",
        drivers=("стабильность объёма", "резидентность", "эксплуатация"),
        decision="Региональный эндпоинт с оплатой за токены внутри сервисного периметра.",
        alternatives=(Alternative(name="provisioned", rejected_because="стабильной базы объёма ещё нет, "
                                  "пересечение ожидается на десятом месяце"),
                      Alternative(name="open_weights", rejected_because="требует 1.5 ставки дежурств, "
                                  "которых у города нет")),
        consequences=("счёт растёт вместе с объёмом до пересмотра", "промпты настраиваются под одну модель"),
        reversal_weeks=6, reversal_usd=60_000, review_on=date(2027, 5, 14))
    text = render(adr)
    assert text.startswith("# ADR-007:") and "точка вариации 2" in text
    assert text.count("отвергнута, потому что") == 2
    assert due([adr], date(2027, 5, 1)) == [] and due([adr], date(2027, 5, 14)) == [7]
    try:
        Decision.model_validate(adr.model_dump() | {"alternatives": (), "review_on": date(2026, 9, 1)})
    except ValidationError as err:
        assert "нет альтернатив" in str(err) and "дата пересмотра" in str(err)
    else:
        raise AssertionError("решение без альтернатив обязано быть отвергнуто")
    print(text.splitlines()[0], "· строк в документе:", len(text.splitlines()))
