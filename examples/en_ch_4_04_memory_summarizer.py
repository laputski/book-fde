# Extracted from the book automatically. Lines above the mark are not part of the listing.
from stubs import FakeLLM, LLMClient, count_tokens  # noqa: F401
# --- the listing ---
from dataclasses import dataclass, field

DAY = 24 * 3600.0
TRUST = {"billing": 3, "crm": 3, "operator": 2, "customer": 1}
TTL = {"billing": 7 * DAY, "crm": 7 * DAY, "operator": 30 * DAY, "customer": 1 * DAY}


@dataclass(frozen=True)
class Fact:
    """A statement of memory together with where it came from and when it expires."""

    text: str
    source: str                   # a system of record, the operator, or the customer's words
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
        """The summary for the context: trusted sources first, then recency."""
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
    """Fold everything but the last keep turns into one fact with a provenance."""
    if len(history) <= keep:
        return history
    folded, tail = history[:-keep], history[-keep:]
    reply = llm.complete("Compress the dialogue into two or three statements:\n" + "\n".join(folded))
    memory.remember(Fact(reply.text, "customer", now))
    return tail


if __name__ == "__main__":
    memory = Memory()
    memory.remember(Fact("account 4402, tariff Orion S", "crm", created_at=0.0))
    memory.remember(Fact("a double charge of 1490 roubles on 3 March", "billing", created_at=120.0))
    memory.remember(Fact("the customer says free roaming was promised to him", "customer",
                         created_at=0.0))

    history = [f"customer: turn {i}" for i in range(12)]
    llm = FakeLLM(["the customer complains about a charge and asks for a refund"])
    tail = roll(history, memory, llm, now=600.0)
    assert tail == history[-4:] and len(memory.live(600.0)) == 4

    summary = memory.render(now=600.0, budget_tokens=200)
    assert summary.splitlines()[0].startswith("- a double charge")   # billing above the words
    assert "[customer" in summary and "t=" in summary                # the model sees the source

    trusted = memory.render(now=600.0, budget_tokens=200, min_trust=2)
    assert "roaming" not in trusted                 # the customer's words do not become a fact
    later = memory.render(now=2 * DAY, budget_tokens=200)
    assert "roaming" not in later                   # the lifetime expired on its own
    assert "[billing" in later

    narrow = memory.render(now=600.0, budget_tokens=30)
    assert len(narrow.splitlines()) < len(summary.splitlines())   # a short budget drops the lower lines
    print(f"{len(memory.live(600.0))} facts in memory, {len(summary.splitlines())} lines in the summary")
