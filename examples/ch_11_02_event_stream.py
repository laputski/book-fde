from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class Token(BaseModel):
    kind: Literal["token"] = "token"
    text: str


class ToolStart(BaseModel):
    kind: Literal["tool_start"] = "tool_start"
    call_id: str
    tool: str
    args: dict[str, str]


class ToolResult(BaseModel):
    kind: Literal["tool_result"] = "tool_result"
    call_id: str
    ok: bool
    summary: str
    sources: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    kind: Literal["approval_request"] = "approval_request"
    request_id: str
    tool: str
    args: dict[str, str]
    expires_at: float


class Final(BaseModel):
    kind: Literal["final"] = "final"
    status: Literal["done", "waiting_for_approval", "failed"]


type AnyPayload = Token | ToolStart | ToolResult | ApprovalRequest | Final


class Event(BaseModel):
    run_id: str
    seq: int                                    # номер внутри запуска: 1, 2, 3, ...
    payload: Annotated[AnyPayload, Field(discriminator="kind")]


def to_sse(event: Event) -> str:
    return f"id: {event.seq}\nevent: {event.payload.kind}\ndata: {event.model_dump_json()}\n\n"


def parse_sse(frame: str) -> Event:
    data = next(line.removeprefix("data: ") for line in frame.splitlines() if line.startswith("data: "))
    return Event.model_validate_json(data)


@dataclass
class EventLog:
    """Журнал событий запуска: единственный источник того, что показывает интерфейс."""
    run_id: str
    events: list[Event] = field(default_factory=list)

    def emit(self, payload: AnyPayload) -> Event:
        event = Event(run_id=self.run_id, seq=len(self.events) + 1, payload=payload)
        self.events.append(event)
        return event

    def resume(self, last_seq: int) -> Iterator[str]:
        """Всё, что идёт после последнего номера, который клиент подтвердил."""
        for event in self.events[last_seq:]:
            yield to_sse(event)


@dataclass
class Screen:
    """Клиент: применяет события строго по порядку и помнит последний номер."""
    last_seq: int = 0
    text: str = ""
    tool_log: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    pending: dict[str, ApprovalRequest] = field(default_factory=dict)
    status: str = "streaming"

    def apply(self, event: Event) -> None:
        if event.seq <= self.last_seq:
            return                              # повтор после переподключения
        if event.seq != self.last_seq + 1:
            raise ValueError(f"пропуск: ожидалось {self.last_seq + 1}, пришло {event.seq}")
        match event.payload:
            case Token(text=text):
                self.text += text
            case ToolStart(call_id=call_id, tool=tool):
                self.tool_log.append(f"{call_id} {tool}: выполняется")
            case ToolResult(call_id=call_id, ok=ok, summary=summary, sources=sources):
                self.tool_log.append(f"{call_id}: {'готово' if ok else 'ошибка'}, {summary}")
                self.sources.extend(sources)
            case ApprovalRequest() as request:
                self.pending[request.request_id] = request
            case Final(status=status):
                self.status = status
        self.last_seq = event.seq


if __name__ == "__main__":
    log = EventLog("run-12")
    log.emit(Token(text="По протоколу сепсиса "))
    log.emit(ToolStart(call_id="c1", tool="get_allergies", args={"patient": "P-12"}))
    log.emit(ToolResult(call_id="c1", ok=True, summary="аллергий не найдено",
                        sources=["ehr:AllergyIntolerance?patient=P-12"]))
    log.emit(Token(text="показан цефтриаксон."))
    log.emit(ApprovalRequest(request_id="a1", tool="place_order",
                             args={"drug": "ceftriaxone", "dose": "2 g", "route": "iv"}, expires_at=900.0))
    log.emit(Final(status="waiting_for_approval"))

    screen = Screen()
    for frame in list(log.resume(0))[:3]:
        screen.apply(parse_sse(frame))          # после третьего события соединение оборвалось
    for frame in log.resume(screen.last_seq - 1):
        screen.apply(parse_sse(frame))          # сервер переотправил и третье: оно отброшено
    assert screen.text == "По протоколу сепсиса показан цефтриаксон."
    assert len(screen.tool_log) == 2 and screen.sources == ["ehr:AllergyIntolerance?patient=P-12"]
    assert list(screen.pending) == ["a1"] and screen.status == "waiting_for_approval"
    try:
        Screen().apply(parse_sse(to_sse(log.events[1])))
        raise AssertionError("пропуск первого события обязан быть замечен")
    except ValueError:
        pass
    assert to_sse(log.events[4]).startswith("id: 5\nevent: approval_request\n")
    print("интерфейс собирает экран из журнала событий и возобновляет поток без потерь")
