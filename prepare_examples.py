#!/usr/bin/env python3
"""Prepare the extracted listings for type checking and execution.

Excerpts with top-level await or return are wrapped in a function: they
cannot be compiled, and hence checked, otherwise. An import of the names
whose implementations live in the stubs is then prepended to each file.
The listings inside the book itself are never modified.
"""
import json
import pathlib
import subprocess
import sys
import textwrap

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "examples")
HEADER = "# Extracted from the book automatically. Lines above the mark are not part of the listing.\n"
MARK = "# --- the listing ---\n"


def undefined_names() -> dict[str, list[str]]:
    raw = subprocess.run(
        ["ruff", "check", "--select", "F821", "--output-format", "json", str(OUT)],
        capture_output=True, text=True).stdout
    found: dict[str, set[str]] = {}
    for item in json.loads(raw) if raw.strip() else []:
        message = item["message"]
        if not message.startswith("Undefined name `"):
            continue
        name = message.split("`")[1]
        found.setdefault(pathlib.Path(item["filename"]).name, set()).add(name)
    return {k: sorted(v) for k, v in found.items()}


def wrap_if_needed() -> int:
    wrapped = 0
    for path in sorted(OUT.glob("*.py")):
        if path.name == "stubs.py":
            continue
        source = path.read_text(encoding="utf-8")
        try:
            compile(source, str(path), "exec")
        except SyntaxError:
            body = textwrap.indent(source.rstrip("\n"), "    ")
            path.write_text("from typing import Any\n\n\nasync def _excerpt() -> Any:\n" + body + "\n", encoding="utf-8")
            wrapped += 1
    return wrapped


def inject_imports(names: dict[str, list[str]]) -> int:
    touched = 0
    for path in sorted(OUT.glob("*.py")):
        if path.name == "stubs.py":
            continue
        needed = names.get(path.name, [])
        if not needed:
            continue
        source = path.read_text(encoding="utf-8")
        line = "from stubs import " + ", ".join(needed) + "  # noqa: F401\n"
        path.write_text(HEADER + line + MARK + source, encoding="utf-8")
        touched += 1
    return touched


def main() -> None:
    print("excerpts wrapped:", wrap_if_needed())
    print("files given stub imports:", inject_imports(undefined_names()))
    left = undefined_names()
    left.pop("stubs.py", None)
    if left:
        print("still undefined:")
        for name, items in sorted(left.items()):
            print(" ", name, items)
        sys.exit(1)
    print("no undefined names remain")


if __name__ == "__main__":
    main()
