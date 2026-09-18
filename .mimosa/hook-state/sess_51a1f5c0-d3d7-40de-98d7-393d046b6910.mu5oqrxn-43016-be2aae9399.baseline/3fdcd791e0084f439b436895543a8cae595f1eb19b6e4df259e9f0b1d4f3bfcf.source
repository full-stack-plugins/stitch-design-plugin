"""Deterministic HTML, canvas, copy, and editability gates."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from .contracts import PageSpec


def normalize_text(value: str) -> str:
    return " ".join(value.split())


@dataclass
class HtmlNode:
    tag: str
    attrs: dict[str, str]
    parent: "HtmlNode | None" = None
    children: list["HtmlNode"] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    @property
    def classes(self) -> tuple[str, ...]:
        return tuple(self.attrs.get("class", "").split())

    @property
    def style(self) -> dict[str, str]:
        declarations: dict[str, str] = {}
        for item in self.attrs.get("style", "").split(";"):
            if ":" not in item:
                continue
            name, value = item.split(":", 1)
            declarations[name.strip().lower()] = value.strip()
        return declarations

    def visible_text(self) -> str:
        values = list(self.text_parts)
        values.extend(child.visible_text() for child in self.children)
        return normalize_text(" ".join(value for value in values if value))


@dataclass(frozen=True)
class HtmlDocument:
    roots: tuple[HtmlNode, ...]
    raw: str

    def nodes(self) -> tuple[HtmlNode, ...]:
        found: list[HtmlNode] = []

        def visit(node: HtmlNode) -> None:
            found.append(node)
            for child in node.children:
                visit(child)

        for root in self.roots:
            visit(root)
        return tuple(found)

    def visible_text(self) -> str:
        return normalize_text(" ".join(root.visible_text() for root in self.roots))

    def by_purpose(self, purpose: str) -> tuple[HtmlNode, ...]:
        return tuple(node for node in self.nodes() if node.attrs.get("data-purpose") == purpose)


class _DocumentParser(HTMLParser):
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.roots: list[HtmlNode] = []
        self.stack: list[HtmlNode] = []

    def handle_starttag(self, tag, attrs):
        node = HtmlNode(tag.lower(), {name.lower(): value or "" for name, value in attrs})
        if self.stack:
            node.parent = self.stack[-1]
            self.stack[-1].children.append(node)
        else:
            self.roots.append(node)
        if tag.lower() not in self._VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1].tag == tag.lower():
            self.stack.pop()

    def handle_endtag(self, tag):
        lowered = tag.lower()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == lowered:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack and self.stack[-1].tag not in {"script", "style", "template"}:
            self.stack[-1].text_parts.append(data)


@dataclass(frozen=True)
class GateResult:
    failures: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.failures


def parse_html(path: Path) -> HtmlDocument:
    raw = path.read_text(encoding="utf-8")
    parser = _DocumentParser()
    parser.feed(raw)
    parser.close()
    return HtmlDocument(tuple(parser.roots), raw)


def validate_html(spec: PageSpec, html_path: Path, render_metadata: dict) -> GateResult:
    failures: list[str] = []
    expected_canvas = (spec.canvas.width, spec.canvas.height, spec.canvas.scale)
    actual_canvas = (
        render_metadata.get("width"),
        render_metadata.get("height"),
        render_metadata.get("scale"),
    )
    if actual_canvas != expected_canvas:
        failures.append(f"canvas dimensions must be {expected_canvas}, got {actual_canvas}")
    try:
        document = parse_html(html_path)
    except (OSError, UnicodeDecodeError) as error:
        return GateResult((f"HTML could not be read: {type(error).__name__}", *failures))
    nodes = document.nodes()
    meaningful = [node for node in nodes if node.tag not in {"html", "head", "body", "meta", "link", "title"}]
    if not meaningful or all(node.tag in {"img", "canvas"} for node in meaningful):
        failures.append("HTML is flattened and has no editable DOM structure")
    visible = document.visible_text()
    for required in spec.fixed_copy:
        if normalize_text(required) not in visible:
            failures.append(f"missing fixed copy: {required}")
    for pattern in spec.forbidden_patterns:
        try:
            matched = re.search(pattern, document.raw)
        except re.error:
            failures.append(f"invalid forbidden pattern: {pattern}")
        else:
            if matched:
                failures.append(f"forbidden pattern matched: {pattern}")
    for purpose in spec.editable_regions:
        matches = document.by_purpose(purpose)
        if len(matches) != 1:
            failures.append(f"editable region must occur exactly once: {purpose}")
    from .business_gate import validate_business_assertions

    failures.extend(validate_business_assertions(spec, document).failures)
    return GateResult(tuple(failures))

