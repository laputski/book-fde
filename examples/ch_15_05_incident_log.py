from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from itertools import pairwise

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

PROMISES = ("больше не повторится", "исправлено окончательно", "по вине")


class Kind(StrEnum):
    DETECTED = "detected"
    MITIGATED = "mitigated"
    UPDATE_SENT = "update_sent"
    ROLLED_BACK = "rolled_back"
    VERIFIED = "verified"
    RESOLVED = "resolved"


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)
    at: datetime
    kind: Kind
    summary: str
    bundle_id: str = ""


class Update(BaseModel):
    model_config = ConfigDict(frozen=True)
    at: datetime
    sender: str
    audience: tuple[str, ...]
    known: str = Field(min_length=10)               # что известно
    doing: str = Field(min_length=10)               # что делается
    advice: str = Field(min_length=10)              # что делать клиницисту сейчас
    next_update_at: datetime | None = None
    final: bool = False

    @model_validator(mode="after")
    def cadence(self) -> Update:
        if not self.final and self.next_update_at is None:
            raise ValueError("обновление без времени следующего обновления")
        if self.next_update_at is not None and self.next_update_at <= self.at:
            raise ValueError("следующее обновление назначено в прошлом")
        return self


def render(u: Update) -> str:
    body = f"{u.known} {u.doing} {u.advice}".lower()
    if promised := [p for p in PROMISES if p in body]:
        raise ValueError(f"обещание или обвинение в тексте: {promised}")
    status = "восстановлен" if u.final else "идёт работа"
    tail = "Инцидент закрыт." if u.final else f"Следующее обновление в {u.next_update_at:%H:%M}."
    return (f"[{u.at:%H:%M}] Ассистент по руководствам: {status}\nЧто известно: {u.known}\n"
            f"Что делаем: {u.doing}\nЧто делать сейчас: {u.advice}\n{tail}")


class Incident(BaseModel):
    id: str
    comms_lead: str                                 # единственный голос для заказчика
    events: list[Event] = Field(default_factory=list)
    sent: list[Update] = Field(default_factory=list)

    def log(self, at: datetime, kind: Kind, summary: str, bundle_id: str = "") -> None:
        if self.events and at < self.events[-1].at:
            raise ValueError("события записываются в порядке времени")
        self.events.append(Event(at=at, kind=kind, summary=summary, bundle_id=bundle_id))

    def send(self, u: Update) -> str:
        if u.sender != self.comms_lead:
            raise PermissionError("заказчику пишет только ответственный за коммуникацию")
        text = render(u)
        self.sent.append(u)
        self.log(u.at, Kind.UPDATE_SENT, ", ".join(u.audience))
        return text

    def since_detection(self, kind: Kind) -> timedelta:
        return next(e.at for e in self.events if e.kind is kind) - self.events[0].at


if __name__ == "__main__":
    lead = "руководитель engagement"
    leads = ("заведующие отделениями", "главный врач по информатизации")

    def at(hhmm: str) -> datetime:
        hour, minute = map(int, hhmm.split(":"))
        return datetime(2026, 9, 14, hour, minute)

    def update(hhmm: str, known: str, doing: str, advice: str, nxt: str = "",
               sender: str = lead) -> Update:
        return Update(at=at(hhmm), sender=sender, audience=leads, known=known, doing=doing,
                      advice=advice, next_update_at=at(nxt) if nxt else None, final=not nxt)

    inc = Incident(id="INC-0914", comms_lead=lead)
    inc.log(at("09:10"), Kind.DETECTED, "цитаты редакции 7 вместо 8", "R-119")
    first = inc.send(update("09:14", "часть ответов о дозировании ссылается на редакцию 7 вместо 8",
                            "переводим ответы о дозировании в режим фрагментов с цитатами",
                            "сверяйте дозировку по открытому документу", nxt="09:30"))
    assert first.endswith("Следующее обновление в 09:30.")
    try:
        Update(at=at("09:20"), sender=lead, audience=leads, known="причина устанавливается",
               doing="сравниваем выпуски", advice="сверяйте по документу")
        raise AssertionError("обновление без времени следующего прошло проверку")
    except ValidationError:
        pass
    try:
        inc.send(update("09:21", "причина найдена в промпте", "исправляем промпт сейчас",
                        "ждите исправления", nxt="09:30", sender="дежурный инженер"))
        raise AssertionError("второй голос прошёл")
    except PermissionError:
        pass

    inc.log(at("09:22"), Kind.MITIGATED, "выключатель: ступень 1", "R-119")
    inc.send(update("09:30", "ответы о дозировании показывают фрагменты действующей редакции",
                    "сравниваем выпуск R-119 с предыдущим", "режим фрагментов безопасен для обхода",
                    nxt="10:00"))
    inc.send(update("10:00", "причина в изменении промпта выпуска R-119",
                    "откатываем выпуск целиком на R-118", "режим фрагментов сохраняется", nxt="10:30"))
    inc.log(at("10:05"), Kind.ROLLED_BACK, "R-119 -> R-118", "R-118")
    inc.log(at("10:20"), Kind.VERIFIED, "пробы 20 из 20, трассы инцидента 23 из 23", "R-118")
    last = inc.send(update("10:30", "ответы о дозировании снова ссылаются на редакцию 8",
                           "полный режим возвращён в 10:25 после проверки",
                           "разбор инцидента пришлём до пятницы"))
    inc.log(at("10:30"), Kind.RESOLVED, "отбой", "R-118")

    assert last.endswith("Инцидент закрыт.")
    assert inc.since_detection(Kind.UPDATE_SENT) == timedelta(minutes=4)
    assert inc.since_detection(Kind.MITIGATED) == timedelta(minutes=12)
    assert all(a.next_update_at is not None and b.at <= a.next_update_at for a, b in pairwise(inc.sent))
    print("хронология записана, каждое обновление назначает следующее и приходит вовремя")
