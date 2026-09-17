#!/usr/bin/env python3
"""Renumber the line references of the annotations under a listing.

An annotation row is ``<div><span class="at">строка N</span>…`` (or ``line N``).
Authors may write ``<span class="at" data-anchor="unique code fragment">строка ?</span>``:
this tool finds the fragment inside the figure's code, replaces ``?`` with the
1-based line number, and keeps ``data-anchor`` so the reference survives edits.
Rows without ``data-anchor`` are left untouched.

Usage: tools/gloss_lines.py parts/ru/23-ch-06.html [more files…]
"""
from __future__ import annotations

import html
import pathlib
import re
import sys

FIGURE = re.compile(r'(<figure class="code"[^>]*>)(.*?)(</figure>)', re.S)
CODE = re.compile(r"<pre><code>(.*?)</code></pre>", re.S)
ROW = re.compile(r'<span class="at" data-anchor="([^"]+)">(строка|line) [^<]*</span>')


def renumber(text: str) -> tuple[str, int, list[str]]:
    fixed = 0
    problems: list[str] = []

    def per_figure(m: re.Match[str]) -> str:
        nonlocal fixed
        body = m.group(2)
        code = CODE.search(body)
        if not code:
            return m.group(0)
        lines = html.unescape(code.group(1)).strip("\n").splitlines()

        def per_row(r: re.Match[str]) -> str:
            nonlocal fixed
            anchor = html.unescape(r.group(1))
            hits = [i for i, line in enumerate(lines, 1) if anchor in line]
            if len(hits) != 1:
                problems.append(f"anchor `{anchor}`: {len(hits)} matches")
                return r.group(0)
            fixed += 1
            return f'<span class="at" data-anchor="{r.group(1)}">{r.group(2)} {hits[0]}</span>'
        return m.group(1) + ROW.sub(per_row, body) + m.group(3)

    return FIGURE.sub(per_figure, text), fixed, problems


def main() -> int:
    bad = 0
    for name in sys.argv[1:]:
        path = pathlib.Path(name)
        out, fixed, problems = renumber(path.read_text(encoding="utf-8"))
        path.write_text(out, encoding="utf-8")
        print(f"{path}: {fixed} references renumbered")
        for p in problems:
            print("  ", p)
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
