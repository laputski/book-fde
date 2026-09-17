from __future__ import annotations

from conftest import CODE_EN, CODE_RU, chapter, page
from dia_lint import lint
from number_figures import number

SECS = [("s-1-1", "One"), ("s-1-2", "Two")]


def build(ru_kwargs=None, en_kwargs=None, numbered=True):
    text = page(chapter("ru", 1, "Глава", SECS, CODE_RU, **(ru_kwargs or {})),
                chapter("en", 1, "Chapter", SECS, CODE_EN, **(en_kwargs or {})))
    return number(text) if numbered else text


def test_good_diagram_passes():
    assert lint(build()) == []


def test_bait_hex_colour():
    text = build().replace('stroke="var(--sA)"', 'stroke="#0072B2"', 1)
    assert any("literal colour" in line for line in lint(text))


def test_url_reference_is_not_a_colour():
    # url(#ar1) contains a hash but is not a colour: it must pass.
    assert lint(build()) == []


def test_bait_missing_aria_label():
    text = build().replace(
        'aria-label="A two-step scheme showing one rectangle and one arrow used to exercise the rules"',
        'aria-label="short"', 1)
    assert any("aria-label too short" in line for line in lint(text))


def test_bait_unnumbered_placeholder():
    text = build(numbered=False)
    assert any("placeholder remains" in line for line in lint(text))


def test_bait_wrong_caption_word():
    text = build(en_kwargs={"caption_word": "Figure"})
    assert any("caption must open" in line for line in lint(text))


def test_bait_geometry_differs_between_locales():
    text = build().replace('width="100" height="40"', 'width="120" height="40"', 1)
    assert any("geometry differs" in line for line in lint(text))


def test_labels_may_differ_between_locales():
    # The fixture already uses different label texts in ru and en.
    assert lint(build()) == []


def test_bait_stroke_too_wide():
    text = build().replace('stroke-width="1.8"', 'stroke-width="2.5"')
    assert any("exceeds 2" in line for line in lint(text))


def test_bait_step_numbering_gap():
    text = build().replace('data-step="2"', 'data-step="3"')
    assert any("data-step values" in line for line in lint(text))
