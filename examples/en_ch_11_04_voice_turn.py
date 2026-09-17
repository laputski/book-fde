from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

BUDGET_MS = {"listening": 250.0, "transcribing": 100.0, "thinking": 300.0, "speaking": 150.0}
TARGET_MS = 800.0                               # from the caller's end of speech to the first audio


@dataclass
class Clock:
    ms: float = 0.0                             # virtual time: the test does not wait


@dataclass(frozen=True)
class TurnPlan:
    costs: dict[str, float]                     # how long each stage would take
    first: str
    action: str | None = None
    action_ms: float = 0.0
    second: str = ""


@dataclass
class VoiceTurn:
    clock: Clock
    committed: list[str]                        # the effect ledger is kept longer than the turn
    spent: dict[str, float] = field(default_factory=dict)
    spoken: list[str] = field(default_factory=list)
    state: str = "listening"
    first_audio_ms: float | None = None

    async def stage(self, name: str, cost: float) -> None:
        self.state = name
        await asyncio.sleep(0)                  # the point where barge-in cancels the turn
        self.clock.ms += cost
        self.spent.setdefault(name, cost)

    async def say(self, text: str, cost: float) -> None:
        await self.stage("speaking", cost)
        if self.first_audio_ms is None:
            self.first_audio_ms = self.clock.ms
        self.spoken.append(text)

    async def commit(self, action: str, cost: float) -> None:
        await asyncio.sleep(0)
        self.clock.ms += cost
        self.committed.append(action)

    async def run(self, plan: TurnPlan) -> None:
        for name in ("listening", "transcribing", "thinking"):
            await self.stage(name, plan.costs[name])
        await self.say(plan.first, plan.costs["speaking"])
        if plan.action is not None:
            effect = asyncio.ensure_future(self.commit(plan.action, plan.action_ms))
            try:
                await asyncio.shield(effect)
            except asyncio.CancelledError:
                await effect                    # a started write runs to its outcome
                raise
            await self.say(plan.second, plan.costs["speaking"])
        self.state = "done"

    def breaches(self) -> list[str]:
        return [name for name, ms in self.spent.items() if ms > BUDGET_MS[name]]


async def converse(turn: VoiceTurn, plan: TurnPlan, barge_in_ms: float | None = None) -> str:
    task = asyncio.create_task(turn.run(plan))
    while not task.done():
        await asyncio.sleep(0)
        if barge_in_ms is not None and turn.clock.ms >= barge_in_ms and not task.cancelling():
            task.cancel()                       # the caller spoke: speech and generation stop
    try:
        await task
    except asyncio.CancelledError:
        turn.state = "interrupted"
    return turn.state


async def main() -> None:
    fast = {"listening": 240.0, "transcribing": 90.0, "thinking": 280.0, "speaking": 140.0}
    plan = TurnPlan(fast, "Booking a nurse callback.", "callback:P-12", 400.0,
                    "Done: a nurse will call you back within two hours.")

    calm = VoiceTurn(Clock(), [])
    assert await converse(calm, plan) == "done"
    assert calm.first_audio_ms == 750.0 and calm.breaches() == []

    ledger: list[str] = []
    early = VoiceTurn(Clock(), ledger)
    assert await converse(early, plan, barge_in_ms=300.0) == "interrupted"
    assert ledger == [] and early.spoken == []                  # interrupted before the write: no record

    late = VoiceTurn(Clock(), ledger)
    assert await converse(late, plan, barge_in_ms=750.0) == "interrupted"
    assert ledger == ["callback:P-12"]                          # the write was under way: completed
    assert late.spoken == ["Booking a nurse callback."]

    slow = VoiceTurn(Clock(), [])
    await converse(slow, TurnPlan({**fast, "thinking": 420.0}, "One moment, checking."))
    assert slow.breaches() == ["thinking"] and (slow.first_audio_ms or 0.0) > TARGET_MS


if __name__ == "__main__":
    asyncio.run(main())
    print("the turn fits 800 ms; barge-in stops speech but not a write already started")
