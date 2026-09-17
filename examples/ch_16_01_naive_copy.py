# Три копии одного ассистента после трёх engagements; файлы склеены для показа.

# nordbank/assistant.py
NORDBANK_PROMPT = "Вы помощник оператора Nordbank. Отвечайте только по базе знаний банка."
NORDBANK_MIN_SCORE = 0.62


def nordbank_prompt(question: str, passages: list[tuple[str, float]]) -> str | None:
    cited = [text for text, score in passages if score >= NORDBANK_MIN_SCORE]
    return f"{NORDBANK_PROMPT}\n{cited}\n{question}" if cited else None


def nordbank_execute(action: str, target: str, approved: set[tuple[str, str]]) -> bool:
    return any(name == action for name, _ in approved)


# orion/assistant.py: копия nordbank с другими именами и порогом
ORION_PROMPT = "Вы помощник оператора Orion Telecom. Отвечайте только по базе знаний."
ORION_MIN_SCORE = 0.55


def orion_prompt(question: str, passages: list[tuple[str, float]]) -> str | None:
    cited = [text for text, score in passages if score >= ORION_MIN_SCORE]
    return f"{ORION_PROMPT}\n{cited}\n{question}" if cited else None


def orion_execute(action: str, target: str, approved: set[tuple[str, str]]) -> bool:
    return any(name == action for name, _ in approved)


# northgate/assistant.py: копия orion; дефект одобрения нашёл аудит города
NORTHGATE_PROMPT = "Вы помощник жителя Northgate. Отвечайте только по документам города."
NORTHGATE_MIN_SCORE = 0.70


def northgate_prompt(question: str, passages: list[tuple[str, float]]) -> str | None:
    cited = [text for text, score in passages if score >= NORTHGATE_MIN_SCORE]
    return f"{NORTHGATE_PROMPT}\n{cited}\n{question}" if cited else None


def northgate_execute(action: str, target: str, approved: set[tuple[str, str]]) -> bool:
    return (action, target) in approved             # исправлено только здесь


if __name__ == "__main__":
    approved = {("submit", "req-17")}               # человек одобрил заявку req-17
    assert not northgate_execute("submit", "req-99", approved)
    assert nordbank_execute("submit", "req-99", approved)       # исправление не перенесено
    assert orion_execute("submit", "req-99", approved)
    passages = [("регламент 4.2", 0.60)]
    assert orion_prompt("срок?", passages) is not None
    assert nordbank_prompt("срок?", passages) is None           # тот же поиск, другой порог в коде
    print("исправление есть в одной копии из трёх")
