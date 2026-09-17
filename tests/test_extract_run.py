from __future__ import annotations

import json
import pathlib
import shutil

from conftest import CODE_EN, CODE_RU, ROOT, chapter, page
from extract_examples import extract
from run_examples import run

SECS = [("s-1-1", "One"), ("s-1-2", "Two")]


def prepared(tmp_path: pathlib.Path, text: str) -> pathlib.Path:
    out = tmp_path / "examples"
    out.mkdir()
    shutil.copy(ROOT / "examples" / "stubs.py", out / "stubs.py")
    extract(text, out)
    return out


def test_listings_extracted_and_executed(tmp_path):
    text = page(chapter("ru", 1, "Глава", SECS, CODE_RU), chapter("en", 1, "Chapter", SECS, CODE_EN))
    out = prepared(tmp_path, text)
    names = sorted(p.name for p in out.glob("*.py") if p.name != "stubs.py")
    assert names == ["ch_1_01_engagement.py", "en_ch_1_01_engagement.py"]
    ran, skipped, failures = run(out)
    assert (ran, skipped, failures) == (2, 0, [])


def test_bait_failing_listing_fails_the_run(tmp_path):
    bad = CODE_EN.replace("assert Engagement.weeks == 12", "assert Engagement.weeks == 13")
    text = page(chapter("ru", 1, "Глава", SECS, CODE_RU), chapter("en", 1, "Chapter", SECS, bad))
    out = prepared(tmp_path, text)
    ran, skipped, failures = run(out)
    assert ran == 2 and len(failures) == 1 and "en_ch_1_01_engagement.py" in failures[0]


def test_data_run_no_is_skipped(tmp_path):
    looping = "while True:\n    pass"
    text = page(chapter("ru", 1, "Глава", SECS, looping, run=' data-run="no"'),
                chapter("en", 1, "Chapter", SECS, looping, run=' data-run="no"'))
    out = prepared(tmp_path, text)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest == {"ch_1_01_engagement.py": False, "en_ch_1_01_engagement.py": False}
    ran, skipped, failures = run(out)
    assert (ran, skipped, failures) == (0, 2, [])


def test_bait_timeout_is_a_failure(tmp_path, monkeypatch):
    import run_examples
    monkeypatch.setattr(run_examples, "TIMEOUT", 1)
    looping = "import time\ntime.sleep(5)"
    text = page(chapter("ru", 1, "Глава", SECS, looping), chapter("en", 1, "Chapter", SECS, looping))
    out = prepared(tmp_path, text)
    ran, skipped, failures = run_examples.run(out)
    assert ran == 2 and len(failures) == 2 and "timeout" in failures[0]
