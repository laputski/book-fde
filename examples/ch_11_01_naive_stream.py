from collections.abc import Iterator


def agent_reply(wording: int) -> Iterator[str]:
    """Агент отдаёт интерфейсу только текст, нарезанный на фрагменты."""
    ask = ["Подтвердите назначение цефтриаксона 2 г в/в.",
           "Если вы согласны, я назначу цефтриаксон 2 г в/в."][wording]
    text = f"По протоколу сепсиса показана антибактериальная терапия. Аллергий нет. {ask}"
    for i in range(0, len(text), 12):
        yield text[i:i + 12]


def needs_approval(screen: str) -> bool:
    return "Подтвердите" in screen          # интерфейс угадывает намерение по словам


if __name__ == "__main__":
    first = "".join(agent_reply(0))
    second = "".join(agent_reply(1))
    assert needs_approval(first)
    assert not needs_approval(second)       # то же намерение, другие слова: кнопки нет
    assert "Аллергий нет" in second         # утверждение без источника и без следа вызова
    print("просьба об одобрении потерялась в тексте ответа")
