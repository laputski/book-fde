#!/usr/bin/env python3
"""The book's staleness detector.

Checks three things and prints a markdown report:
  1. Age: a source in data/anchors.json checked more than review_after_days
     ago asks for a review of the chapters that rely on it.
  2. Publication: a job post that answers "Job not found", no longer shows
     its expected title, or does not answer means the requirements the book
     is calibrated against changed. The careers page is a large client-side
     application (over a megabyte), so the whole page is read.
  3. Links: every external link of the assembled book answers.

Exit codes: 0 — no drift; 4 — drift found, report on stdout.
The script never edits the book's text: prose changes are a human's call.
"""
from __future__ import annotations

import datetime
import html.parser
import json
import pathlib
import ssl
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent


def tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if context.cert_store_stats()["x509_ca"] == 0:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    return context


def check_age(report: list[str], today: datetime.date | None = None) -> None:
    anchors = json.loads((ROOT / "data" / "anchors.json").read_text(encoding="utf-8"))
    limit = int(anchors.get("review_after_days", 120))
    today = today or datetime.date.today()
    for src in anchors["sources"]:
        checked = datetime.date.fromisoformat(src["checked_at"])
        age = (today - checked).days
        if age > limit:
            chapters = ", ".join(src.get("chapters", []))
            report.append(
                f"- **{src['id']}** was last reviewed {age} days ago (limit {limit}): "
                f"re-read {src['url']} and revisit chapters {chapters}")


MAX_PAGE_BYTES = 8_000_000
WITHDRAWN_MARKERS = ("Job not found", "may have been taken down")


def job_status(page: str, expect: str | None) -> str | None:
    """Why a fetched job post no longer counts as published, or None if it does."""
    marker = next((m for m in WITHDRAWN_MARKERS if m in page), None)
    if marker:
        return f'the page says "{marker}"'
    if expect and expect not in page:
        return f'the page no longer shows the title "{expect}"'
    return None


def check_jobs(report: list[str]) -> None:
    anchors = json.loads((ROOT / "data" / "anchors.json").read_text(encoding="utf-8"))
    context = tls_context()
    for src in anchors["sources"]:
        if src.get("kind") != "job":
            continue
        request = urllib.request.Request(src["url"], headers={"User-Agent": "book-fde-linkcheck"})
        try:
            with urllib.request.urlopen(request, timeout=25, context=context) as resp:
                page = resp.read(MAX_PAGE_BYTES).decode("utf-8", "replace")
        except Exception as err:
            report.append(f"- job post **{src['id']}** unreachable ({err.__class__.__name__}): {src['url']}")
            continue
        reason = job_status(page, src.get("expect"))
        if reason:
            report.append(
                f"- job post **{src['id']}** is no longer published ({reason}): the requirements in "
                f"Appendix A need a fresh source ({src['url']})")


class LinkCollector(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value and value.startswith("https://"):
                self.urls.add(value)


def check_links(report: list[str]) -> None:
    page = (ROOT / "fde-advanced.html").read_text(encoding="utf-8")
    collector = LinkCollector()
    collector.feed(page)
    context = tls_context()
    for url in sorted(collector.urls):
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "book-fde-linkcheck"})
        try:
            with urllib.request.urlopen(request, timeout=20, context=context) as resp:
                if resp.status >= 400:
                    report.append(f"- link answers {resp.status}: {url}")
        except urllib.error.HTTPError as err:
            if err.code in (403, 405):     # alive, but refusing robots or HEAD
                continue
            report.append(f"- link answers {err.code}: {url}")
        except Exception as err:
            report.append(f"- link unreachable ({err.__class__.__name__}): {url}")


def main() -> int:
    report: list[str] = []
    check_age(report)
    if "--no-links" not in sys.argv:
        check_jobs(report)
        check_links(report)
    if not report:
        print("no drift")
        return 0
    print("## Staleness detected\n")
    print("\n".join(report))
    print("\nThe book's text was not modified: each item above needs an edit.")
    return 4


if __name__ == "__main__":
    sys.exit(main())
