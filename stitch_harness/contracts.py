"""Validated project-level contracts for Stitch delivery runs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


PAGE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SUPPORTED_ASSERTIONS = {"dom-style"}


class ContractError(ValueError):
    """A page specification is unsafe or incomplete."""


def _required(mapping: dict[str, Any], key: str, expected_type):
    value = mapping.get(key)
    if not isinstance(value, expected_type):
        raise ContractError(f"{key} must be {expected_type.__name__}")
    return value


@dataclass(frozen=True)
class Canvas:
    width: int
    height: int
    scale: int


@dataclass(frozen=True)
class Comparison:
    critical_copy_recall: float
    layout_score_min: float
    visual_quality_score_min: int


@dataclass(frozen=True)
class BusinessAssertion:
    assertion_id: str
    assertion_type: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class PageSpec:
    schema_version: int
    page_id: str
    title: str
    canvas: Canvas
    theme: str
    fixed_copy: tuple[str, ...]
    editable_regions: tuple[str, ...]
    forbidden_patterns: tuple[str, ...]
    business_assertions: tuple[BusinessAssertion, ...]
    comparison: Comparison
    archive: str
    source: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "PageSpec":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ContractError("page specification is not valid UTF-8 JSON") from error
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PageSpec":
        if not isinstance(payload, dict):
            raise ContractError("page specification must be an object")
        schema_version = _required(payload, "schema_version", int)
        if schema_version != 1:
            raise ContractError("schema_version must be 1")
        page_id = _required(payload, "page_id", str)
        if PAGE_ID_PATTERN.fullmatch(page_id) is None:
            raise ContractError("page_id must be a safe lowercase slug")
        title = _required(payload, "title", str).strip()
        if not title:
            raise ContractError("title cannot be empty")

        canvas_data = _required(payload, "canvas", dict)
        width = _required(canvas_data, "width", int)
        height = _required(canvas_data, "height", int)
        scale = _required(canvas_data, "scale", int)
        if width < 1 or height < 1 or scale != 1:
            raise ContractError("canvas requires positive dimensions and scale 1")
        canvas = Canvas(width, height, scale)

        theme = _required(payload, "theme", str)
        fixed_copy = cls._string_tuple(payload, "fixed_copy", require_values=True)
        editable_regions = cls._string_tuple(payload, "editable_regions", require_values=True)
        forbidden_patterns = cls._string_tuple(payload, "forbidden_patterns", require_values=False)

        assertion_data = _required(payload, "business_assertions", list)
        assertions: list[BusinessAssertion] = []
        assertion_ids: set[str] = set()
        for item in assertion_data:
            if not isinstance(item, dict):
                raise ContractError("business assertion must be an object")
            assertion_id = _required(item, "id", str)
            assertion_type = _required(item, "type", str)
            if assertion_type not in SUPPORTED_ASSERTIONS:
                raise ContractError(f"unsupported business assertion type: {assertion_type}")
            if assertion_id in assertion_ids:
                raise ContractError(f"duplicate business assertion id: {assertion_id}")
            assertion_ids.add(assertion_id)
            parameters = {key: value for key, value in item.items() if key not in {"id", "type"}}
            assertions.append(BusinessAssertion(assertion_id, assertion_type, parameters))

        comparison_data = _required(payload, "comparison", dict)
        critical = comparison_data.get("critical_copy_recall")
        layout = comparison_data.get("layout_score_min")
        quality = comparison_data.get("visual_quality_score_min")
        if not isinstance(critical, (int, float)) or not 0 <= critical <= 1:
            raise ContractError("critical_copy_recall must be between 0 and 1")
        if not isinstance(layout, (int, float)) or not 0 <= layout <= 1:
            raise ContractError("layout_score_min must be between 0 and 1")
        if not isinstance(quality, int) or not 1 <= quality <= 5:
            raise ContractError("visual_quality_score_min must be between 1 and 5")
        comparison = Comparison(float(critical), float(layout), quality)

        archive = _required(payload, "archive", str)
        archive_path = PurePosixPath(archive)
        if archive_path.is_absolute() or ".." in archive_path.parts or not archive_path.parts:
            raise ContractError("archive must be a contained project-relative path")

        return cls(
            schema_version,
            page_id,
            title,
            canvas,
            theme,
            fixed_copy,
            editable_regions,
            forbidden_patterns,
            tuple(assertions),
            comparison,
            archive,
            json.loads(json.dumps(payload)),
        )

    @staticmethod
    def _string_tuple(payload: dict[str, Any], key: str, *, require_values: bool) -> tuple[str, ...]:
        values = _required(payload, key, list)
        if require_values and not values:
            raise ContractError(f"{key} cannot be empty")
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise ContractError(f"{key} must contain non-empty strings")
        if len(values) != len(set(values)):
            raise ContractError(f"{key} must not contain duplicates")
        return tuple(values)

