#!/usr/bin/env python3
"""Contrast of the book's colours on every ground of every theme.

Diagram labels are drawn with layer colours. The Okabe and Ito hues are
chosen to stay distinguishable for colour-blind readers, but several of them
are too light for small text on a white page. The page therefore maps every
diagram label written with var(--sX) to a label token var(--tX), and every
line or fill to a graphic token var(--gX). This tool reads parts/00-head.html
and checks, for the light theme, both dark theme blocks and the print block:

  * body text, muted text and the seven label tokens reach 4.5:1 (WCAG 1.4.3)
    against --bg, --paper and --sunk;
  * the seven graphic tokens reach 3:1 (WCAG 1.4.11) against the same grounds;
  * the CSS rules that apply the tokens to diagram labels, lines and fills
    exist for all seven layers.

Usage: tools/check_contrast.py [head file]   (default: parts/00-head.html)
Exit codes: 0 — every pair passes; 10 — violations, report on stdout.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LAYERS = "ABCDEFG"
GROUNDS = ("bg", "paper", "sunk")
TEXT_MIN = 4.5
GRAPHIC_MIN = 3.0

BLOCKS = {
    "light": re.compile(r"(?<![\w\]\)])\s*:root\{(.*?)\}", re.S),
    "dark (system)": re.compile(r"prefers-color-scheme:dark\)\{\s*:root:not\(\[data-theme=\"light\"\]\)\{(.*?)\}", re.S),
    "dark (toggle)": re.compile(r"\n:root\[data-theme=\"dark\"\]\{(.*?)\}", re.S),
    "print": re.compile(r"@media print\{.*?:root:not\(\[data-theme=\"light\"\]\)\{(.*?)\}", re.S),
}
TOKEN = re.compile(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6}|#[0-9A-Fa-f]{3})\b")


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def ratio(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def themes(css: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for name, pattern in BLOCKS.items():
        match = pattern.search(css)
        out[name] = dict(TOKEN.findall(match.group(1))) if match else {}
    return out


def violations(css: str) -> list[str]:
    report: list[str] = []
    for name, tokens in themes(css).items():
        if not tokens:
            report.append(f"- {name}: theme block not found")
            continue
        grounds = {g: tokens[g] for g in GROUNDS if g in tokens}
        missing = [g for g in GROUNDS if g not in tokens]
        if missing:
            report.append(f"- {name}: grounds not defined: {', '.join(missing)}")
        required = [("text", TEXT_MIN), ("muted", TEXT_MIN)]
        required += [(f"t{x}", TEXT_MIN) for x in LAYERS] + [(f"g{x}", GRAPHIC_MIN) for x in LAYERS]
        for token, minimum in required:
            if token not in tokens:
                report.append(f"- {name}: --{token} is not defined")
                continue
            for ground, colour in grounds.items():
                value = ratio(tokens[token], colour)
                if value < minimum:
                    report.append(f"- {name}: --{token} {tokens[token]} on --{ground} {colour} "
                                  f"is {value:.2f}:1, needs {minimum}:1")
    compact = re.sub(r"\s+", "", css)
    for x in LAYERS:
        rules = (f'figure.diasvgtext[fill="var(--s{x})"]{{fill:var(--t{x})}}',
                 f'figure.diasvg[stroke="var(--s{x})"]{{stroke:var(--g{x})}}',
                 f'figure.diasvg:not(text)[fill="var(--s{x})"]{{fill:var(--g{x})}}')
        for rule in rules:
            if rule not in compact:
                report.append(f"- rule missing: {rule}")
    return report


def main() -> int:
    path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "parts" / "00-head.html"
    report = violations(path.read_text(encoding="utf-8"))
    if not report:
        print(f"contrast: ok ({len(BLOCKS)} themes, {len(LAYERS)} layers, {path.name})")
        return 0
    print("## Colours below the contrast minimum or not applied to diagrams\n")
    print("\n".join(report))
    return 10


if __name__ == "__main__":
    sys.exit(main())
