# Extracted from the book automatically. Lines above the mark are not part of the listing.
from stubs import cosine, embed  # noqa: F401
# --- the listing ---
GUIDELINES = {
    "sepsis-v3": ("Department: intensive care. Lactate threshold 2 mmol/l. On suspicion "
                  "of sepsis, blood cultures are drawn before the first dose of antibiotic."),
    "psych-v1": ("Department: psychiatry. Suicide risk is assessed on every admission. "
                 "The document is closed to the other departments."),
}


def fixed_chunks(text: str, size: int = 60) -> list[str]:
    """Slicing by character count: sentence and table boundaries are ignored."""
    return [text[i:i + size] for i in range(0, len(text), size)]


def index_all() -> list[str]:
    return [part for text in GUIDELINES.values() for part in fixed_chunks(text)]


def search(query: str, k: int = 3) -> list[str]:
    q = embed(query)
    parts = index_all()
    return sorted(parts, key=lambda part: cosine(q, embed(part)), reverse=True)[:k]


if __name__ == "__main__":
    parts = index_all()
    assert len(parts) > len(GUIDELINES)                  # the document was cut blindly
    cut = [i for i in range(len(parts) - 1)
           if parts[i][-1].isalnum() and parts[i + 1][0].isalnum()]
    assert cut                                           # a chunk boundary fell inside a word
    assert any("psychiatr" in part for part in parts)    # a closed document in the shared index
    hits = search("lactate threshold in sepsis")
    assert len(hits) == 3 and all(isinstance(h, str) for h in hits)
    print("three strings with no source, version or rights check:", len(hits))
