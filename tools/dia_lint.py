#!/usr/bin/env python3
"""The diagram rules of the book, enforced.

For every <figure class="dia"> of the assembled page:
  - the <svg> has a viewBox, role="img" and an aria-label of a full sentence;
  - colour comes only from currentColor and CSS variables: no hex, no rgb();
  - stroke widths do not exceed 2; corner radii come from the allowed set;
  - the marker ids are unique inside the locale;
  - the caption opens with "Диаграмма N." / "Diagram N." and the numbers
    run 1, 2, 3, … through the locale without gaps (no {{DIA}} left);
  - a stepped diagram (data-steps) numbers its groups 1..n contiguously;
  - the k-th diagram of the Russian locale and the k-th of the English one
    share the same geometry: the SVG bodies are identical once <text>
    elements are removed, so only labels may differ between locales.

Exit codes: 0 — clean; 6 — violations, report on stdout.
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from bookdom import Diagram, read  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEX = re.compile(r'(?:fill|stroke|stop-color|color)\s*=\s*"\s*#[0-9a-fA-F]{3,8}\b')
STYLE_HEX = re.compile(r'style\s*=\s*"[^"]*#[0-9a-fA-F]{3,8}')
RGB = re.compile(r'rgba?\(')
WIDTH = re.compile(r'stroke-width\s*=\s*"([0-9.]+)"')
RX = re.compile(r'\brx\s*=\s*"([0-9.]+)"')
MARKER = re.compile(r'<marker[^>]*\bid\s*=\s*"([^"]+)"')
TEXT = re.compile(r'<text\b[^>]*>.*?</text>', re.S)
TITLE = re.compile(r'<title\b[^>]*>.*?</title>', re.S)
CAPTION = {"ru": re.compile(r'^Диаграмма (\d+)\.'), "en": re.compile(r'^Diagram (\d+)\.')}
ALLOWED_RX = {2, 3, 4, 5, 6, 8, 18, 20, 22, 24, 26, 28, 30}


def lint_one(d: Diagram, locale: str, k: int, seen_markers: set[str], report: list[str]) -> None:
    tag = f"- {locale} **{d.chapter}** diagram {k}"
    if not d.attrs.get("viewbox"):
        report.append(f"{tag}: missing viewBox")
    if d.attrs.get("role") != "img":
        report.append(f"{tag}: role must be \"img\"")
    label = d.attrs.get("aria-label", "")
    if len(label) < 40:
        report.append(f"{tag}: aria-label too short ({len(label)} characters); write a full sentence")
    if HEX.search(d.body) or STYLE_HEX.search(d.body) or RGB.search(d.body):
        report.append(f"{tag}: literal colour found; use currentColor or var(--sA…--sG, --muted, --line)")
    for w in WIDTH.findall(d.body):
        if float(w) > 2:
            report.append(f"{tag}: stroke-width {w} exceeds 2")
    for r in RX.findall(d.body):
        if float(r) not in ALLOWED_RX:
            report.append(f"{tag}: rx={r} is outside the allowed set {sorted(ALLOWED_RX)}")
    for m in MARKER.findall(d.body):
        if m in seen_markers:
            report.append(f"{tag}: marker id `{m}` already used in this locale")
        seen_markers.add(m)
    if "{{DIA}}" in d.caption:
        report.append(f"{tag}: unnumbered caption placeholder remains")
    m = CAPTION[locale].match(d.caption) if locale in CAPTION else None
    if not m:
        report.append(f"{tag}: caption must open with the numbered label; got `{d.caption[:40]}`")
    elif int(m.group(1)) != k:
        report.append(f"{tag}: caption number {m.group(1)} but this is diagram {k} of the locale")
    if d.steps:
        want = [str(i) for i in range(1, len(d.steps) + 1)]
        if sorted(d.steps, key=int) != want:
            report.append(f"{tag}: data-step values {d.steps} are not 1..{len(d.steps)}")


CAPTION_ATTR = re.compile(r'\s+data-caption="[^"]*"')


def geometry(body: str) -> str:
    """The SVG without its language-bearing parts: <text>, <title>, data-caption."""
    stripped = CAPTION_ATTR.sub("", TITLE.sub("", TEXT.sub("", body)))
    return " ".join(stripped.split())


def lint(text: str) -> list[str]:
    report: list[str] = []
    locales = read(text)
    per_locale: dict[str, list[Diagram]] = {}
    for loc in locales:
        dias = [d for c in loc.chapters for d in c.diagrams]
        per_locale[loc.code] = dias
        markers: set[str] = set()
        for k, d in enumerate(dias, 1):
            lint_one(d, loc.code, k, markers, report)
    if set(per_locale) == {"ru", "en"}:
        ru, en = per_locale["ru"], per_locale["en"]
        if len(ru) != len(en):
            report.append(f"- diagram count differs: ru {len(ru)}, en {len(en)}")
        for k, (a, b) in enumerate(zip(ru, en, strict=False), 1):
            if geometry(a.body) != geometry(b.body):
                report.append(f"- diagram {k} ({a.chapter}): geometry differs between locales beyond <text> elements")
    return report


def main() -> int:
    page = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "fde-advanced.html")
    text = page.read_text(encoding="utf-8")
    report = lint(text)
    if not report:
        n = len([d for c in read(text)[0].chapters for d in c.diagrams])
        print(f"diagrams: ok ({n} per locale, {page.name})")
        return 0
    print("## Diagram rules violated\n")
    print("\n".join(report))
    return 6


if __name__ == "__main__":
    sys.exit(main())
