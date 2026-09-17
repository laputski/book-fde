from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

BUDGET_MS = {"listening": 250.0, "transcribing": 100.0, "thinking": 300.0, "speaking": 150.0}
TARGET_MS = 800.0                               # от конца речи звонящего до первого звука ответа


@dataclass
class Clock:
    ms: float = 0.0                             # виртуальное время: тест не ждёт


@dataclass(frozen=True)
class TurnPlan:
    costs: dict[str, float]                     # сколько заняла бы каждая стадия
    first: str
    action: str | None = None
    action_ms: float = 0.0
    second: str = ""


@dataclass
class VoiceTurn:
    clock: Clock
    committed: list[str]                        # журнал эффектов хранится дольше хода
    spent: dict[str, float] = field(default_factory=dict)
    spoken: list[str] = field(default_factory=list)
    state: str = "listening"
    first_audio_ms: float | None = None

    async def stage(self, name: str, cost: float) -> None:
        self.state = name
        await asyncio.sleep(0)                  # точка, в которой barge-in отменяет ход
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
                await effect                    # начатая запись доводится до исхода
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
            task.cancel()                       # звонящий заговорил: речь и генерация прекращаются
    try:
        await task
    except asyncio.CancelledError:
        turn.state = "interrupted"
    return turn.state


async def main() -> None:
    fast = {"listening": 240.0, "transcribing": 90.0, "thinking": 280.0, "speaking": 140.0}
    plan = TurnPlan(fast, "Записываю обратный звонок медсестры.", "callback:P-12", 400.0,
                    "Готово: медсестра перезвонит в течение двух часов.")

    calm = VoiceTurn(Clock(), [])
    assert await converse(calm, plan) == "done"
    assert calm.first_audio_ms == 750.0 and calm.breaches() == []

    ledger: list[str] = []
    early = VoiceTurn(Clock(), ledger)
    assert await converse(early, plan, barge_in_ms=300.0) == "interrupted"
    assert ledger == [] and early.spoken == []                  # перебили до записи: записи нет

    late = VoiceTurn(Clock(), ledger)
    assert await converse(late, plan, barge_in_ms=750.0) == "interrupted"
    assert ledger == ["callback:P-12"]                          # запись уже шла: доведена
    assert late.spoken == ["Записываю обратный звонок медсестры."]

    slow = VoiceTurn(Clock(), [])
    await converse(slow, TurnPlan({**fast, "thinking": 420.0}, "Секунду, уточняю."))
    assert slow.breaches() == ["thinking"] and (slow.first_audio_ms or 0.0) > TARGET_MS


if __name__ == "__main__":
    asyncio.run(main())
    print("ход укладывается в 800 мс; перебивание прерывает речь, но не уже начатую запись")
