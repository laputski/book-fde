from __future__ import annotations

from check_reference import check, defined_names

STUBS = "class LLMClient:\n    pass\n\ndef embed(text: str) -> list[float]:\n    return []\n"


def page(ru_names: str, en_names: str, listing: str = "class Runner:\n    pass") -> str:
    def block(loc: str, names: str) -> str:
        return (f'<div class="locale" data-locale="{loc}">'
                '<section class="chapter" id="ch-7"><figure class="code" data-fold="0">'
                f'<figcaption><span class="file">two_frameworks.py</span></figcaption><pre><code>{listing}</code></pre></figure></section>'
                '<section class="chapter" id="app-b"><table><tbody>'
                f'<tr><td>ADK</td><td>framework</td><td>{names}</td><td>7</td></tr>'
                '</tbody></table></section></div>')
    return block("ru", ru_names) + block("en", en_names)


def test_names_defined_by_listing_or_stub_pass():
    names = "<code>Runner</code>, <code>LLMClient</code>, <code>embed</code>"
    assert check(page(names, names), STUBS) == []


def test_plain_text_cell_promises_nothing():
    assert check(page("нет", "none"), STUBS) == []


def test_escaped_listing_is_parsed():
    listing = "class Graph:\n    edges: dict[str, str] = {}\n\nLIMIT = 3 &lt; 4"
    assert check(page("<code>Graph</code>, <code>LIMIT</code>", "<code>Graph</code>, <code>LIMIT</code>", listing), STUBS) == []


def test_bait_name_that_no_listing_defines():
    report = check(page("<code>AgentRuntime</code>", "<code>AgentRuntime</code>"), STUBS)
    assert len(report) == 2 and all("AgentRuntime" in line for line in report)


def test_bait_locales_promise_different_names():
    report = check(page("<code>Runner</code>", "<code>LLMClient</code>"), STUBS)
    assert report == [
        "- the locales promise different names: ru ['Runner'], en ['LLMClient']",
    ]


def test_defined_names_ignore_nested_definitions():
    source = "class Outer:\n    class Inner:\n        pass\n\ndef f():\n    def g():\n        pass\n"
    assert defined_names(source) == {"Outer", "f"}
