from __future__ import annotations

from check_isomorphism import check
from conftest import CODE_EN, CODE_RU, chapter, page


def test_good_page_is_isomorphic(numbered, spec):
    assert check(numbered, spec) == []


def test_translated_comments_and_docstrings_are_allowed(numbered, spec):
    # CODE_RU and CODE_EN differ only in comments and strings: already covered by the good page.
    assert "code differs" not in " ".join(check(numbered, spec))


def test_bait_extra_listing_in_one_locale(spec):
    secs = [("s-1-1", "One"), ("s-1-2", "Two")]
    extra = '<figure class="code" data-fold="0"><pre><code>x = 1</code></pre></figure>'
    text = page(chapter("ru", 1, "Глава", secs, CODE_RU), chapter("en", 1, "Chapter", secs, CODE_EN, extra=extra))
    report = check(text, spec)
    assert any("listings ru 1 vs en 2" in line for line in report), report


def test_bait_code_changed_beyond_comments(spec):
    secs = [("s-1-1", "One"), ("s-1-2", "Two")]
    text = page(chapter("ru", 1, "Глава", secs, CODE_RU),
                chapter("en", 1, "Chapter", secs, CODE_EN.replace("weeks = 12", "weeks = 13")))
    report = check(text, spec)
    assert any("code differs beyond comments" in line for line in report), report


def test_bait_missing_section_against_spec(spec):
    secs = [("s-1-1", "One")]
    text = page(chapter("ru", 1, "Глава", secs, CODE_RU), chapter("en", 1, "Chapter", secs, CODE_EN))
    report = check(text, spec)
    assert any("do not match the spec" in line and "sections" in line for line in report), report


def test_bait_layers_mismatch(spec):
    secs = [("s-1-1", "One"), ("s-1-2", "Two")]
    text = page(chapter("ru", 1, "Глава", secs, CODE_RU, layers="FG"),
                chapter("en", 1, "Chapter", secs, CODE_EN, layers="AB"))
    report = check(text, spec)
    assert any("layer indicator" in line for line in report), report


def test_bait_broken_anchor(spec):
    secs = [("s-1-1", "One"), ("s-1-2", "Two")]
    extra = '<p><a href="#s-9-4">nowhere</a></p>'
    text = page(chapter("ru", 1, "Глава", secs, CODE_RU, extra=extra),
                chapter("en", 1, "Chapter", secs, CODE_EN, extra=extra))
    report = check(text, spec)
    assert any("missing anchor `#s-9-4`" in line for line in report), report


def test_bait_todo_marker(spec):
    secs = [("s-1-1", "One"), ("s-1-2", "Two")]
    extra = "<p>TODO-BOOK write this</p>"
    text = page(chapter("ru", 1, "Глава", secs, CODE_RU, extra=extra),
                chapter("en", 1, "Chapter", secs, CODE_EN, extra=extra))
    report = check(text, spec)
    assert any("TODO-BOOK" in line for line in report), report


def test_only_mode_accepts_links_to_promised_chapters(spec):
    secs = [("s-1-1", "One"), ("s-1-2", "Two")]
    extra = '<p><a href="#ch-19">later</a> <a href="#s-19-1">and its section</a></p>'
    text = page(chapter("ru", 1, "Глава", secs, CODE_RU, extra=extra),
                chapter("en", 1, "Chapter", secs, CODE_EN, extra=extra))
    from number_figures import number
    assert check(number(text), spec, private=True, only="ch-1") == []


def test_bait_only_mode_still_rejects_unpromised_anchor(spec):
    secs = [("s-1-1", "One"), ("s-1-2", "Two")]
    extra = '<p><a href="#ch-77">nowhere</a></p>'
    text = page(chapter("ru", 1, "Глава", secs, CODE_RU, extra=extra),
                chapter("en", 1, "Chapter", secs, CODE_EN, extra=extra))
    from number_figures import number
    report = check(number(text), spec, private=True, only="ch-1")
    assert any("missing anchor `#ch-77`" in line for line in report), report


def test_bait_only_mode_detects_locale_difference(spec):
    secs = [("s-1-1", "One"), ("s-1-2", "Two")]
    from number_figures import number
    text = page(chapter("ru", 1, "Глава", secs, CODE_RU),
                chapter("en", 1, "Chapter", secs, CODE_EN.replace("weeks = 12", "weeks = 13")))
    report = check(number(text), spec, private=True, only="ch-1")
    assert any("code differs" in line for line in report), report


def test_fstring_placeholder_order_is_a_string_difference():
    from check_isomorphism import code_shape
    ru = 'x = 1\nmsg = f"первая {x} ошибка в {x + 1}"\n'
    en = 'x = 1\nmsg = f"{x + 1}: first {x} error"\n'
    assert code_shape(ru) == code_shape(en)


def test_bait_fstring_expression_outside_string_still_differs():
    from check_isomorphism import code_shape
    ru = 'x = 1\nmsg = f"{x}" + str(x)\n'
    en = 'x = 1\nmsg = f"{x}" + repr(x)\n'
    assert code_shape(ru) != code_shape(en)
