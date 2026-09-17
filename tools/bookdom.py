#!/usr/bin/env python3
"""A small structural reader for the assembled book.

The checkers need counts and ordered lists per locale and per chapter, not a
full DOM. This module parses the page once with html.parser and records the
elements the book's conventions are built on: sections, headings with ids,
code figures (file name, code text), diagram figures (svg attributes and
body, caption), definition lists, callouts, quizzes, tabs and detail levels.
"""
from __future__ import annotations

import html as htmlmod
import html.parser
from dataclasses import dataclass, field


@dataclass
class Listing:
    chapter: str
    file: str
    code: str
    attrs: dict[str, str]


@dataclass
class Diagram:
    chapter: str
    attrs: dict[str, str]
    body: str
    caption: str
    steps: list[str]


@dataclass
class Chapter:
    id: str
    kind: str                       # cover | part | chapter
    headings: list[tuple[str, str, str]] = field(default_factory=list)   # (tag, id, text)
    listings: list[Listing] = field(default_factory=list)
    diagrams: list[Diagram] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    levels: dict[str, int] = field(default_factory=dict)
    layers: str = ""
    anchors: list[str] = field(default_factory=list)     # href="#..." targets
    ids: list[str] = field(default_factory=list)


@dataclass
class Locale:
    code: str
    chapters: list[Chapter] = field(default_factory=list)
    todo: int = 0

    def chapter(self, cid: str) -> Chapter | None:
        return next((c for c in self.chapters if c.id == cid), None)


COUNTED = {"def": "dl", "warn": "div", "note": "div", "aside": "div", "quiz": "div",
           "tabs": "div", "goals": "div", "recap": "div", "rec": "div", "checklist": "div"}


