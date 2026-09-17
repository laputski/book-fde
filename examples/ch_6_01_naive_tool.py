import json

ACCOUNTS = [{"id": str(i), "name": f"client {i}", "iban": f"NB00{i:04d}", "balance": str(i * 10)}
            for i in range(2000)]


def tool(query: str) -> str:
    """Поиск по счетам."""
    rows = [a for a in ACCOUNTS if query in a["name"]]
    return json.dumps(rows)


if __name__ == "__main__":
    out = tool("client")
    print(len(out), "символов ответа на один вопрос")   # ~150 000
