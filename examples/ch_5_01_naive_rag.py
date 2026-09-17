# Extracted from the book automatically. Lines above the mark are not part of the listing.
from stubs import cosine, embed  # noqa: F401
# --- the listing ---
GUIDELINES = {
    "sepsis-v3": ("Отделение: реанимация. Порог лактата 2 ммоль/л. При подозрении "
                  "на сепсис посев крови берут до первой дозы антибиотика."),
    "psych-v1": ("Отделение: психиатрия. Оценку суицидального риска проводят при "
                 "каждом поступлении. Документ закрыт для остальных отделений."),
}


def fixed_chunks(text: str, size: int = 60) -> list[str]:
    """Нарезка по числу символов: границы фраз и таблиц не учитываются."""
    return [text[i:i + size] for i in range(0, len(text), size)]


def index_all() -> list[str]:
    return [part for text in GUIDELINES.values() for part in fixed_chunks(text)]


def search(query: str, k: int = 3) -> list[str]:
    q = embed(query)
    parts = index_all()
    return sorted(parts, key=lambda part: cosine(q, embed(part)), reverse=True)[:k]


if __name__ == "__main__":
    parts = index_all()
    assert len(parts) > len(GUIDELINES)                  # документ разрезан вслепую
    cut = [i for i in range(len(parts) - 1)
           if parts[i][-1].isalnum() and parts[i + 1][0].isalnum()]
    assert cut                                           # граница чанка прошла внутри слова
    assert any("психиатр" in part for part in parts)     # закрытый документ в общем индексе
    hits = search("порог лактата при сепсисе")
    assert len(hits) == 3 and all(isinstance(h, str) for h in hits)
    print("три строки без источника, версии и проверки прав:", len(hits))
