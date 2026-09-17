#!/usr/bin/env python3
"""Extract the book's listings into separate files for tool verification.

Reads the assembled page (fde-advanced.html by default, or the path given
as the first argument) and writes one .py file per listing into the output
directory (examples/ by default, or the second argument). Listings whose
figure carries data-run="no" are extracted but excluded from execution;
the decision is recorded in <out>/manifest.json.
"""
import html
import json
import pathlib
import re
import sys

FIGURE = re.compile(r'<figure class="code"([^>]*)>(.*?)</figure>', re.S)
CHAPTER = re.compile(r'<section class="chapter" id="([^"]+)"')
FILENAME = re.compile(r'<span class="file">([^<]+)</span>')
CODE = re.compile(r"<pre><code>(.*?)</code></pre>", re.S)
NORUN = re.compile(r'data-run="no"')


def chapters(text: str):
    marks = [(m.start(), m.group(1)) for m in CHAPTER.finditer(text)]

    def at(pos: int) -> str:
        current = "intro"
        for start, name in marks:
            if start <= pos:
                current = name
            else:
                break
        return current
    return at


def extract(text: str, out: pathlib.Path) -> dict[str, bool]:
    """Write the listings of ``text`` into ``out``; return the run manifest."""
    where = chapters(text)
    en_start = text.find('<div class="locale" data-locale="en">')
    out.mkdir(exist_ok=True)
    for old in out.glob("*.py"):
        if old.name != "stubs.py":       # the stubs are maintained by hand
            old.unlink()
    counters: dict[str, int] = {}
    manifest: dict[str, bool] = {}
    for match in FIGURE.finditer(text):
        attrs, body = match.group(1), match.group(2)
        code = CODE.search(body)
        if not code:
            continue
        source = html.unescape(code.group(1)).strip("\n")
        chapter = where(match.start())
        is_en = 0 <= en_start <= match.start()
        locale_key = ("en:" if is_en else "ru:") + chapter
        counters[locale_key] = counters.get(locale_key, 0) + 1
        named = FILENAME.search(body)
        stem = named.group(1).rsplit("/", 1)[-1].removesuffix(".py") if named else "listing"
        stem = re.sub(r"[^a-z0-9_]", "_", stem.lower())
        prefix = "en_" if is_en else ""
        name = f"{prefix}{chapter.replace('-', '_')}_{counters[locale_key]:02d}_{stem}.py"
        (out / name).write_text(source + "\n", encoding="utf-8")
        manifest[name] = NORUN.search(attrs) is None
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "fde-advanced.html")
    out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "examples")
    manifest = extract(src.read_text(encoding="utf-8"), out)
    runnable = sum(1 for v in manifest.values() if v)
    print(f"listings extracted: {len(manifest)}, runnable: {runnable}")


if __name__ == "__main__":
    main()
