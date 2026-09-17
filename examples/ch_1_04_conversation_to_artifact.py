from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

CONFIDENCE = {"+": 0.9, "!": 0.5, "?": 0.2}   # измерено, названо по памяти, предположено

NOTE = """
источник: Пер Ульсен, руководитель контакт-центра, неделя 1, день 2

Разговор о том, почему оператор держит открытыми три окна одновременно.

+ 412 операторов работают в трёх сменах
! оператор тратит до 4 минут на сбор истории из трёх систем
? среднее время обработки равно 6 минутам 40 секундам @ выгрузка AHT за квартал | Сив Берг
? половина обращений закрывается без core banking @ разметка 200 обращений | Сив Берг
"""


class RequirementCandidate(BaseModel):
    """Кандидат в требование: утверждение с источником и следующим шагом."""

    text: str = Field(min_length=8)
    source: str = Field(min_length=3)         # кто сказал и когда
    confidence: float = Field(ge=0.0, le=1.0)
    follow_up: str = ""
    follow_up_owner: str = ""

    @model_validator(mode="after")
    def weak_claims_need_an_owner(self) -> RequirementCandidate:
        if self.confidence < 0.5 and not self.follow_up_owner:
            raise ValueError(f"слабое утверждение без владельца проверки: {self.text}")
        return self


def read_note(note: str) -> list[RequirementCandidate]:
    """Разобрать заметку: строка «источник:», далее утверждения с маркером + ! ?."""
    source = ""
    rows: list[RequirementCandidate] = []
    for raw in note.strip().splitlines():
        line = raw.strip()
        if line.startswith("источник:"):
            source = line.removeprefix("источник:").strip()
            continue
        marker, _, rest = line.partition(" ")
        if marker not in CONFIDENCE:
            continue                          # проза заметки в артефакт не попадает
        claim, _, tail = rest.partition("@")
        follow_up, _, owner = tail.partition("|")
        rows.append(RequirementCandidate(
            text=claim.strip(),
            source=source,
            confidence=CONFIDENCE[marker],
            follow_up=follow_up.strip(),
            follow_up_owner=owner.strip(),
        ))
    return rows


if __name__ == "__main__":
    rows = read_note(NOTE)
    assert len(rows) == 4                     # четыре утверждения, проза пропущена
    assert all(r.source.startswith("Пер Ульсен") for r in rows)
    assert [r.confidence for r in rows] == [0.9, 0.5, 0.2, 0.2]
    assert all(r.follow_up_owner == "Сив Берг" for r in rows if r.confidence < 0.5)
    try:
        RequirementCandidate(text="операторы недовольны инструментами",
                             source="разговор в коридоре, неделя 1", confidence=0.2)
        raise AssertionError("слабое утверждение обязано получить владельца проверки")
    except ValueError:
        pass
    print(len(rows), "кандидата в требования: у каждого источник и следующий шаг")
