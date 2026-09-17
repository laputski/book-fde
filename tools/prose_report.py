#!/usr/bin/env python3
"""Candidate sentences for the editorial pass on prose style.

The book states claims directly. Contrast constructions ("не X, а Y",
"X, not Y"), rhetorical set-ups, evaluative framing and metaphorical verbs
are allowed only where they carry meaning, and only a human or a careful
editor can decide that. This tool therefore does not guard anything: it
lists the sentences that match one of the patterns, so that an editor reads
each of them and keeps, rewrites or deletes it. Code listings are skipped;
figure captions, glosses, tables and the texts of diagram steps are read.

Usage: tools/prose_report.py [--list] [source files…]   (default: parts/, private/parts/)
Always exits 0; prints counts per file and category, and with --list the sentences.
"""
from __future__ import annotations

import html
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

PATTERNS: dict[str, re.Pattern[str]] = {
    "contrast": re.compile(
        r"(?<![\w-])[Нн]е (?:[^.;:!?]{1,80}?), а (?!также|затем|потом|значит|именно)"
        r"|, а не |не столько [^.;:!?]{1,60} сколько|не просто "
        r"|(?<![\w-])[Nn]ot (?:[^.;:!?]{1,80}?), but |, not |\brather than\b|\bnot (?:just|merely|simply)\b"),
    "set-up": re.compile(
        r"другое:|[Оо]твет прост|[Вв]от почему|[Ии]менно поэтому|[Дд]ело не в |[Вв]опрос не в |[Сс]уть в том"
        r"|\b[Tt]he questions are different\b|\b[Hh]ere is why\b|\b[Tt]he answer is simple\b|\b[Tt]he catch\b"
        r"|\b[Tt]he point is\b|\bis different:"),
    "evaluative": re.compile(
        r"звучит|на первый взгляд|(?<![\w-])кажется|коварн|по-настоящему|(?<![\w-])настоящ\w*|(?<![\w-])ключев(?:ой|ая|ое|ые|ого|ую|ых|ым|ыми)\b"
        r"|критически важн|огромн|элегантн|(?<![\w-])красив|(?<![\w-])мощн(?:ый|ая|ое|ые|ого|ым|ыми)\b|удивительн"
        r"|\bsounds (?:simple|easy)\b|\bdeceptively\b|\b[Tt]he real\b|\bcrucial\w*|\bpowerful\b|\belegant\b|\bhuge\b"
        r"|\bseemingly\b|\bat first glance\b|\bsurprising\w*"),
    "metaphor": re.compile(
        r"(?<![\w-])(?:живёт|живут|жить|принадлежит|принадлежат|лечится|лечатся|едет|едут|бросает кости)\b"
        r"|\blives? in\b|\bbelongs? to\b|\bis cured\b|\brides? along\b"),
}

PRE = re.compile(r"<pre>.*?</pre>", re.S)
ATTR = re.compile(r'\s(?:data-caption|aria-label)="([^"]*)"')
TAG = re.compile(r"<[^>]+>")
SENTENCE = re.compile(r"(?<=[.!?])\s+")


def sentences(source: str) -> list[str]:
    """Readable sentences of a chapter file: code removed, captions of diagram steps kept."""
    text = PRE.sub(" ", source)
    captions = " ".join(value.rstrip(".") + "." for value in ATTR.findall(text))
    text = TAG.sub(" ", text) + " " + captions
    text = html.unescape(text)
    return [" ".join(s.split()) for s in SENTENCE.split(text) if s.strip()]


def candidates(source: str) -> list[tuple[str, str]]:
    """(category, sentence) for every sentence matching a pattern."""
    out: list[tuple[str, str]] = []
    for sentence in sentences(source):
        for name, pattern in PATTERNS.items():
            if pattern.search(sentence):
                out.append((name, sentence))
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--list"]
    listing = "--list" in sys.argv
    files = [pathlib.Path(a) for a in args] if args else sorted(
        list((ROOT / "parts").glob("*/*.html")) + list((ROOT / "private" / "parts").glob("*/*.html")))
    totals = dict.fromkeys(PATTERNS, 0)
    for f in files:
        found = candidates(f.read_text(encoding="utf-8"))
        counts = dict.fromkeys(PATTERNS, 0)
        for name, _ in found:
            counts[name] += 1
            totals[name] += 1
        print(f"{f}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        if listing:
            for name, sentence in found:
                print(f"  [{name}] {sentence}")
    print("total: " + ", ".join(f"{k} {v}" for k, v in totals.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
