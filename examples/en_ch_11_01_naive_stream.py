from collections.abc import Iterator


def agent_reply(wording: int) -> Iterator[str]:
    """The agent hands the interface nothing but text, cut into chunks."""
    ask = ["Confirm the order for ceftriaxone 2 g IV.",
           "If you agree, I will order ceftriaxone 2 g IV."][wording]
    text = f"Per the sepsis protocol, antibiotic therapy is indicated. No allergies. {ask}"
    for i in range(0, len(text), 12):
        yield text[i:i + 12]


def needs_approval(screen: str) -> bool:
    return "Confirm" in screen              # the interface guesses the intent from words


if __name__ == "__main__":
    first = "".join(agent_reply(0))
    second = "".join(agent_reply(1))
    assert needs_approval(first)
    assert not needs_approval(second)       # same intent, other words: no button
    assert "No allergies" in second         # a claim with no source and no trace of a call
    print("the approval request got lost in the text of the answer")
