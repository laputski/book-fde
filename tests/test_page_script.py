from __future__ import annotations

import re

from conftest import ROOT

TAIL = (ROOT / "parts" / "99-tail.html").read_text(encoding="utf-8")


def function_body(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    depth, i = 0, source.index("{", start)
    for j in range(i, len(source)):
        depth += {"{": 1, "}": -1}.get(source[j], 0)
        if depth == 0:
            return source[i:j + 1]
    raise AssertionError(f"unbalanced function {name}")


def skips_hidden_headings(body: str) -> bool:
    """The scroll spy ignores headings without a layout box before comparing tops."""
    loop = re.search(r"for \(const el of heads\) \{(.*?)getBoundingClientRect\(\)\.top", body, re.S)
    return bool(loop and re.search(r"getClientRects\(\)\.length === 0\) continue", loop.group(1)))


def test_scroll_spy_skips_headings_of_hidden_levels():
    # Defect observed on 2026-09-17: at the Overview and Standard levels the hidden
    # "In depth" heading of chapter 1 reported top 0 and kept the rail on chapter 1.
    assert skips_hidden_headings(function_body(TAIL, "markHere"))


def test_bait_scroll_spy_without_the_guard():
    body = function_body(TAIL, "markHere")
    broken = re.sub(r"\s*if \(el\.getClientRects\(\)\.length === 0\) continue;", "", body)
    assert broken != body and not skips_hidden_headings(broken)
