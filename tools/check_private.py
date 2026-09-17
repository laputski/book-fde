#!/usr/bin/env python3
"""The public/private boundary of the book.

The public build must not contain the private chapters, any link to their
ids, or any mention of their section ids. The private ids come from
the stubs of data/spec.json (chapters, parts and appendices marked "private").
The published spec itself must hold stubs only (tools/spec_loader.py).

Exit codes: 0 — clean; 7 — a private id leaked into the public build.
"""
from __future__ import annotations

import pathlib
import re
import sys

from spec_loader import PUBLIC, load, stub_violations

ROOT = pathlib.Path(__file__).resolve().parent.parent


def private_ids(spec: dict) -> list[str]:
    ids: list[str] = []
    for ch in spec["chapters"]:
        if ch.get("private"):
            ids.append(ch["id"])
            ids.append(f"s-{ch['num']}")
            ids.extend(s["id"] for s in ch.get("sections", []))
    for app in spec["appendices"]:
        if app.get("private"):
            ids.append(app["id"])
            if "letter" in app:
                ids.append(f"s-{app['letter'].lower()}")
    for part in spec["parts"]:
        if part.get("private"):
            ids.append(part["id"])
    return ids


def leaks(text: str, ids: list[str]) -> list[str]:
    found: list[str] = []
    for i in ids:
        pattern = re.compile(r'(?:id="' + re.escape(i) + r'"|href="#' + re.escape(i) + r'(?:"|-))')
        n = len(pattern.findall(text))
        if n:
            found.append(f"- `{i}` appears {n} time(s)")
    return found


def main() -> int:
    page = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "fde-advanced.html")
    import json
    report = stub_violations(json.loads(PUBLIC.read_text(encoding="utf-8")))
    report += leaks(page.read_text(encoding="utf-8"), private_ids(load()))
    if not report:
        print(f"public/private boundary: ok ({page.name})")
        return 0
    print("## Private content leaked into the public build\n")
    print("\n".join(report))
    return 7


if __name__ == "__main__":
    sys.exit(main())
