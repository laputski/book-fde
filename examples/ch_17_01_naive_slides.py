BOXES = ["Портал", "Агент", "LLM", "Векторная БД", "CRM", "Мониторинг"]
ARROWS = [("Портал", "Агент"), ("Агент", "LLM"), ("Агент", "Векторная БД"),
          ("Агент", "CRM"), ("Агент", "Мониторинг")]


def impact(change: str) -> set[str]:
    """Что затронет изменение требования? Схема содержит только имена и стрелки."""
    hit = {box for box in BOXES if box.lower() in change.lower()}
    for source, target in ARROWS:
        if source in hit:
            hit.add(target)
    return hit


if __name__ == "__main__":
    assert impact("данные жителей не покидают страну") == set()    # драйвер не назван ни в одном блоке
    assert impact("заменить LLM на более дешёвую") == {"LLM"}      # цена замены неизвестна
    assert len(BOXES) == 6 and len(ARROWS) == 5
    print("шесть блоков, пять стрелок, ни одного решения")
