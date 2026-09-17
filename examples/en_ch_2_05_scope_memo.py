from __future__ import annotations

from dataclasses import dataclass

WORD_LIMIT = 320          # one page the sponsor will read to the end


@dataclass(frozen=True)
class Metric:
    name: str
    baseline: str         # the value measured before the pilot
    target: str           # the acceptance threshold
    dataset: str          # what we measure on, so the result is reproducible

    def line(self) -> str:
        return f"{self.name}: {self.baseline} → {self.target}; dataset: {self.dataset}"


@dataclass(frozen=True)
class Memo:
    customer: str
    decision: str
    in_scope: tuple[str, ...]
    out_of_scope: tuple[str, ...]
    metrics: tuple[Metric, ...]
    constraints: tuple[str, ...]
    money: tuple[str, ...]
    approvers: tuple[str, ...]


def section(title: str, items: tuple[str, ...]) -> str:
    return title + "\n" + "\n".join(f"- {item}" for item in items)


def render(memo: Memo) -> str:
    return "\n\n".join([
        f"{memo.customer}. Decision: {memo.decision}",
        section("In the pilot:", memo.in_scope),
        section("Not in the pilot:", memo.out_of_scope),
        section("How we will check:", tuple(m.line() for m in memo.metrics)),
        section("Constraints:", memo.constraints),
        section("Money:", memo.money),
        section("Approvers:", memo.approvers),
    ])


def words(text: str) -> int:
    return sum(1 for w in text.split() if any(c.isalnum() for c in w))


if __name__ == "__main__":
    memo = Memo(
        customer="Nordbank Regional",
        decision="a 10-week pilot of agent suggestions in the cards queue",
        in_scope=("an answer suggested from the knowledge base inside the agent desktop",
                  "reading accounts and case history on behalf of the agent",
                  "a call summary the agent edits and stores in the CRM"),
        out_of_scope=("answering the customer without an agent", "writing to core banking",
                      "the card-block, mortgage and business queues"),
        metrics=(
            Metric("average handling time", "372 s", "at most 335 s",
                   "400 calls of the cards queue in March"),
            Metric("share of summaries unedited", "0", "at least 0.80",
                   "200 calls labelled by a supervisor"),
            Metric("cost per case", "3.20 EUR", "at most 3.00 EUR",
                   "pilot billing for the fourth month"),
        ),
        constraints=("personal data is processed inside the region only "
                     "(chief information security officer)",
                     "a decision visible to the customer is confirmed by a human (compliance)",
                     "core banking is unavailable from 02:00 to 04:00 (platform owner)"),
        money=("240,000 EUR to build, 11,000 EUR per month to run",
               "break-even in month four at 70 per cent coverage by month three"),
        approvers=("the chief technology officer as sponsor",
                   "the chief information security officer as owner of the perimeter",
                   "the head of the contact centre as owner of the metric"),
    )
    text = render(memo)
    assert words(text) <= WORD_LIMIT, words(text)
    for m in memo.metrics:
        assert m.name in text and m.baseline in text and m.target in text and m.dataset in text
    assert text.count("→") == len(memo.metrics)          # a baseline and a threshold for each metric
    assert all(memo.in_scope) and all(memo.out_of_scope)
    print(words(text), "words, metrics", len(memo.metrics), "· the pilot boundary is named from both sides")