class Reader(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.locales: list[Locale] = []
        self.cur: Locale | None = None
        self.chapter: Chapter | None = None
        self.stack: list[tuple[str, dict[str, str]]] = []
        self.capture: list[str] | None = None
        self.capture_tag: str | None = None
        self.capture_depth = 0
        self.listing: Listing | None = None
        self.diagram: Diagram | None = None
        self.in_code = False
        self.code_buf: list[str] = []
        self.in_file = False
        self.file_buf: list[str] = []
        self.heading: tuple[str, str] | None = None
        self.heading_buf: list[str] = []
        self.svg_depth = 0
        self.svg_buf: list[str] = []
        self.caption_buf: list[str] | None = None
        self.in_quiz = 0

    # ── helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def classes(attrs: dict[str, str]) -> set[str]:
        return set((attrs.get("class") or "").split())

    def bump(self, key: str) -> None:
        if self.chapter is not None:
            self.chapter.counts[key] = self.chapter.counts.get(key, 0) + 1

    # ── parser events ───────────────────────────────────────────────────
    def handle_starttag(self, tag: str, attrlist: list[tuple[str, str | None]]) -> None:
        attrs = {k: (v or "") for k, v in attrlist}
        cls = self.classes(attrs)
        self.stack.append((tag, attrs))
        if self.svg_depth:
            self.svg_depth += 1
            self.svg_buf.append(self.get_starttag_text() or "")
            if attrs.get("data-step") and self.diagram is not None:
                self.diagram.steps.append(attrs["data-step"])
            return
        if tag == "div" and "locale" in cls:
            self.cur = Locale(code=attrs.get("data-locale", "?"))
            self.locales.append(self.cur)
            self.chapter = None
            return
        if self.cur is None:
            return
        if tag == "section" and ({"chapter", "part", "cover"} & cls):
            kind = "chapter" if "chapter" in cls else "part" if "part" in cls else "cover"
            self.chapter = Chapter(id=attrs.get("id", ""), kind=kind)
            self.cur.chapters.append(self.chapter)
        if self.chapter is None:
            return
        if attrs.get("id"):
            self.chapter.ids.append(attrs["id"])
        if tag == "a" and attrs.get("href", "").startswith("#"):
            self.chapter.anchors.append(attrs["href"][1:])
        if tag in ("h2", "h3") and attrs.get("id"):
            self.heading = (tag, attrs["id"])
            self.heading_buf = []
        if tag == "span" and "strata" in cls:
            self.chapter.layers = ""
            self._in_strata = True
        if tag == "i" and getattr(self, "_in_strata", False):
            self.chapter.layers += attrs.get("data-s", "") or "."
        if attrs.get("data-level"):
            lvl = attrs["data-level"]
            self.chapter.levels[lvl] = self.chapter.levels.get(lvl, 0) + 1
        if tag == "figure" and "code" in cls:
            self.listing = Listing(chapter=self.chapter.id, file="", code="", attrs=attrs)
            self.chapter.listings.append(self.listing)
        if tag == "figure" and "dia" in cls:
            self.diagram = Diagram(chapter=self.chapter.id, attrs={}, body="", caption="", steps=[])
            self.chapter.diagrams.append(self.diagram)
        if tag == "svg" and self.diagram is not None:
            self.diagram.attrs = attrs
            self.svg_depth = 1
            self.svg_buf = []
            return
        if tag == "figcaption" and self.diagram is not None and self.listing is None:
            self.caption_buf = []
        if tag == "span" and "file" in cls and self.listing is not None:
            self.in_file = True
            self.file_buf = []
        if tag == "code" and self.listing is not None and self.stack[-2][0] == "pre":
            self.in_code = True
            self.code_buf = []
        for key, wanted in COUNTED.items():
            if tag == wanted and key in cls:
                self.bump(key)
        if tag == "div" and "quiz" in cls:
            self.in_quiz += 1
        if tag == "details" and self.in_quiz:
            self.bump("question")
        if tag == "div" and attrs.get("role") == "tabpanel":
            self.bump("tabpanel")
        if attrs.get("data-round"):
            self.bump("qbank")

    def handle_endtag(self, tag: str) -> None:
        if self.svg_depth:
            self.svg_depth -= 1
            if self.svg_depth == 0:
                if self.diagram is not None:
                    self.diagram.body = "".join(self.svg_buf)
                self.svg_buf = []
            else:
                self.svg_buf.append(f"</{tag}>")
            if self.stack and self.stack[-1][0] == tag:
                self.stack.pop()
            return
        top = self.stack.pop() if self.stack else ("", {})
        cls = self.classes(top[1])
        if tag == "div" and "locale" in cls:
            self.cur = None
            self.chapter = None
            return
        if self.chapter is None:
            return
        if tag in ("h2", "h3") and self.heading and self.heading[0] == tag:
            text = " ".join("".join(self.heading_buf).split())
            self.chapter.headings.append((tag, self.heading[1], text))
            self.heading = None
        if tag == "span" and getattr(self, "_in_strata", False) and "strata" in cls:
            self._in_strata = False
        if tag == "span" and self.in_file:
            self.in_file = False
            if self.listing is not None:
                self.listing.file = "".join(self.file_buf).strip()
        if tag == "code" and self.in_code:
            self.in_code = False
            if self.listing is not None:
                self.listing.code = htmlmod.unescape("".join(self.code_buf)).strip("\n")
        if tag == "figcaption" and self.caption_buf is not None and self.diagram is not None:
            self.diagram.caption = " ".join("".join(self.caption_buf).split())
            self.caption_buf = None
        if tag == "figure" and "code" in cls:
            self.listing = None
        if tag == "figure" and "dia" in cls:
            self.diagram = None
        if tag == "div" and "quiz" in cls:
            self.in_quiz -= 1

    def handle_startendtag(self, tag: str, attrlist: list[tuple[str, str | None]]) -> None:
        if self.svg_depth:
            self.svg_buf.append(self.get_starttag_text() or "")
            attrs = {k: (v or "") for k, v in attrlist}
            if attrs.get("data-step") and self.diagram is not None:
                self.diagram.steps.append(attrs["data-step"])
            return
        self.handle_starttag(tag, attrlist)
        self.handle_endtag(tag)

    def _text(self, data: str) -> None:
        if self.svg_depth:
            self.svg_buf.append(data)
            return
        if self.cur is not None and "TODO-BOOK" in data:
            self.cur.todo += 1
        if self.in_code:
            self.code_buf.append(data)
        if self.in_file:
            self.file_buf.append(data)
        if self.heading is not None:
            self.heading_buf.append(htmlmod.unescape(data))
        if self.caption_buf is not None:
            self.caption_buf.append(htmlmod.unescape(data))

    def handle_data(self, data: str) -> None:
        self._text(data)

    def handle_entityref(self, name: str) -> None:
        self._text(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._text(f"&#{name};")


def read(text: str) -> list[Locale]:
    reader = Reader()
    reader.feed(text)
    reader.close()
    return reader.locales
