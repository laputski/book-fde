# Extracted from the book automatically. Lines above the mark are not part of the listing.
from stubs import count_tokens  # noqa: F401
# --- the listing ---
SYSTEM = ("You are the assistant of an Orion Telecom chat operator. Answer in the "
          "customer's language, briefly, and never promise compensation yourself.")
BUDGET_TOKENS = 32_000


def build_prompt(profile: str, invoices: str, kb: str,
                 history: list[str], question: str) -> str:
    """Building the prompt by concatenation, in the order the data arrived."""
    text = "Customer: " + profile + "\n"
    text += "Invoices: " + invoices + "\n"
    text += SYSTEM + "\n"
    text += "Knowledge base: " + kb + "\n"
    for turn in history:
        text += turn + "\n"
    return text + "Question: " + question


if __name__ == "__main__":
    kb = "Double charge: check the date of the billing cycle, then issue a refund. " * 1200
    history = [f"customer: message number {i} about the charge and the tariff\n"
               f"operator: reply number {i} quoting the terms of the tariff" for i in range(800)]

    first = build_prompt("Peter Ilyin, tariff Orion S", "invoice 1204 for 1490 roubles",
                         kb, history, "why was I charged twice?")
    second = build_prompt("Maria Kim, tariff Orion L", "invoice 8831 for 3200 roubles",
                          kb, history, "why was I charged twice?")

    assert count_tokens(first) > BUDGET_TOKENS          # the window overflows with history
    shared = 0
    for a, b in zip(first, second):
        if a != b:
            break
        shared += 1
    assert shared < 12                                  # no common prefix left to cache
    print(count_tokens(first), "tokens, common prefix:", shared, "characters")
