# Authoring a chapter

This file is the contract every chapter of the book satisfies. The tools
enforce most of it; the rest is judgement, and the exemplar chapter
(`parts/ru/23-ch-06.html` and `parts/en/23-ch-06.html`) shows every
element in use.

## Sources of truth

- `data/spec.json` fixes, for every chapter: its id and file name, the
  layers it touches, the case file it works with, whether it has an
  "On Google Cloud" section, the number of diagrams, the ordered list of
  listing file names, and the ids and titles of its sections. The chapter
  must match the spec; if the chapter needs a different section list or
  listing name, change the spec in the same change.
- The chapters of the local-only part appear in `data/spec.json` as stubs
  (number, id, file) so that the published repository does not reveal their
  outline; their full entries live in `private/spec.private.json`, which
  `tools/spec_loader.py` merges when it exists. `tools/check_private.py`
  fails if a private stub publishes a title, sections or listings.
- Both locales are written in one sitting and are isomorphic
  element-for-element. `tools/check_isomorphism.py fde-advanced.html --only=ch-N`
  verifies one chapter while its neighbours are still missing.

## The rhythm of a chapter

```
<section class="chapter" id="ch-N">
  .chead  (eyebrow, .strata with the chapter's layers, h2#s-N with <span class="num">N</span>)
  .goals  (4–5 outcomes)
  h3#s-N-1  The task: … (+ .rec badge linking the case file in Appendix G)
  h3#s-N-2  Why …          (+ dl.def definitions)
  figure.dia               (the mechanism of the chapter)
  h3 … sections            (.tabs Naive / Considered / The difference around the central listing)
  .warn                    (common mistakes; the index of mistakes is built from them)
  h3#s-N-k data-level="2"  On Google Cloud: …   (+ .rec badge to Appendix B; .aside comparison)
  h3#s-N-last data-level="3"  In depth: …   (h4 sub-sections, all data-level="3")
  .quiz data-level="2"     (exactly 3 <details>)
  .recap                   (takeaways + .seealso links)
</section>
```

Levels: level 1 must read as a complete book on its own; nothing visible
at level 1 may open with a reference to a hidden passage. Naive tabs,
`.gloss`, `.note`, the Google Cloud section and the quiz are level 2.
"In depth" is level 3 entirely (the `h3`, its `h4`s, paragraphs, figures).

## Listings

- Python 3.13, self-contained, stdlib + pydantic only, no network, no
  filesystem writes, deterministic. Every listing ends with an
  `if __name__ == "__main__":` block that asserts what the text claims and
  prints one line. Vendor SDKs are never imported: use `typing.Protocol`
  and a `Fake…` implementation inside the listing, or names from
  `examples/stubs.py` (they are injected automatically when undefined).
- Markup: `<figure class="code" data-fold="N"><figcaption><span class="file">stem.py</span></figcaption><pre><code>…</code></pre></figure>`.
  Escape `<`, `>` and `&` inside `<code>`. `data-fold="0"` under 14 lines,
  otherwise the number of lines to show folded (16–26).
- A listing that must not be executed (a deliberate infinite loop, a
  deliberate crash) carries `data-run="no"` on the figure.
- The code of a listing is identical in both locales except comments,
  docstrings and string literals; `check_isomorphism` compares the token
  shape.
- Annotations: `<div class="gloss" data-level="2">` with rows
  `<div><span class="at" data-anchor="unique fragment">строка ?</span><p>…</p></div>`
  (`line ?` in English). Run `python3 tools/gloss_lines.py parts/ru/NN-ch-NN.html parts/en/NN-ch-NN.html`
  to fill the numbers; the anchor must occur on exactly one line.
- The listing names in the spec are the `.file` stems in order; the first
  is the naive one inside the "Naive" tab.

## Diagrams

- Inline SVG only: `<figure class="dia"><div class="svg-wrap"><svg viewBox="0 0 880 H" role="img" aria-label="one full sentence" xmlns="…">`.
  H between 230 and 420. No `width`/`height` attributes.
- Colour only through `currentColor`, `var(--sA…--sG)` (the seven layers,
  see chapter 0), `var(--muted)`, `var(--line)`, `var(--line-strong)`.
  No hex, no rgb(). A saturated colour means its layer and nothing else.
- Strokes: 1.3–1.4 connectors, 1.5–1.6 boxes, 1.8 boxes that carry a
  layer colour; never above 2. `rx="4"`/`"5"` boxes, `rx="8"` frames,
  `rx="20"` pills. Orthogonal `H`/`V` paths, no curves. Dashed `5 4`
  means optional/feedback, `6 5` means an enclosing region. Solid fills
  only for small quantity marks at `opacity="0.85"`.
- One `<marker>` per diagram with a unique id (`ar6a`, `ar6b`, …):
  `viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"`,
  path `M0,1 L9,5 L0,9 z`.
- Labels: Inter 11–13px (600 for node titles); a secondary JetBrains Mono
  10.5–11px `var(--muted)` line for "where it is covered".
- Caption: `<figcaption><b>Диаграмма {{DIA}}.</b> …` / `<b>Diagram {{DIA}}.</b> …`.
  The build numbers them. The sentence states the takeaway, not what is drawn.
