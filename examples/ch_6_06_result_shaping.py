from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class Shaped:
    rows: list[dict[str, Any]]
    total: int
    summary: dict[str, Any]
    next_cursor: int | None


def shape(rows: list[dict[str, Any]], cursor: int, limit_bytes: int) -> Shaped:
    """Первая страница, укладывающаяся в бюджет, плюс сводка по всему набору."""
    summary = {"count": len(rows), "sum": sum(r["amount"] for r in rows),
               "first": rows[0]["date"] if rows else None, "last": rows[-1]["date"] if rows else None}
    page: list[dict[str, Any]] = []
    used = len(json.dumps(summary))
    i = cursor
    while i < len(rows):
        size = len(json.dumps(rows[i], ensure_ascii=False))
        if used + size > limit_bytes:
            break
        page.append(rows[i])
        used += size
        i += 1
    return Shaped(page, len(rows), summary, i if i < len(rows) else None)


if __name__ == "__main__":
    ops = [{"id": i, "date": f"2026-0{1 + i % 9}-01", "amount": 10 + i} for i in range(400)]
    first = shape(ops, cursor=0, limit_bytes=2_000)
    assert 0 < len(first.rows) < 400 and first.next_cursor is not None
    assert first.summary["count"] == 400 and first.summary["sum"] == sum(10 + i for i in range(400))
    second = shape(ops, cursor=first.next_cursor, limit_bytes=2_000)
    assert second.rows[0]["id"] == first.rows[-1]["id"] + 1
    print("страница по бюджету, сводка по всему набору, курсор для продолжения")
