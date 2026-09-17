#!/usr/bin/env python3
"""Appendix B promises, for every tool, the name that models it in the listings.

The third column of each table in Appendix B ("stub in the listings") names
classes or functions in <code> elements. Every such name must be defined at
module level by a listing of the same page or by examples/stubs.py, and both
locales must promise the same names. A name that no listing defines is a
false statement of the book about itself.

Usage: tools/check_reference.py [page]   (default: fde-advanced.html)
Exit codes: 0 — every promised name exists; 9 — violations, report on stdout.
"""
from __future__ import annotations

import ast
import html
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCALE = re.compile(r'<div class="locale" data-locale="(ru|en)">')
APP_B = re.compile(r'<section class="chapter" id="app-b">(.*?)</section>', re.S)
ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
CELL = re.compile(r"<td>(.*?)</td>", re.S)
CODE_NAME = re.compile(r"<code>([A-Za-z_][A-Za-z0-9_]*)</code>")
LISTING = re.compile(r'<figure class="code"[^>]*>.*?<pre><code>(.*?)</code></pre>', re.S)


def locales(page: str) -> dict[str, str]:
    marks = [(m.start(), m.group(1)) for m in LOCALE.finditer(page)]
    return {loc: page[start:(marks[i + 1][0] if i + 1 < len(marks) else len(page))]
            for i, (start, loc) in enumerate(marks)}


def defined_names(source: str) -> set[str]:
    """Module-level classes, functions and assigned names of one listing."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def promised_names(block: str) -> list[str]:
    """Names in the third column of every Appendix B table row, in order."""
    section = APP_B.search(block)
    if not section:
        return []
    out: list[str] = []
    for row in ROW.findall(section.group(1)):
        cells = CELL.findall(row)
        if len(cells) >= 3:
            out.extend(CODE_NAME.findall(cells[2]))
    return out


def check(page: str, stubs: str) -> list[str]:
    known = defined_names(stubs)
    blocks = locales(page)
    for block in blocks.values():
        for code in LISTING.findall(block):
            known |= defined_names(html.unescape(code))
    report: list[str] = []
    promised = {loc: promised_names(block) for loc, block in blocks.items()}
    for loc, names in promised.items():
        report.extend(f"- {loc}: Appendix B names `{n}`, which no listing or stub defines"
                      for n in names if n not in known)
    if len(promised) == 2 and promised.get("ru") != promised.get("en"):
        report.append(f"- the locales promise different names: ru {promised.get('ru')}, en {promised.get('en')}")
    return report


def main() -> int:
    page_path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "fde-advanced.html"
    page = page_path.read_text(encoding="utf-8")
    stubs = (ROOT / "examples" / "stubs.py").read_text(encoding="utf-8")
    report = check(page, stubs)
    if not report:
        count = len(promised_names(locales(page).get("ru", "")))
        print(f"reference: ok ({count} names promised by Appendix B, {page_path.name})")
        return 0
    print("## Appendix B promises names that the listings do not define\n")
    print("\n".join(report))
    return 9


if __name__ == "__main__":
    sys.exit(main())
