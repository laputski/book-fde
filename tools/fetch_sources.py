#!/usr/bin/env python3
"""Verify that the book's sources are reachable and stamp the check date.

Reads data/anchors.json, sends a HEAD (falling back to GET) to every source,
and writes data/sources_meta.json with today's date when every source
answered. Exit codes: 0 — nothing changed; 3 — the date advanced (the signal
for the weekly auto-commit); 2 — at least one source did not answer, the
date is left untouched and the staleness detector will report it.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import ssl
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
META = ROOT / "data" / "sources_meta.json"


def tls_context() -> ssl.SSLContext:
    """The system trust store, falling back to certifi when it is empty."""
    context = ssl.create_default_context()
    if context.cert_store_stats()["x509_ca"] == 0:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    return context


def reachable(url: str, context: ssl.SSLContext) -> bool:
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, method=method, headers={"User-Agent": "book-fde-linkcheck"})
        try:
            with urllib.request.urlopen(request, timeout=25, context=context) as resp:
                return resp.status < 400
        except urllib.error.HTTPError as err:
            if err.code in (403, 405):
                return True          # alive, but refusing robots or HEAD
            if method == "GET":
                return False
        except Exception:
            if method == "GET":
                return False
    return False


def main() -> int:
    anchors = json.loads((ROOT / "data" / "anchors.json").read_text(encoding="utf-8"))
    context = tls_context()
    total = len(anchors["sources"])
    alive = sum(1 for s in anchors["sources"] if reachable(s["url"], context))
    previous = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
    today = datetime.date.today().isoformat()
    if alive < total:
        print(f"sources: {alive}/{total} reachable; the check date stays {previous.get('checked_at')}")
        return 2
    meta = {"checked_at": today, "reachable": alive, "total": total}
    changed = meta != previous
    META.write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    print(f"sources: {alive}/{total} reachable, checked {today}, {'changed' if changed else 'unchanged'}")
    return 3 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
