<div align="center">

<img src="assets/logo.svg" width="140" alt="Forward Deployed Engineering">

# Forward Deployed Engineering

**A bilingual, single-file browser textbook on taking agentic AI systems
from prototype to production inside a customer's organisation: discovery,
integration, agents, evaluation, observability, security, operations, and
turning field patterns into product.**

[![ci](https://github.com/laputski/book-fde/actions/workflows/ci.yml/badge.svg)](https://github.com/laputski/book-fde/actions/workflows/ci.yml)
[![deploy](https://github.com/laputski/book-fde/actions/workflows/deploy.yml/badge.svg)](https://github.com/laputski/book-fde/actions/workflows/deploy.yml)
[![weekly](https://github.com/laputski/book-fde/actions/workflows/weekly.yml/badge.svg)](https://github.com/laputski/book-fde/actions/workflows/weekly.yml)
[![site](https://img.shields.io/badge/read-fde.ragworld.org-0072B2)](https://fde.ragworld.org)
[![python](https://img.shields.io/badge/python-3.13%20%7C%203.14-3776AB?logo=python&logoColor=white)](https://fde.ragworld.org)
[![languages](https://img.shields.io/badge/languages-EN%20%7C%20RU-555)](https://fde.ragworld.org)
[![text](https://img.shields.io/badge/text%20%26%20diagrams-CC%20BY%204.0-97CA00)](LICENSE-CONTENT)
[![code](https://img.shields.io/badge/code-MIT-blue)](LICENSE)

**[Read it at fde.ragworld.org →](https://fde.ragworld.org)**

*Читайте документацию репозитория по-русски: [README.ru.md](README.ru.md)*

</div>

---

An introduction, eighteen chapters and seven appendices with 51 hand-drawn
SVG diagrams and 102 code listings per language, all in one self-contained
HTML file; every listing is checked by ruff and mypy and executed. A
language switch (EN/RU), three reading-depth levels, full-text search, term
popovers, step-by-step diagrams, print-to-PDF, day/night themes. Six
fictional customers run through the chapters, and the book is calibrated
against two Google Cloud job posts read in September 2026, Staff Forward
Deployed Engineer (GenAI) and Forward Deployed Engineering Manager
(Generative AI); Appendix A maps every requirement to the sections that
cover it.

The book is part of the [ragworld.org](https://ragworld.org) series,
alongside the [RAG World registry](https://ragworld.org), the textbook
[Advanced Python for RAG](https://github.com/laputski/book-python), and
[causa-rag](https://github.com/laputski/causa-rag), a diagnostic bench
for RAG.

## Repository layout

| Path | Purpose |
| --- | --- |
| `fde-advanced.html` | the assembled book; a build artifact, committed |
| `parts/` | sources: shell (`00-head`, `99-tail`), one file per chapter under `ru/` and `en/` |
| `build.sh` | assembles the book, numbers the diagrams, stamps the sources check date |
| `check_all.sh` | every check in order: build, isomorphism, diagrams, boundary, listings, tests, drift |
| `examples/` | listings of both locales extracted from the book, plus typed stubs and the run manifest |
| `check_examples.sh` | listing verification: parse, ruff, mypy, execution |
| `data/spec.json` | the source of truth for chapters, sections, listings and diagram counts |
| `data/anchors.json` | the external sources the prose relies on, with the dates they were read |
| `tools/check_isomorphism.py` | both locales share one structure and match the spec |
| `tools/dia_lint.py` | the diagram rules: colours, strokes, captions, numbering, shared geometry |
| `tools/check_private.py` | nothing from the local-only part leaks into the public build |
| `tools/style_lint.py` | house style: no em dashes outside code listings |
| `tools/check_reference.py` | every name that Appendix B attributes to the listings is defined by a listing |
| `tools/check_contrast.py` | diagram labels reach 4.5:1 and diagram lines 3:1 against every ground of every theme, including print |
| `tools/spec_loader.py` | loads `data/spec.json` and, when present, merges the local-only `private/spec.private.json` over its private stubs |
| `tools/check_fictional_data.py` | phone numbers and e-mail addresses in examples come only from ranges reserved for fiction |
| `tools/with_lock.sh` | serialises concurrent runs of `check_examples.sh`, which would otherwise overwrite each other's extracted files |
| `tools/prose_report.py` | editorial aid: lists sentences with contrast constructions, rhetorical set-ups, evaluative framing or metaphorical verbs for review |
| `tools/check_drift.py` | staleness detector: source age, job posts still published, links |
| `tests/` | unit tests of the tools; every guard has a bait that must trip it |

## Working locally

```sh
./build.sh            # reassemble the book after editing parts/
./check_all.sh        # run every check
python3 tools/check_drift.py   # sync check: sources, job posts, links
```

Preview: `python3 -m http.server 8732`, then open
`http://localhost:8732/fde-advanced.html`.

Authoring conventions: chapter files are HTML fragments; both locales
must be element-for-element isomorphic (same ids, same listings, same
diagram geometry with translated labels); listings are self-contained
Python that runs to completion; diagrams use only `currentColor` and the
seven layer variables; annotations under a listing refer to lines through
`data-anchor` and are renumbered by `tools/gloss_lines.py`.

## Deployment

GitHub Pages, deployed by `.github/workflows/deploy.yml` on every push to
`main`. The site answers at `laputski.github.io/book-fde`. The
`fde.ragworld.org` domain needs a CNAME record `fde → laputski.github.io`
on the DNS side and the same name in Settings → Pages → Custom domain (the
workflow token cannot change Pages settings). Enforce HTTPS there once the
certificate is issued.

## Self-updating

The rule: **data updates automatically, prose changes only through review.**

- `ci.yml` checks on every push that the build is reproducible, both locales are
  isomorphic, the diagrams obey the rules, and the listings of both
  locales pass parsing, ruff, mypy and execution on Python 3.13, 3.14, and
  the 3.15 prerelease.
- `weekly.yml` verifies on Mondays or on demand that every source in
  `data/anchors.json` still answers, stamps the check date into Appendix E
  by auto-commit, and runs the staleness detector, which opens a
  `drift`-labelled issue when a source is older than the review limit, a
  job post is taken down, or a link dies; a human lands the prose fix
  through a PR.
- Scheduled workflows on public repositories go dormant after 60 days
  without commits; the workflow leaves a sync mark if the quiet stretch
  exceeds 45 days.

## Licensing

The code of the repository (build and check scripts, tools, the page
script, the extracted listings) is under the MIT licence, see `LICENSE`.
The text and the diagrams of the book are under CC BY 4.0, see
`LICENSE-CONTENT`.

*Comments inside the Russian-locale listings are Russian by design: they
are part of the book's Russian text. The English locale carries the same
listings with English comments, and the build verifies that the code is
otherwise identical.*
