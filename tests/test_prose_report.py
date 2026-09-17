from __future__ import annotations

from prose_report import candidates, sentences


def categories(source: str) -> set[str]:
    return {name for name, _ in candidates(source)}


def test_user_example_contrast_and_set_up_are_found():
    source = ("<p>Инженер, добавляющий в систему платёжный шлюз, не спрашивает, можно ли на него положиться. "
              "Он спрашивает другое: какова схема запроса. Пять вопросов образуют контракт, и этот контракт, "
              "а не репутация поставщика, определяет встраивание.</p>")
    assert {"contrast", "set-up"} <= categories(source)


def test_user_example_evaluative_framing_is_found():
    assert categories("<p>Задача звучит просто: превратить PDF в запись SAP.</p>") == {"evaluative"}


def test_edited_versions_are_clean():
    source = ("<p>Типичные вопросы инженера, добавляющего в систему платёжный шлюз или геокодер: какова схема "
              "запроса и ответа. Данные вопросы образуют контракт, который определяет, как зависимость "
              "встраивается в систему. Задача заключается в том, чтобы превратить PDF в запись SAP.</p>")
    assert candidates(source) == []


def test_metaphorical_verbs_and_english_patterns_are_found():
    assert "metaphor" in categories("<p>p95 живёт в ремонте и отсрочках.</p>")
    assert {"contrast", "metaphor"} <= categories("<p>The tail lives in the retries, not in the model.</p>")
    assert "evaluative" in categories("<p>The task sounds simple.</p>")


def test_capacity_and_code_are_not_reported():
    source = ("<p>Мощность кластера и ключ идемпотентности описаны в разделе 14.3.</p>"
              "<pre><code># не X, а Y — комментарий в коде</code></pre>")
    assert candidates(source) == []


def test_diagram_step_captions_are_read():
    source = '<g data-step="1" data-caption="Батч идёт туда, где кривая проседает, а не в пик."></g>'
    assert any("Батч" in s for s in sentences(source))
    assert "contrast" in categories(source)
