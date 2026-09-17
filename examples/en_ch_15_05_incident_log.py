from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from itertools import pairwise

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

PROMISES = ("will never happen again", "fixed for good", "fault of")


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
    known: str = Field(min_length=10)               # what is known
    doing: str = Field(min_length=10)               # what is being done
    advice: str = Field(min_length=10)              # what a clinician should do now
    next_update_at: datetime | None = None
    final: bool = False

    @model_validator(mode="after")
    def cadence(self) -> Update:
        if not self.final and self.next_update_at is None:
            raise ValueError("an update without the time of the next update")
        if self.next_update_at is not None and self.next_update_at <= self.at:
            raise ValueError("the next update is scheduled in the past")
        return self


def render(u: Update) -> str:
    body = f"{u.known} {u.doing} {u.advice}".lower()
    if promised := [p for p in PROMISES if p in body]:
        raise ValueError(f"a promise or a blame in the text: {promised}")
    status = "restored" if u.final else "work in progress"
    tail = "Incident closed." if u.final else f"Next update at {u.next_update_at:%H:%M}."
    return (f"[{u.at:%H:%M}] Guideline assistant: {status}\nWhat we know: {u.known}\n"
            f"What we are doing: {u.doing}\nWhat to do now: {u.advice}\n{tail}")


class Incident(BaseModel):
    id: str
    comms_lead: str                                 # the single voice towards the customer
    events: list[Event] = Field(default_factory=list)
    sent: list[Update] = Field(default_factory=list)

    def log(self, at: datetime, kind: Kind, summary: str, bundle_id: str = "") -> None:
        if self.events and at < self.events[-1].at:
            raise ValueError("events are recorded in time order")
        self.events.append(Event(at=at, kind=kind, summary=summary, bundle_id=bundle_id))

    def send(self, u: Update) -> str:
        if u.sender != self.comms_lead:
            raise PermissionError("only the communications lead writes to the customer")
        text = render(u)
        self.sent.append(u)
        self.log(u.at, Kind.UPDATE_SENT, ", ".join(u.audience))
        return text

    def since_detection(self, kind: Kind) -> timedelta:
        return next(e.at for e in self.events if e.kind is kind) - self.events[0].at


if __name__ == "__main__":
    lead = "engagement lead"
    leads = ("heads of department", "chief medical information officer")

    def at(hhmm: str) -> datetime:
        hour, minute = map(int, hhmm.split(":"))
        return datetime(2026, 9, 14, hour, minute)

    def update(hhmm: str, known: str, doing: str, advice: str, nxt: str = "",
               sender: str = lead) -> Update:
        return Update(at=at(hhmm), sender=sender, audience=leads, known=known, doing=doing,
                      advice=advice, next_update_at=at(nxt) if nxt else None, final=not nxt)

    inc = Incident(id="INC-0914", comms_lead=lead)
    inc.log(at("09:10"), Kind.DETECTED, "edition 7 cited instead of 8", "R-119")
    first = inc.send(update("09:14", "some dosing answers cite edition 7 instead of edition 8",
                            "we are switching dosing answers to passages with citations",
                            "check the dose against the open guideline document", nxt="09:30"))
    assert first.endswith("Next update at 09:30.")
    try:
        Update(at=at("09:20"), sender=lead, audience=leads, known="the cause is being established",
               doing="comparing the releases", advice="check against the document")
        raise AssertionError("an update without the next time passed validation")
    except ValidationError:
        pass
    try:
        inc.send(update("09:21", "the cause is in the prompt", "fixing the prompt right now",
                        "wait for the fix", nxt="09:30", sender="on-call engineer"))
        raise AssertionError("a second voice got through")
    except PermissionError:
        pass

    inc.log(at("09:22"), Kind.MITIGATED, "kill switch: rung 1", "R-119")
    inc.send(update("09:30", "dosing answers now show passages of the current edition",
                    "comparing release R-119 with the previous one", "passage mode is safe for the ward round",
                    nxt="10:00"))
    inc.send(update("10:00", "the cause is a prompt change in release R-119",
                    "rolling the whole release back to R-118", "passage mode stays on for now", nxt="10:30"))
    inc.log(at("10:05"), Kind.ROLLED_BACK, "R-119 -> R-118", "R-118")
    inc.log(at("10:20"), Kind.VERIFIED, "probes 20 of 20, incident traces 23 of 23", "R-118")
    last = inc.send(update("10:30", "dosing answers cite edition 8 again",
                           "full mode restored at 10:25 after verification",
                           "the incident review will follow by Friday"))
    inc.log(at("10:30"), Kind.RESOLVED, "all-clear", "R-118")

    assert last.endswith("Incident closed.")
    assert inc.since_detection(Kind.UPDATE_SENT) == timedelta(minutes=4)
    assert inc.since_detection(Kind.MITIGATED) == timedelta(minutes=12)
    assert all(a.next_update_at is not None and b.at <= a.next_update_at for a, b in pairwise(inc.sent))
    print("the timeline is recorded; every update sets the next one and arrives on time")