- Stepped diagrams: `figure.dia[data-steps]` with `<g data-step="1" data-caption="…">`
  groups numbered 1..n. Everything outside the groups stays visible.
- The SVG of the two locales must be identical once `<text>` elements and
  `data-caption` attributes are removed: draw once, translate the labels.
  Size boxes so that both languages fit.

## Prose

- No em dashes outside code listings, including headings, table cells and
  diagram labels: `tools/style_lint.py` fails on them. Use a verb instead.
- Scientific register, precise terms, definitions for every term the
  chapter introduces (`dl.def`; in Russian the `dt` ends with
  `<span class="en">(original term)</span>`). No em-dashes as connectors;
  use verbs. Paragraphs of three to five sentences.
- Internal links carry `data-secref`: `<a href="#s-9-4" data-secref="9.4">`.
  Only ids that `data/spec.json` promises.

### Direct statements

Every sentence states a claim, a mechanism, a number or an example. The
following devices make a text read as machine-generated filler and are not
used; `python3 tools/prose_report.py --list <files>` lists candidate
sentences for review (it reports, it does not decide).

1. **Contrast constructions** ("не X, а Y", "X, а не Y", "не просто",
   "not X but Y", "X, not Y", "rather than") only when the choice between X
   and Y is itself the content: Y is an alternative a competent reader would
   otherwise take, and the text says why it is rejected. Test: delete the
   negated part; if the reader loses nothing needed, keep it deleted. When
   the rejected alternative matters, give it its own sentence with the
   reason.
2. **Rhetorical set-ups**: a denial followed by a reveal ("Он не спрашивает
   A. Он спрашивает другое: B"), a question answered at once, "Ответ
   прост:", "Вот почему", "Here is why", "The catch is". State B directly.
3. **Evaluative or emotional framing**: "звучит просто", "на первый взгляд",
   "коварный", "настоящий", "ключевой", "критически важный", "sounds
   simple", "deceptively", "the real", "crucial". Give the property and its
   measure instead.
4. **Metaphorical verbs** where a literal verb exists: "живёт в",
   "принадлежит", "лечится", "едет с", "lives in", "belongs to", "is cured
   by". Write "определяется", "устраняется", "передаётся". Established terms
   (noisy neighbour, cold start) stay.
5. **Slogans**: diagram captions, recap items and the last sentence of a
   paragraph state a conclusion with its condition and mechanism, not a
   maxim. Intensifiers ("ровно", "всегда", "единственный", "именно") only
   when literally true.

Examples from the book (before → after):

- «Инженер, добавляющий в систему платёжный шлюз или геокодер, не спрашивает,
  можно ли на них положиться. Он спрашивает другое: какова схема запроса и
  ответа, … и сколько стоит вызов. Пять вопросов образуют контракт, и этот
  контракт, а не репутация поставщика, определяет, как зависимость
  встраивается в систему.» → «Типичные вопросы инженера, добавляющего в
  систему платёжный шлюз или геокодер: какова схема запроса и ответа, … и
  сколько стоит вызов. Данные вопросы образуют контракт, который определяет,
  как зависимость встраивается в систему.»
- «Задача звучит просто: превратить PDF в структурированную запись SAP.» →
  «Задача заключается в том, чтобы превращать PDF в структурированную запись
  SAP при трёх ограничениях.»
- «Медиана задержки принадлежит модели, а хвост распределения принадлежит
  повторам: p95 живёт в ремонте и отсрочках, поэтому укладывание в восемь
  секунд достигается сокращением доли повторов, а не выбором более быстрой
  модели.» → «Медиана задержки определяется временем работы модели, а 95-й
  процентиль определяется повторами: ремонтом ответа и отсрочками после
  отказов. Поэтому требование в восемь секунд выполняется прежде всего
  сокращением доли повторов: более быстрая модель уменьшает длительность
  каждой попытки, но не число попыток.» (The rejected alternative is kept
  because it is the decision a reader would otherwise make, and the reason
  is given.)
- "Cost is counted in input and output tokens, not in requests." → "Cost is
  calculated from the number of input and output tokens."
- Fictional customers only (Appendix G). Sources as `<a class="src">`
  with a target="_blank" rel="noreferrer".
- Nothing from the local-only part in public files; the public/private
  checker fails on any id or link of a private stub in `data/spec.json`.
- Personal data in examples is fictional by construction: phone numbers from
  +44 7700 900000–900999, e-mail addresses in `.example`, `.test`, `.invalid`
  or `example.com/.net/.org`; `tools/check_fictional_data.py` fails otherwise.
- Never leave `TODO-BOOK` markers in a finished chapter.

## Checking a chapter

```sh
./build.sh
python3 tools/check_isomorphism.py fde-advanced.html --only=ch-N
python3 tools/dia_lint.py fde-advanced.html
python3 tools/check_private.py fde-advanced.html
python3 tools/style_lint.py parts/ru/NN-ch-NN.html parts/en/NN-ch-NN.html
python3 tools/check_reference.py fde-advanced.html
python3 tools/check_contrast.py
python3 tools/check_fictional_data.py parts/ru/NN-ch-NN.html parts/en/NN-ch-NN.html
./check_examples.sh
```

The build must stay reproducible: no timestamps, no randomness in the
sources. Look at the chapter in the browser in both themes and both
locales before calling it done (`python3 -m http.server 8732`).
