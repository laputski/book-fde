# Extracted from the book automatically. Lines above the mark are not part of the listing.
from stubs import FakeLLM, LLMClient  # noqa: F401
# --- the listing ---
import json

DOC = "TKL-000412 | DE | DAP | 8703.23 | легковой автомобиль | 2 | 18400 EUR"


def extract(doc: str, llm: LLMClient) -> dict:
    """Наивное извлечение: промпт строкой, ответ через json.loads."""
    reply = llm.complete(f"Извлеки поля декларации из документа:\n{doc}")
    return json.loads(reply.text)


if __name__ == "__main__":
    llm = FakeLLM(['{"shipment_id": "TKL-000412", "value": 18400}'])
    fields = extract(DOC, llm)
    assert fields["shipment_id"] == "TKL-000412"   # больше ничего не проверено
    print("поля извлечены:", fields)
