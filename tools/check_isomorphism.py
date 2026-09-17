#!/usr/bin/env python3
"""Check that the two locales of the assembled book are structurally
isomorphic and that both match data/spec.json.

Compared per chapter: the ordered list of heading ids, the number and file
names of listings, the code of listings (comments and string contents
ignored, so translated comments and docstrings are allowed), the number of
diagrams, definitions, warnings, notes, asides, quizzes and questions,
tabs and tab panels, goals and recaps, the layer indicator, and the number
of elements at each detail level. Against the spec: the set of chapters,
their section ids and order, their listing names, their diagram counts,
and their layer letters. Anchors of internal links must resolve inside the
same locale. TODO-BOOK markers fail the check.

Usage: tools/check_isomorphism.py [page.html] [--private] [--only=ch-N]
With --only, the spec and anchor checks cover one chapter and links are
resolved against the ids the spec promises, so a chapter can be verified
before its neighbours exist.

Exit codes: 0 — isomorphic; 5 — differences found, report on stdout.
"""
from __future__ import annotations

import io
import json
import pathlib
import sys
import tokenize

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from bookdom import Chapter, Locale, read  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
COUNT_KEYS = ["def", "warn", "note", "aside", "quiz", "question", "tabs", "tabpanel",
              "goals", "recap", "rec", "checklist", "qbank"]


def code_shape(code: str) -> list[str]:
    """The listing reduced to token types and non-string, non-comment values.

    Every string literal, including a whole f-string with its embedded
    expressions, collapses to one STRING token: natural-language strings may
    differ between locales, and a translated f-string may place its
    placeholders in another order.
    """
    out: list[str] = []
    fstart = getattr(tokenize, "FSTRING_START", None)
    fend = getattr(tokenize, "FSTRING_END", None)
    depth = 0
    try:
        for tok in tokenize.generate_tokens(io.StringIO(code + "\n").readline):
            if fstart is not None and tok.type == fstart:
                if depth == 0:
                    out.append("STRING")
                depth += 1
                continue
            if fend is not None and tok.type == fend:
                depth -= 1
                continue
            if depth:
                continue
            if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                            tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING,
                            tokenize.ENDMARKER):
                continue
            if tok.type == tokenize.STRING:
                out.append("STRING")
            else:
                out.append(tok.string)
    except (tokenize.TokenError, SyntaxError):
        return [line.split("#", 1)[0].rstrip() for line in code.splitlines()]
    return out


def compare_locales(a: Locale, b: Locale, report: list[str]) -> None:
    ids_a = [c.id for c in a.chapters]
    ids_b = [c.id for c in b.chapters]
    if ids_a != ids_b:
        report.append(f"- section order differs: {a.code} {ids_a} vs {b.code} {ids_b}")
    for ca in a.chapters:
        cb = b.chapter(ca.id)
        if cb is None:
            continue
        compare_chapter(ca, cb, a.code, b.code, report)


def compare_chapter(ca: Chapter, cb: Chapter, la: str, lb: str, report: list[str]) -> None:
    tag = f"**{ca.id}**"
    ha = [(t, i) for t, i, _ in ca.headings]
    hb = [(t, i) for t, i, _ in cb.headings]
    if ha != hb:
        report.append(f"- {tag}: heading ids differ: {la} {[i for _, i in ha]} vs {lb} {[i for _, i in hb]}")
    if len(ca.listings) != len(cb.listings):
        report.append(f"- {tag}: listings {la} {len(ca.listings)} vs {lb} {len(cb.listings)}")
    else:
        for n, (x, y) in enumerate(zip(ca.listings, cb.listings, strict=True), 1):
            if x.file != y.file:
                report.append(f"- {tag}: listing {n} file name {la} `{x.file}` vs {lb} `{y.file}`")
            if x.attrs.get("data-run") != y.attrs.get("data-run") or x.attrs.get("data-level") != y.attrs.get("data-level"):
                report.append(f"- {tag}: listing {n} (`{x.file}`) data-run/data-level attributes differ")
            if code_shape(x.code) != code_shape(y.code):
                report.append(f"- {tag}: listing {n} (`{x.file}`) code differs beyond comments and strings")
    if len(ca.diagrams) != len(cb.diagrams):
        report.append(f"- {tag}: diagrams {la} {len(ca.diagrams)} vs {lb} {len(cb.diagrams)}")
    for key in COUNT_KEYS:
        if ca.counts.get(key, 0) != cb.counts.get(key, 0):
            report.append(f"- {tag}: {key} count {la} {ca.counts.get(key, 0)} vs {lb} {cb.counts.get(key, 0)}")
    if ca.layers != cb.layers:
        report.append(f"- {tag}: layer indicator {la} `{ca.layers}` vs {lb} `{cb.layers}`")
    for lvl in ("2", "3"):
        if ca.levels.get(lvl, 0) != cb.levels.get(lvl, 0):
            report.append(f"- {tag}: elements at level {lvl}: {la} {ca.levels.get(lvl, 0)} vs {lb} {cb.levels.get(lvl, 0)}")


