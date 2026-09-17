#!/usr/bin/env python3
"""Execute the extracted listings that the manifest allows.

Each runnable listing is started as its own process with the examples
directory as working directory (so the stubs import), a wall-clock limit,
and no network expectation. A non-zero exit or a timeout fails the check.
Listings marked data-run="no" in the book are skipped and reported.
"""
import json
import pathlib
import subprocess
import sys

TIMEOUT = 20


def run(out: pathlib.Path) -> tuple[int, int, list[str]]:
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    ran = skipped = 0
    for name in sorted(manifest):
        if not manifest[name]:
            skipped += 1
            continue
        ran += 1
        try:
            proc = subprocess.run([sys.executable, name], cwd=out, capture_output=True,
                                  text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            failures.append(f"{name}: timeout after {TIMEOUT}s")
            continue
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
            failures.append(f"{name}: exit {proc.returncode}: " + " | ".join(tail))
    return ran, skipped, failures


def main() -> int:
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "examples")
    ran, skipped, failures = run(out)
    for line in failures:
        print(line)
    print(f"listings executed: {ran}, skipped by manifest: {skipped}, failed: {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
