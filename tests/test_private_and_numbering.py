from __future__ import annotations

from check_private import leaks, private_ids
from conftest import CODE_EN, CODE_RU, chapter, page
from number_figures import number

SECS = [("s-1-1", "One"), ("s-1-2", "Two")]


def test_numbering_restarts_per_locale():
    text = page(chapter("ru", 1, "Г", SECS, CODE_RU) + chapter("ru", 2, "Г", SECS, CODE_RU),
                chapter("en", 1, "C", SECS, CODE_EN) + chapter("en", 2, "C", SECS, CODE_EN))
    out = number(text)
    assert out.count("<b>Диаграмма 1.</b>") == 1 and out.count("<b>Диаграмма 2.</b>") == 1
    assert out.count("<b>Diagram 1.</b>") == 1 and out.count("<b>Diagram 2.</b>") == 1
    assert "{{DIA}}" not in out


def test_private_ids_from_spec(spec):
    ids = private_ids(spec)
    assert "ch-19" in ids and "s-19-1" in ids and "app-q" in ids and "ch-1" not in ids


def test_clean_public_page_has_no_leak(good_page, spec):
    assert leaks(good_page, private_ids(spec)) == []


def test_bait_link_to_private_chapter(spec):
    extra = '<p><a href="#ch-19">local-only part</a></p>'
    text = page(chapter("ru", 1, "Г", SECS, CODE_RU, extra=extra), chapter("en", 1, "C", SECS, CODE_EN, extra=extra))
    found = leaks(text, private_ids(spec))
    assert found and "ch-19" in found[0]


def test_bait_private_section_present(spec):
    text = page(chapter("ru", 19, "Г", [("s-19-1", "x")], CODE_RU), chapter("en", 19, "C", [("s-19-1", "x")], CODE_EN))
    found = leaks(text, private_ids(spec))
    assert any("ch-19" in line for line in found) and any("s-19-1" in line for line in found)
