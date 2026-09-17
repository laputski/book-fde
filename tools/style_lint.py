#!/usr/bin/env python3
"""House style of the book's prose, enforced where a machine can decide.

The book replaces long dashes used as connectors with verbs. Any em dash
(U+2014) outside code listings is reported with its file, line and context:
in headings, paragraphs, table cells, captions and diagram labels alike.
A diagram referred to by number in the text ("диаграмма 3", "Diagram 15")
is reported too: the build numbers diagrams across the whole book, so a
number written by hand is wrong as soon as a chapter moves. Code listings
(<pre>…</pre>) and fenced Markdown code blocks are exempt.

Usage: tools/style_lint.py [source files…]
       (default: parts/, private/parts/ and the repository's Markdown documents)
Exit codes: 0 — clean; 8 — violations, report on stdout.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRE = re.compile(r"<pre>.*?</pre>|^```.*?^```", re.S | re.M)
DOCUMENTS = ("README.md", "README.ru.md", "CONTRIBUTING.md")
DASH = "—"
DIAGRAM_NUMBER = re.compile(r"(?<![\w{])(?:[Дд]иаграм\w*|[Dd]iagrams?)\s+\d+")
# The English locale uses British spelling. Lower-case American forms are
# reported outside code, attributes and the titles of cited sources; proper
# names are capitalised ("World Health Organization") and therefore pass.
AMERICAN = re.compile(
    r"\b(?:behavior\w*|organiz\w*|artifact\w*|modeling|modeled|catalogs?|analyz\w*|optimiz\w*"
    r"|prioritiz\w*|normaliz\w*|serializ\w*|summariz\w*|utiliz\w*|minimiz\w*|maximiz\w*|recogniz\w*"
    r"|standardiz\w*|centraliz\w*|authoriz\w*|categoriz\w*|visualiz\w*|customiz\w*|finaliz\w*"
    r"|initializ\w*|tokeniz\w*|favor\w*|color\w*|labeled|labeling|canceled|canceling|percent)\b")
AMERICAN_ALLOWED = ("AWS organization",)
NOT_PROSE = re.compile(r'<pre>.*?</pre>|<code>.*?</code>|<a class="src"[^>]*>.*?</a>|<span class="file">.*?</span>'
                       r'|\s[\w-]+="[^"]*"', re.S)


def violations(text: str, english: bool = False) -> list[tuple[int, str]]:
    """(line, context) for every em dash or hand-written diagram number outside code,
    and, for an English file, every American spelling outside code and cited titles."""
    masked = PRE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    found = [*re.finditer(DASH, masked), *DIAGRAM_NUMBER.finditer(masked)]
    if english:
        for allowed in AMERICAN_ALLOWED:
            masked = masked.replace(allowed, " " * len(allowed))
        prose = NOT_PROSE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), masked)
        found += list(AMERICAN.finditer(prose))
    out: list[tuple[int, str]] = []
    for m in sorted(found, key=lambda m: m.start()):
        line = masked.count("\n", 0, m.start()) + 1
        start = max(0, m.start() - 40)
        context = re.sub(r"<[^>]+>", "", text[start:m.end() + 30]).replace("\n", " ")
        out.append((line, context.strip()))
    return out


def default_files() -> list[pathlib.Path]:
    """Chapter sources of both builds plus the Markdown documents of the repository."""
    chapters = list((ROOT / "parts").glob("*/*.html")) + list((ROOT / "private" / "parts").glob("*/*.html"))
    return sorted(chapters) + [ROOT / name for name in DOCUMENTS if (ROOT / name).exists()]


def main() -> int:
    args = sys.argv[1:]
    files = [pathlib.Path(a) for a in args] if args else default_files()
    report: list[str] = []
    for f in files:
        english = "en" in f.parts and f.suffix == ".html"
        for line, context in violations(f.read_text(encoding="utf-8"), english):
            report.append(f"- {f.relative_to(ROOT) if f.is_absolute() else f}:{line}: …{context}…")
    if not report:
        print(f"style: ok ({len(files)} files)")
        return 0
    print("## Em dashes (replace with verbs), hand-written diagram numbers (refer to the section)"
          " or American spellings in the English locale (use British forms)\n")
    print("\n".join(report))
    return 8


if __name__ == "__main__":
    sys.exit(main())
