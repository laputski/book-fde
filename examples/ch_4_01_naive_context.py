# Extracted from the book automatically. Lines above the mark are not part of the listing.
from stubs import count_tokens  # noqa: F401
# --- the listing ---
SYSTEM = ("Ты ассистент оператора чата Orion Telecom. Отвечай на языке клиента, "
          "коротко, и никогда не обещай компенсацию сам.")
BUDGET_TOKENS = 32_000


def build_prompt(profile: str, invoices: str, kb: str,
                 history: list[str], question: str) -> str:
    """Сборка промпта конкатенацией в том порядке, в каком пришли данные."""
    text = "Клиент: " + profile + "\n"
    text += "Счета: " + invoices + "\n"
    text += SYSTEM + "\n"
    text += "База знаний: " + kb + "\n"
    for turn in history:
        text += turn + "\n"
    return text + "Вопрос: " + question


if __name__ == "__main__":
    kb = "Двойное списание: сверить дату биллингового цикла, затем оформить возврат. " * 1200
    history = [f"клиент: сообщение номер {i} про списание и тариф\n"
               f"оператор: ответ номер {i} со ссылкой на условия тарифа" for i in range(800)]

    first = build_prompt("Пётр Ильин, тариф Orion S", "счёт 1204 на 1490 рублей",
                         kb, history, "почему списали дважды?")
    second = build_prompt("Мария Ким, тариф Orion L", "счёт 8831 на 3200 рублей",
                          kb, history, "почему списали дважды?")

    assert count_tokens(first) > BUDGET_TOKENS          # окно переполнено историей
    shared = 0
    for a, b in zip(first, second):
        if a != b:
            break
        shared += 1
    assert shared < 12                                  # общего префикса для кэша нет
    print(count_tokens(first), "токенов, общий префикс:", shared, "символов")
