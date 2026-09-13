"""Typed, deterministic business assertions over normalized HTML."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .contracts import BusinessAssertion, PageSpec
from .html_gate import GateResult, HtmlDocument, HtmlNode


_PURPOSE_CHILDREN = re.compile(r"^\[data-purpose='([a-z0-9-]+)'\] > \*$")


@dataclass(frozen=True)
class BusinessGateResult(GateResult):
    failed_ids: tuple[str, ...] = ()


def _property_present(node: HtmlNode, property_name: str) -> bool:
    value = node.style.get(property_name, "").strip().lower()
    if value and value not in {"none", "0", "0px", "initial", "unset"}:
        return True
    classes = node.classes
    if property_name == "border-radius":
        return any(token == "rounded" or token.startswith("rounded-") for token in classes)
    if property_name == "box-shadow":
        return any(token == "shadow" or token.startswith("shadow-") for token in classes)
    if property_name == "background-image":
        return any("gradient" in token for token in classes)
    return False


def _validate_dom_style(assertion: BusinessAssertion, document: HtmlDocument) -> list[str]:
    selector = assertion.parameters.get("selector")
    expected_count = assertion.parameters.get("count")
    forbidden = assertion.parameters.get("forbidden_properties")
    if not isinstance(selector, str) or not isinstance(expected_count, int) or not isinstance(forbidden, list):
        return [f"{assertion.assertion_id}: invalid dom-style parameters"]
    match = _PURPOSE_CHILDREN.fullmatch(selector)
    if match is None:
        return [f"{assertion.assertion_id}: unsupported selector"]
    parents = document.by_purpose(match.group(1))
    if len(parents) != 1:
        return [f"{assertion.assertion_id}: selector parent must occur exactly once"]
    children = parents[0].children
    failures: list[str] = []
    if len(children) != expected_count:
        failures.append(f"{assertion.assertion_id}: expected {expected_count} direct children, got {len(children)}")
    for index, child in enumerate(children):
        for property_name in forbidden:
            if not isinstance(property_name, str):
                failures.append(f"{assertion.assertion_id}: forbidden property must be a string")
            elif _property_present(child, property_name):
                failures.append(f"{assertion.assertion_id}: child {index + 1} uses {property_name}")
    return failures


def validate_business_assertions(spec: PageSpec, document: HtmlDocument) -> BusinessGateResult:
    failures: list[str] = []
    failed_ids: list[str] = []
    for assertion in spec.business_assertions:
        if assertion.assertion_type == "dom-style":
            current = _validate_dom_style(assertion, document)
        else:
            current = [f"{assertion.assertion_id}: unsupported assertion type"]
        if current:
            failures.extend(current)
            failed_ids.append(assertion.assertion_id)
    return BusinessGateResult(tuple(failures), tuple(failed_ids))
