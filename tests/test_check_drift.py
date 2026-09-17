from __future__ import annotations

import json

from check_drift import MAX_PAGE_BYTES, job_status

TITLE = "Staff Forward Deployed Engineer"
SHELL = "<script>" + "x" * 1_100_000 + "</script>"      # the careers page is a large application bundle


def test_published_post_passes():
    assert job_status(f"<html>{SHELL}<h2>{TITLE}</h2>Minimum qualifications</html>", TITLE) is None


def test_bait_withdrawal_marker_after_the_first_megabyte():
    # The defect observed on 2026-09-17: the marker sat at about 1.1 MB and a
    # reader limited to 400 KB never saw it.
    page = f"<html>{SHELL}<p>Job not found. This job may have been taken down.</p></html>"
    assert page.index("Job not found") > 1_000_000
    assert job_status(page, TITLE) == 'the page says "Job not found"'


def test_bait_page_without_the_expected_title():
    page = f"<html>{SHELL}<h2>Search jobs</h2></html>"
    assert job_status(page, TITLE) == f'the page no longer shows the title "{TITLE}"'


def test_read_limit_covers_the_observed_page_size():
    observed_page_bytes = 1_286_648                     # the Warsaw post, fetched on 2026-09-17
    assert MAX_PAGE_BYTES > 4 * observed_page_bytes


def test_every_job_source_names_its_expected_title():
    from conftest import ROOT
    anchors = json.loads((ROOT / "data" / "anchors.json").read_text(encoding="utf-8"))
    jobs = [s for s in anchors["sources"] if s.get("kind") == "job"]
    assert jobs and all(s.get("expect") for s in jobs)
