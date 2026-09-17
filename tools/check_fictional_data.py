#!/usr/bin/env python3
"""Personal data in the book's examples must be fictional by construction.

Listings and prose show phone numbers and e-mail addresses of customers,
attackers and callers. A plausible number or address may belong to a real
person, so the book uses only ranges reserved for fiction and documentation:

  * phone numbers: the UK drama range +44 7700 900000 to 900999 (Ofcom);
  * e-mail domains: the .example, .test and .invalid top-level domains and
    example.com, example.net, example.org (RFC 2606, RFC 6761).

The check reads the source files of both builds, code included.

Usage: tools/check_fictional_data.py [source files...]   (default: parts/, private/parts/)
Exit codes: 0 — only reserved values; 11 — violations, report on stdout.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PHONE = re.compile(r"\+\d[\d \t()-]{8,}\d")
EMAIL = re.compile(r"[\w.+-]+@((?:[\w-]+\.)+[A-Za-z]{2,})\b")
FICTIONAL_PHONE_PREFIX = "447700900"
RESERVED_TLDS = ("example", "test", "invalid")
RESERVED_DOMAINS = ("example.com", "example.net", "example.org")


def violations(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for m in PHONE.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if not (digits.startswith(FICTIONAL_PHONE_PREFIX) and len(digits) == 12):
            out.append((text.count("\n", 0, m.start()) + 1, f"phone number {m.group()!r}"))
    for m in EMAIL.finditer(text):
        domain = m.group(1).lower()
        reserved = domain.rsplit(".", 1)[-1] in RESERVED_TLDS or any(
            domain == d or domain.endswith("." + d) for d in RESERVED_DOMAINS)
        if not reserved:
            out.append((text.count("\n", 0, m.start()) + 1, f"e-mail address {m.group()!r}"))
    return sorted(out)


def main() -> int:
    args = sys.argv[1:]
    files = [pathlib.Path(a) for a in args] if args else sorted(
        list((ROOT / "parts").glob("*/*.html")) + list((ROOT / "private" / "parts").glob("*/*.html")))
    report = [f"- {f}:{line}: {what}" for f in files for line, what in violations(f.read_text(encoding="utf-8"))]
    if not report:
        print(f"fictional data: ok ({len(files)} files)")
        return 0
    print("## Phone numbers or e-mail addresses outside the ranges reserved for fiction\n")
    print("\n".join(report))
    return 11


if __name__ == "__main__":
    sys.exit(main())
