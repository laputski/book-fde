from __future__ import annotations

import json
from pathlib import Path

from check_isomorphism import check
from check_private import leaks, private_ids
from conftest import CODE_EN, CODE_RU, chapter, page
from spec_loader import PUBLIC, load, merge, stub_violations

STUB = {"num": 19, "id": "ch-19", "file": "70-ch-19", "private": True}
FULL = {**STUB, "title": {"ru": "Т", "en": "T"}, "sections": [{"id": "s-19-1"}], "listings": [], "diagrams": 0}


def public_spec() -> dict:
    return {"chapters": [{"num": 1, "id": "ch-1"}, STUB], "appendices": [], "parts": []}


def test_merge_replaces_stubs_with_full_private_entries():
    merged = merge(public_spec(), {"chapters": [FULL]})
    assert merged["chapters"][1] == FULL and merged["chapters"][0] == {"num": 1, "id": "ch-1"}


def test_published_spec_holds_stubs_only():
    assert stub_violations(json.loads(PUBLIC.read_text(encoding="utf-8"))) == []


def test_bait_private_title_in_published_spec():
    leaked = public_spec()
    leaked["chapters"][1] = {**STUB, "title": {"en": "Local-only Part"}}
    assert stub_violations(leaked) == [
        "- data/spec.json chapters `ch-19` is private but publishes title"]


def test_boundary_works_from_stubs_alone_as_in_ci(tmp_path: Path):
    spec = load(private_path=tmp_path / "absent.json")          # CI has no private/ directory
    ids = private_ids(spec)
    assert "ch-19" in ids and "app-q" in ids and "part-6" in ids
    link = '<p><a href="#s-19-1">round</a></p>'
    text = page(chapter("ru", 1, "Г", [("s-1-1", "x")], CODE_RU, extra=link),
                chapter("en", 1, "C", [("s-1-1", "x")], CODE_EN, extra=link))
    assert any("s-19" in line for line in leaks(text, ids))


def test_public_isomorphism_ignores_private_stubs():
    spec = {"chapters": [{"num": 1, "id": "ch-1", "layers": ["F", "G"], "diagrams": 1,
                          "listings": ["engagement"], "sections": [{"id": "s-1-1"}, {"id": "s-1-2"}]}, STUB],
            "appendices": [], "parts": []}
    secs = [("s-1-1", "One"), ("s-1-2", "Two")]
    text = page(chapter("ru", 1, "Глава", secs, CODE_RU), chapter("en", 1, "Chapter", secs, CODE_EN))
    assert check(text, spec) == []
