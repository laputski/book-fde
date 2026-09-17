"""Shared fixtures: a minimal two-locale book and its specification.

The fixtures build the smallest page that satisfies every convention, so
each test mutates one thing and expects exactly one guard to fire. A guard
that does not fire on its bait is a broken guard.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

SVG = (
    '<svg viewBox="0 0 880 200" role="img" aria-label="{label}" xmlns="http://www.w3.org/2000/svg">'
    '<defs><marker id="{marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
    'orient="auto-start-reverse"><path d="M0,1 L9,5 L0,9 z" fill="currentColor"/></marker></defs>'
    '<g data-step="1"><rect x="10" y="10" width="100" height="40" rx="5" fill="none" stroke="var(--sA)" stroke-width="1.8"/>'
    '<text x="60" y="35" font-family="Inter,sans-serif" font-size="12" fill="currentColor">{t1}</text></g>'
    '<g data-step="2"><line x1="110" y1="30" x2="200" y2="30" stroke="currentColor" stroke-width="1.4" marker-end="url(#{marker})"/>'
    '<text x="150" y="20" font-size="11" fill="var(--muted)">{t2}</text></g>'
    '</svg>'
)


def chapter(loc: str, num: int, title: str, sections: list[tuple[str, str]], code: str,
            file: str = "engagement.py", layers: str = "FG", run: str = "", caption_word: str = "",
            extra: str = "") -> str:
    strata = "".join(f'<i data-s="{c}"></i>' if c in layers else "<i></i>" for c in "ABCDEFG")
    caption_word = caption_word or ("Диаграмма" if loc == "ru" else "Diagram")
    label = ("Схема из двух шагов, показывающая один прямоугольник и одну стрелку для проверки правил"
             if loc == "ru" else "A two-step scheme showing one rectangle and one arrow used to exercise the rules")
    h3 = "".join(f'<h3 id="{sid}"><span class="num">{num}.{i}</span>{t}</h3><p>Text {i}.</p>'
                 for i, (sid, t) in enumerate(sections, 1))
    return f'''
<section class="chapter" id="ch-{num}">
<div class="chead"><div class="row"><p class="eyebrow">Глава</p>
<span class="strata" role="img" aria-label="layers">{strata}</span></div>
<h2 id="s-{num}"><span class="num">{num}</span>{title}</h2></div>
<div class="goals"><p class="eyebrow">Goals</p><ul><li>one</li></ul></div>
{h3}
<figure class="dia" data-steps><div class="svg-wrap">{SVG.format(label=label, marker=f"ar{num}", t1="узел" if loc == "ru" else "node", t2="ребро" if loc == "ru" else "edge")}</div>
<figcaption><b>{caption_word} {{{{DIA}}}}.</b> Caption text.</figcaption></figure>
<figure class="code" data-fold="0"{run}><figcaption><span class="file">{file}</span></figcaption>
<pre><code>{code}</code></pre></figure>
{extra}
<dl class="def"><dt>Термин <span class="en">(term)</span></dt><dd>Definition.</dd></dl>
<div class="warn"><b>Warning</b>Text.</div>
<div class="quiz" data-level="2"><p class="eyebrow">Q</p>
<details><summary>q1</summary><div class="ans"><p>a</p></div></details>
<details><summary>q2</summary><div class="ans"><p>a</p></div></details>
<details><summary>q3</summary><div class="ans"><p>a</p></div></details></div>
<div class="recap"><p class="eyebrow">Recap</p><ul><li>r</li></ul></div>
</section>'''


def page(ru_body: str, en_body: str) -> str:
    return ('<meta charset="utf-8"><main id="main">\n<div class="locale" data-locale="ru">\n'
            + ru_body + '\n</div>\n<div class="locale" data-locale="en">\n' + en_body + '\n</div>\n</main>')


CODE_RU = ('class Engagement:\n    """Модель engagement."""\n    weeks = 12  # недель\n\n'
           'if __name__ == "__main__":\n    assert Engagement.weeks == 12\n    print("ок")')
CODE_EN = ('class Engagement:\n    """The engagement model."""\n    weeks = 12  # weeks\n\n'
           'if __name__ == "__main__":\n    assert Engagement.weeks == 12\n    print("ok")')


@pytest.fixture
def spec() -> dict:
    return {
        "chapters": [
            {"num": 1, "id": "ch-1", "layers": ["F", "G"], "diagrams": 1, "listings": ["engagement"],
             "sections": [{"id": "s-1-1"}, {"id": "s-1-2"}]},
            {"num": 19, "id": "ch-19", "private": True, "layers": ["F"], "diagrams": 1, "listings": ["prep"],
             "sections": [{"id": "s-19-1"}]},
        ],
        "appendices": [{"letter": "Q", "id": "app-q", "private": True}],
        "parts": [],
    }


@pytest.fixture
def good_page() -> str:
    secs = [("s-1-1", "One"), ("s-1-2", "Two")]
    return page(chapter("ru", 1, "Глава", secs, CODE_RU), chapter("en", 1, "Chapter", secs, CODE_EN))


@pytest.fixture
def numbered(good_page: str) -> str:
    from number_figures import number
    return number(good_page)
