from __future__ import annotations

from style_lint import ROOT, default_files, violations


def test_clean_text_passes():
    assert violations("<p>Агент является циклом с бюджетом.</p>") == []


def test_dash_inside_code_is_exempt():
    assert violations("<pre><code>x = 1  # один — один</code></pre>") == []


def test_bait_dash_in_prose():
    found = violations("<p>Агент — цикл с бюджетом.</p>")
    assert len(found) == 1 and found[0][0] == 1


def test_bait_dash_in_heading_and_svg_label_after_code():
    text = ('<pre><code>a = 1\nb = 2</code></pre>\n'
            '<h3 id="s-1-2">Почему агент — цикл</h3>\n'
            '<svg><text>10× — вот что</text></svg>')
    lines = [line for line, _ in violations(text)]
    assert lines == [3, 4]


def test_markdown_fence_is_exempt():
    text = "Prose without dashes.\n```sh\npython3 tools/style_lint.py  # a — b\n```\n"
    assert violations(text) == []


def test_bait_dash_in_markdown_prose_after_fence():
    text = "```sh\n./build.sh\n```\n- `ci.yml` — on every push\n"
    assert [line for line, _ in violations(text)] == [4]


def test_default_scope_includes_repository_documents():
    names = {f.name for f in default_files()}
    assert {"README.md", "README.ru.md", "CONTRIBUTING.md"} <= names
    assert any(f.parent.parent == ROOT / "parts" for f in default_files())


def test_generated_diagram_caption_passes():
    assert violations("<figcaption><b>Диаграмма {{DIA}}.</b> Вывод.</figcaption>") == []


def test_bait_hand_written_diagram_number_in_both_locales():
    text = "<p>Дерево решений диаграммы 3 выбирает хранилище.</p>\n<p>See Diagram 15 for the tree.</p>"
    assert [line for line, _ in violations(text)] == [1, 2]


def test_british_spelling_and_exempt_places_pass():
    text = ('<p>The organisation keeps behaviour, artefacts and per cent.</p>\n'
            '<pre><code>canceled = "TASK_STATE_CANCELED"  # color</code></pre>\n'
            '<p>The World Health Organization and the AWS organization.'
            '<a class="src" href="https://example.org/color">Color Universal Design</a></p>\n'
            '<figure class="code"><figcaption><span class="file">conversation_to_artifact.py</span></figcaption></figure>')
    assert violations(text, english=True) == []


def test_bait_american_spelling_in_english_prose():
    text = "<p>British text.</p>\n<p>The organization logs every artifact and about three percent fail.</p>"
    assert [line for line, _ in violations(text, english=True)] == [2, 2, 2]


def test_russian_files_are_not_checked_for_english_spelling():
    assert violations("<p>artifact</p>", english=False) == []
