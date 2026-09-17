NOTES = """- ассистент должен быть точным
- отвечать быстро
- интеграция с CRM
- безопасность на уровне банка
- снизить нагрузку на операторов"""

BULLETS = [line.removeprefix("- ") for line in NOTES.splitlines()]

if __name__ == "__main__":
    assert len(BULLETS) == 5
    assert not any(c.isdigit() for b in BULLETS for c in b)   # ни порогов, ни объёмов, ни дат
    print(len(BULLETS), "пунктов и ни одного проверяемого требования")
