from __future__ import annotations

from check_contrast import ROOT, ratio, themes, violations

HEAD = (ROOT / "parts" / "00-head.html").read_text(encoding="utf-8")


def test_ratio_matches_known_pairs():
    assert round(ratio("#000000", "#FFFFFF"), 1) == 21.0
    assert round(ratio("#767676", "#FFFFFF"), 2) == 4.54      # the WebAIM reference grey for 4.5:1
    # the browser measured 2.20:1 for the raw orange diagram label on the page ground --bg #FCFCFD (2026-09-17)
    assert round(ratio("#E69F00", "#FCFCFD"), 2) == 2.20


def test_the_book_head_passes_in_every_theme():
    assert set(themes(HEAD)) == {"light", "dark (system)", "dark (toggle)", "print"}
    assert all(themes(HEAD).values())
    assert violations(HEAD) == []


def test_bait_raw_palette_colour_as_label_token():
    bad = HEAD.replace("--tE:#946700;", "--tE:#E69F00;", 1)
    assert bad != HEAD
    assert any("light: --tE #E69F00" in line for line in violations(bad))


def test_bait_rule_for_one_layer_removed():
    rule = 'figure.dia svg text[fill="var(--sF)"]{fill:var(--tF)}'
    assert rule in HEAD
    assert violations(HEAD.replace(rule, "")) == [
        '- rule missing: figure.diasvgtext[fill="var(--sF)"]{fill:var(--tF)}']


def test_bait_graphic_token_missing_in_toggle_dark_theme():
    dark = HEAD.index(':root[data-theme="dark"]{')
    cut = HEAD.index("--gC:#F07B2E;", dark)
    bad = HEAD[:cut] + HEAD[cut + len("--gC:#F07B2E;"):]
    assert "- dark (toggle): --gC is not defined" in violations(bad)
