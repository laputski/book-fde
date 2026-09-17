# Extracted from the book automatically. Lines above the mark are not part of the listing.
from stubs import count_tokens  # noqa: F401
# --- the listing ---
import hashlib
from dataclasses import dataclass, field
from typing import Literal

BUDGET_TOKENS = 32_000
Zone = Literal["prefix", "suffix"]

INSTRUCTIONS = "## ROLE\nThe assistant of an Orion Telecom chat operator.\n" + "A rule of behaviour, one per line. " * 200
TOOLS = "## TOOLS\n" + "get_invoice(subscriber_id, period) -> Invoice\n" * 120
POLICY = "## ANSWER FORMAT\nThe conclusion first, then a link to the invoice or the article.\n"


class BudgetExceeded(Exception):
    """The mandatory part of the context does not fit the window."""


@dataclass(frozen=True)
class ContextBlock:
    """A piece of context with its price in tokens, a priority and a cache zone."""

    name: str
    text: str
    priority: int                 # 1 is dropped last
    zone: Zone = "suffix"
    required: bool = False

    @property
    def tokens(self) -> int:
        return count_tokens(self.render())

    def render(self) -> str:
        return f"<{self.name}>\n{self.text}\n</{self.name}>\n"


@dataclass
class Assembly:
    prefix: str
    suffix: str
    included: list[str] = field(default_factory=list)
    excluded: list[tuple[str, str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.prefix + self.suffix

    @property
    def tokens(self) -> int:
        return count_tokens(self.text)

    @property
    def prefix_digest(self) -> str:
        return hashlib.blake2b(self.prefix.encode("utf-8"), digest_size=8).hexdigest()


def assemble(blocks: list[ContextBlock], budget: int = BUDGET_TOKENS) -> Assembly:
    """Selection by priority, placement by the declared order."""
    prefix_blocks = [b for b in blocks if b.zone == "prefix"]
    suffix_blocks = [b for b in blocks if b.zone == "suffix"]
    prefix = "".join(b.render() for b in prefix_blocks)
    spent = count_tokens(prefix)
    if spent > budget:
        raise BudgetExceeded(f"the prefix takes {spent} tokens of {budget}")

    chosen: set[str] = set()
    excluded: list[tuple[str, str]] = []
    for block in sorted(suffix_blocks, key=lambda b: (b.priority, b.name)):
        if spent + block.tokens <= budget:
            chosen.add(block.name)
            spent += block.tokens
        elif block.required:
            raise BudgetExceeded(f"the required block {block.name} does not fit")
        else:
            excluded.append((block.name, f"budget: {block.tokens} against {budget - spent} left"))

    ordered = [b for b in suffix_blocks if b.name in chosen]
    return Assembly(prefix=prefix, suffix="".join(b.render() for b in ordered),
                    included=[b.name for b in prefix_blocks] + [b.name for b in ordered],
                    excluded=sorted(excluded))


def request_blocks(profile: str, invoices: str, passages: list[str],
                   summary: str, tail: list[str], question: str) -> list[ContextBlock]:
    """One agent-assist request: the unchanging zone, then the data of the chat."""
    blocks = [
        ContextBlock("instructions", INSTRUCTIONS, priority=1, zone="prefix", required=True),
        ContextBlock("tools", TOOLS, priority=1, zone="prefix", required=True),
        ContextBlock("policy", POLICY, priority=1, zone="prefix", required=True),
        ContextBlock("profile", profile, priority=2),
        ContextBlock("invoices", invoices, priority=2),
    ]
    blocks += [ContextBlock(f"kb:{i}", text, priority=3 + i) for i, text in enumerate(passages)]
    blocks += [
        ContextBlock("memory", summary, priority=2),
        ContextBlock("history", "\n".join(tail), priority=2),
        ContextBlock("question", question, priority=1, required=True),
    ]
    return blocks


if __name__ == "__main__":
    passages = ["A knowledge base article about a double charge on an account. " * 620,
                "An article about moving a payment between two personal accounts of one subscriber. " * 480,
                "An article about an outage in a network segment and the compensation for it. " * 500]
    tail = [f"customer: turn {i}" for i in range(20)]

    first = assemble(request_blocks("Peter Ilyin, Orion S", "invoice 1204 for 1490 roubles",
                                    passages, "the customer complained in March already",
                                    tail, "why was I charged twice?"))
    second = assemble(request_blocks("Maria Kim, Orion L", "invoice 8831 for 3200 roubles",
                                     passages, "no earlier contacts",
                                     tail, "how do I move the payment?"))

    assert first.tokens <= BUDGET_TOKENS and second.tokens <= BUDGET_TOKENS
    assert first.prefix == second.prefix                  # the prefix matches byte for byte
    assert first.prefix_digest == second.prefix_digest
    assert "question" in first.included                   # the required block is there
    assert [n for n, _ in first.excluded] == ["kb:2"]     # the worst priority is evicted
    assert first.included.index("memory") < first.included.index("question")

    tight = assemble(request_blocks("Peter Ilyin, Orion S", "invoice 1204 for 1490 roubles",
                                    passages, "the customer complained in March already",
                                    tail, "why was I charged twice?"), budget=4_000)
    assert tight.included[-1] == "question"               # the question survived
    assert [n for n, _ in tight.excluded] == ["kb:0", "kb:1", "kb:2"]

    try:
        assemble(request_blocks("Peter Ilyin, Orion S", "invoice 1204 for 1490 roubles",
                                passages, "", tail, "why?"), budget=1_000)
        raise AssertionError("a budget shortfall must be a refusal, not a silent truncation")
    except BudgetExceeded:
        pass
    print(f"assembled {first.tokens} tokens, prefix {first.prefix_digest}, "
          f"evicted {len(first.excluded)}")