def compare_spec(loc: Locale, spec: dict, private: bool, report: list[str],
                 only: str | None = None) -> None:
    expected: list[dict] = [c for c in spec["chapters"] if private or not c.get("private")]
    if only:
        expected = [c for c in expected if c["id"] == only]
    present = {c.id: c for c in loc.chapters if c.kind == "chapter"}
    for ch in expected:
        c = present.get(ch["id"])
        if c is None:
            report.append(f"- {loc.code}: chapter {ch['id']} is missing")
            continue
        h3 = [i for t, i, _ in c.headings if t == "h3"]
        want = [s["id"] for s in ch["sections"]]
        if h3 != want:
            report.append(f"- {loc.code} **{ch['id']}**: sections {h3} do not match the spec {want}")
        h2 = [i for t, i, _ in c.headings if t == "h2"]
        if h2 != [f"s-{ch['num']}"]:
            report.append(f"- {loc.code} **{ch['id']}**: chapter heading id {h2} must be s-{ch['num']}")
        files = [x.file.removesuffix(".py") for x in c.listings]
        if files != ch["listings"]:
            report.append(f"- {loc.code} **{ch['id']}**: listings {files} do not match the spec {ch['listings']}")
        if len(c.diagrams) != ch["diagrams"]:
            report.append(f"- {loc.code} **{ch['id']}**: {len(c.diagrams)} diagrams, the spec says {ch['diagrams']}")
        layers = "".join(sorted(x for x in c.layers if x != "."))
        if layers != "".join(sorted(ch["layers"])):
            report.append(f"- {loc.code} **{ch['id']}**: layers `{layers}` do not match the spec `{''.join(sorted(ch['layers']))}`")
        if c.counts.get("question", 0) != 3 and ch["num"] != 0:
            report.append(f"- {loc.code} **{ch['id']}**: {c.counts.get('question', 0)} self-check questions, expected 3")
        if c.counts.get("goals", 0) != 1 or c.counts.get("recap", 0) != 1:
            report.append(f"- {loc.code} **{ch['id']}**: goals/recap blocks must appear exactly once")
    if only:
        return
    for app in spec["appendices"]:
        if app.get("private") and not private:
            continue
        if app["id"] not in present:
            report.append(f"- {loc.code}: appendix {app['id']} is missing")
    for part in spec["parts"]:
        if part.get("private") and not private:
            continue
        if part["id"] not in {c.id for c in loc.chapters}:
            report.append(f"- {loc.code}: part divider {part['id']} is missing")
    extra = set(present) - {c["id"] for c in expected} - {a["id"] for a in spec["appendices"]}
    if extra:
        report.append(f"- {loc.code}: sections not in the spec: {sorted(extra)}")


def spec_ids(spec: dict) -> set[str]:
    """Every id the spec promises: chapters, headings, sections, appendices, parts."""
    ids: set[str] = set()
    for ch in spec["chapters"]:
        ids.update({ch["id"], f"s-{ch['num']}"})
        ids.update(s["id"] for s in ch["sections"])
    for app in spec["appendices"]:
        ids.update({app["id"], f"s-{app['letter'].lower()}"})
    for part in spec["parts"]:
        ids.add(part["id"])
    return ids


def check_anchors(loc: Locale, report: list[str], promised: set[str] | None = None,
                  only: str | None = None) -> None:
    ids: dict[str, int] = {}
    for c in loc.chapters:
        for i in c.ids:
            ids[i] = ids.get(i, 0) + 1
    dup = sorted(i for i, n in ids.items() if n > 1)
    if dup:
        report.append(f"- {loc.code}: duplicate ids {dup}")
    known = set(ids) | (promised or set())
    for c in loc.chapters:
        if only and c.id != only:
            continue
        for target in c.anchors:
            if not target or target in known:
                continue
            # Sub-section anchors (s-N-M-…) of a promised section are accepted while the
            # chapter is absent; once it is present the DOM decides.
            head = "-".join(target.split("-")[:3])
            if head in (promised or set()) and head not in ids:
                continue
            report.append(f"- {loc.code} **{c.id}**: link to missing anchor `#{target}`")


def check(text: str, spec: dict, private: bool = False, only: str | None = None) -> list[str]:
    """Report every violation; ``only`` restricts the spec and anchor checks to one chapter id.

    With ``only``, links are resolved against the ids the spec promises, so a chapter
    can be checked before its neighbours exist. Without it the DOM decides.
    """
    report: list[str] = []
    locales = read(text)
    if [loc.code for loc in locales] != ["ru", "en"]:
        report.append(f"- locales found: {[loc.code for loc in locales]}, expected ru then en")
        return report
    ru, en = locales
    if only:
        ca, cb = ru.chapter(only), en.chapter(only)
        if ca is None or cb is None:
            report.append(f"- chapter {only} is missing in {'ru' if ca is None else 'en'}")
        else:
            compare_chapter(ca, cb, "ru", "en", report)
    else:
        compare_locales(ru, en, report)
    promised = spec_ids(spec) if only else None
    for loc in locales:
        compare_spec(loc, spec, private, report, only)
        check_anchors(loc, report, promised, only)
        if loc.todo:
            report.append(f"- {loc.code}: {loc.todo} TODO-BOOK markers remain")
    return report


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    private = "--private" in sys.argv
    only = None
    for a in sys.argv[1:]:
        if a.startswith("--only="):
            only = a.split("=", 1)[1]
    page = pathlib.Path(args[0] if args else ROOT / "fde-advanced.html")
    from spec_loader import load
    spec = load()
    report = check(page.read_text(encoding="utf-8"), spec, private, only)
    if not report:
        locales = read(page.read_text(encoding="utf-8"))
        n = sum(1 for c in locales[0].chapters if c.kind == "chapter")
        scope = f"chapter {only}" if only else f"{n} sections per locale"
        print(f"isomorphism: ok ({scope}, {page.name})")
        return 0
    print("## Locale isomorphism violated\n")
    print("\n".join(report))
    return 5


if __name__ == "__main__":
    sys.exit(main())
