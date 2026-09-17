"""The book's specification, split along the public/private boundary.

data/spec.json is published. For the private, local-only part it holds
stubs only: the number, id and file name of each private chapter, part and
appendix, without titles, sections or listings, so the public repository
does not reveal the outline of the local-only part. The full private
entries live in private/spec.private.json (ignored by git); when that file
exists, load() replaces every stub with its full entry.
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "data" / "spec.json"
PRIVATE = ROOT / "private" / "spec.private.json"
STUB_KEYS = frozenset({"num", "id", "file", "private", "letter", "chapters"})
KINDS = ("chapters", "appendices", "parts")


def merge(public: dict, private: dict) -> dict:
    """The public spec with every private stub replaced by its full private entry."""
    out = dict(public)
    for kind in KINDS:
        full = {entry["id"]: entry for entry in private.get(kind, [])}
        out[kind] = [full.get(entry["id"], entry) if entry.get("private") else entry
                     for entry in public.get(kind, [])]
    return out


def stub_violations(public: dict) -> list[str]:
    """Private entries of the published spec that carry more than a stub."""
    report: list[str] = []
    for kind in KINDS:
        for entry in public.get(kind, []):
            if entry.get("private"):
                extra = sorted(set(entry) - STUB_KEYS)
                if extra:
                    report.append(f"- data/spec.json {kind} `{entry['id']}` is private but publishes {', '.join(extra)}")
    return report


def load(public_path: pathlib.Path = PUBLIC, private_path: pathlib.Path = PRIVATE) -> dict:
    public = json.loads(public_path.read_text(encoding="utf-8"))
    if private_path.exists():
        return merge(public, json.loads(private_path.read_text(encoding="utf-8")))
    return public
