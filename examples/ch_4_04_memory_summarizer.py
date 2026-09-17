# Extracted from the book automatically. Lines above the mark are not part of the listing.
from stubs import FakeLLM, LLMClient, count_tokens  # noqa: F401
# --- the listing ---
from dataclasses import dataclass, field

DAY = 24 * 3600.0
TRUST = {"billing": 3, "crm": 3, "operator": 2, "customer": 1}
TTL = {"billing": 7 * DAY, "crm": 7 * DAY, "operator": 30 * DAY, "customer": 1 * DAY}


@dataclass(frozen=True)
class Fact:
    """Утверждение памяти вместе с тем, откуда оно взялось и когда истечёт."""

    text: str
    source: str                   # система записи, оператор или слова клиента
    created_at: float

    @property
    def ttl_s(self) -> float:
        return TTL[self.source]

    @property
    def trust(self) -> int:
        return TRUST[self.source]

    def alive(self, now: float) -> bool:
        return now - self.created_at < self.ttl_s


@dataclass
class Memory:
    facts: list[Fact] = field(default_factory=list)

    def remember(self, fact: Fact) -> None:
        self.facts.append(fact)

    def live(self, now: float) -> list[Fact]:
        return [f for f in self.facts if f.alive(now)]

    def render(self, now: float, budget_tokens: int, min_trust: int = 1) -> str:
        """Сводка для контекста: сначала доверенные источники, потом свежесть."""
        rows = [f for f in self.live(now) if f.trust >= min_trust]
        rows.sort(key=lambda f: (-f.trust, -f.created_at))
        lines: list[str] = []
        spent = 0
        for fact in rows:
            line = f"- {fact.text} [{fact.source}, t={fact.created_at:.0f}]"
            cost = count_tokens(line)
            if spent + cost > budget_tokens:
                break
            lines.append(line)
            spent += cost
        return "\n".join(lines)


def roll(history: list[str], memory: Memory, llm: LLMClient, now: float,
         keep: int = 4) -> list[str]:
    """Свернуть всё, кроме последних keep реплик, в один факт с провенансом."""
    if len(history) <= keep:
        return history
    folded, tail = history[:-keep], history[-keep:]
    reply = llm.complete("Сожми диалог в два-три утверждения:\n" + "\n".join(folded))
    memory.remember(Fact(reply.text, "customer", now))
    return tail


if __name__ == "__main__":
    memory = Memory()
    memory.remember(Fact("лицевой счёт 4402, тариф Orion S", "crm", created_at=0.0))
    memory.remember(Fact("двойное списание 1490 рублей 3 марта", "billing", created_at=120.0))
    memory.remember(Fact("клиент говорит, что ему обещали бесплатный роуминг", "customer",
                         created_at=0.0))

    history = [f"клиент: реплика {i}" for i in range(12)]
    llm = FakeLLM(["клиент жалуется на списание и просит вернуть деньги"])
    tail = roll(history, memory, llm, now=600.0)
    assert tail == history[-4:] and len(memory.live(600.0)) == 4

    summary = memory.render(now=600.0, budget_tokens=200)
    assert summary.splitlines()[0].startswith("- двойное списание")   # биллинг выше слов клиента
    assert "[customer" in summary and "t=" in summary                 # провенанс виден модели

    trusted = memory.render(now=600.0, budget_tokens=200, min_trust=2)
    assert "роуминг" not in trusted                 # слова клиента не становятся фактом
    later = memory.render(now=2 * DAY, budget_tokens=200)
    assert "роуминг" not in later                   # срок жизни истёк сам
    assert "[billing" in later

    narrow = memory.render(now=600.0, budget_tokens=30)
    assert len(narrow.splitlines()) < len(summary.splitlines())   # при нехватке бюджета отбрасываются нижние строки
    print(f"в памяти {len(memory.live(600.0))} фактов, в сводке {len(summary.splitlines())} строк")
