# Three copies of one assistant after three engagements; files joined for display.

# nordbank/assistant.py
NORDBANK_PROMPT = "You assist Nordbank operators. Answer only from the bank's knowledge base."
NORDBANK_MIN_SCORE = 0.62


def nordbank_prompt(question: str, passages: list[tuple[str, float]]) -> str | None:
    cited = [text for text, score in passages if score >= NORDBANK_MIN_SCORE]
    return f"{NORDBANK_PROMPT}\n{cited}\n{question}" if cited else None


def nordbank_execute(action: str, target: str, approved: set[tuple[str, str]]) -> bool:
    return any(name == action for name, _ in approved)


# orion/assistant.py: a copy of nordbank with other names and threshold
ORION_PROMPT = "You assist Orion Telecom operators. Answer only from the knowledge base."
ORION_MIN_SCORE = 0.55


def orion_prompt(question: str, passages: list[tuple[str, float]]) -> str | None:
    cited = [text for text, score in passages if score >= ORION_MIN_SCORE]
    return f"{ORION_PROMPT}\n{cited}\n{question}" if cited else None


def orion_execute(action: str, target: str, approved: set[tuple[str, str]]) -> bool:
    return any(name == action for name, _ in approved)


# northgate/assistant.py: a copy of orion; the city audit found the approval defect
NORTHGATE_PROMPT = "You assist Northgate residents. Answer only from city documents."
NORTHGATE_MIN_SCORE = 0.70


def northgate_prompt(question: str, passages: list[tuple[str, float]]) -> str | None:
    cited = [text for text, score in passages if score >= NORTHGATE_MIN_SCORE]
    return f"{NORTHGATE_PROMPT}\n{cited}\n{question}" if cited else None


def northgate_execute(action: str, target: str, approved: set[tuple[str, str]]) -> bool:
    return (action, target) in approved             # fixed only here


if __name__ == "__main__":
    approved = {("submit", "req-17")}               # a human approved request req-17
    assert not northgate_execute("submit", "req-99", approved)
    assert nordbank_execute("submit", "req-99", approved)       # the fix was not carried over
    assert orion_execute("submit", "req-99", approved)
    passages = [("regulation 4.2", 0.60)]
    assert orion_prompt("deadline?", passages) is not None
    assert nordbank_prompt("deadline?", passages) is None           # same search, another threshold in code
    print("the fix exists in one copy out of three")
