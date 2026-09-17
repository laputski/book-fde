#!/usr/bin/env python3
"""Number the diagrams of the assembled book.

Authors write ``<b>Диаграмма {{DIA}}.</b>`` and ``<b>Diagram {{DIA}}.</b>``;
the numbering is continuous inside each locale and restarts at every
``<div class="locale"`` boundary, so both locales number their diagrams
identically. Reads the assembled page on stdin, writes it to stdout.
"""
import re
import sys

LOCALE = re.compile(r'<div class="locale"')
PLACEHOLDER = "{{DIA}}"


def number(text: str) -> str:
    pieces = LOCALE.split(text)
    marker = '<div class="locale"'
    out = [pieces[0]]
    for piece in pieces[1:]:
        counter = 0
        parts = piece.split(PLACEHOLDER)
        numbered = parts[0]
        for rest in parts[1:]:
            counter += 1
            numbered += str(counter) + rest
        out.append(marker + numbered)
    return "".join(out)


if __name__ == "__main__":
    sys.stdout.write(number(sys.stdin.read()))
