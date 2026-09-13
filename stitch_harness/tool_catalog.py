"""Validation and repair for the live Google Stitch MCP tool catalog."""

from __future__ import annotations

import copy
from collections.abc import Iterable
from typing import Any


REQUIRED_TOOL_NAMES = frozenset(
    {
        "apply_design_system",
        "create_design_system",
        "create_design_system_from_design_md",
        "create_project",
        "delete_project",
        "edit_screens",
        "generate_screen_from_text",
        "generate_variants",
        "get_project",
        "get_screen",
        "list_design_systems",
        "list_projects",
        "list_screens",
        "update_design_system",
        "upload_design_md",
    }
)

_REQUIRED_ANNOTATION_KEYS = ("readOnlyHint", "openWorldHint")
_OPTIONAL_ANNOTATION_KEYS = ("destructiveHint", "idempotentHint")

_KNOWN_DEFINITIONS: dict[str, dict[str, Any]] = {
    "ScreenInstance": {
        "description": "An instance of a screen on the project.",
        "type": "object",
        "properties": {
            "groupId": {"type": "string"},
            "groupName": {"type": "string"},
            "height": {"type": "integer", "format": "int32"},
            "hidden": {"type": "boolean"},
            "id": {"type": "string"},
            "isFavourite": {"type": "boolean"},
            "isResized": {"type": "boolean"},
            "label": {"type": "string"},
            "needsLayout": {"type": "boolean"},
            "sourceAsset": {"type": "string"},
            "sourceScreen": {"type": "string"},
            "textContent": {"type": "string"},
            "type": {
                "type": "string",
                "enum": [
                    "SCREEN_INSTANCE_TYPE_UNSPECIFIED",
                    "SCREEN_INSTANCE",
                    "DESIGN_SYSTEM_INSTANCE",
                    "GROUP_INSTANCE",
                    "TEXT_INSTANCE",
                ],
            },
            "variantScreenInstance": {"$ref": "#/$defs/ScreenInstance"},
            "width": {"type": "integer", "format": "int32"},
            "x": {"type": "integer", "format": "int32"},
            "y": {"type": "integer", "format": "int32"},
        },
    },
    "SelectedScreenInstance": {
        "description": "A screen instance selected by the user for editing.",
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "sourceScreen": {"type": "string"},
        },
        "required": ["id", "sourceScreen"],
    },
    "File": {
        "description": "A File resource.",
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "downloadUrl": {"type": "string"},
            "fileContentBase64": {"type": "string", "writeOnly": True},
            "mimeType": {"type": "string"},
            "uploadBlobId": {"type": "string"},
        },
    },
}


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _referenced_definition_names(schema: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for node in _walk(schema):
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            name = reference.removeprefix("#/$defs/").split("/", 1)[0]
            if name:
                names.add(name.replace("~1", "/").replace("~0", "~"))
    return names


def repair_tool_schemas(tools: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy tools and inject definitions omitted by the upstream catalog."""

    repaired = copy.deepcopy(list(tools))
    for tool in repaired:
        if not isinstance(tool, dict):
            continue
        for schema_name in ("inputSchema", "outputSchema"):
            schema = tool.get(schema_name)
            if not isinstance(schema, dict):
                continue
            referenced = _referenced_definition_names(schema)
            needed = referenced.intersection(_KNOWN_DEFINITIONS)
            if not needed:
                continue
            definitions = schema.setdefault("$defs", {})
            if not isinstance(definitions, dict):
                continue
            for name in sorted(needed):
                definitions.setdefault(name, copy.deepcopy(_KNOWN_DEFINITIONS[name]))
    return repaired


def validate_tool_catalog(tools: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    """Return deterministic errors for an incomplete or malformed catalog."""

    materialized = list(tools)
    errors: list[str] = []
    names: list[str] = []
    for index, tool in enumerate(materialized):
        if not isinstance(tool, dict):
            errors.append(f"tool at index {index} is not an object")
            continue
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"tool at index {index} has no valid name")
            continue
        names.append(name)
        annotations = tool.get("annotations")
        if not isinstance(annotations, dict):
            errors.append(f"{name}: annotations are missing")
        else:
            for key in _REQUIRED_ANNOTATION_KEYS:
                if not isinstance(annotations.get(key), bool):
                    errors.append(f"{name}: annotation {key} must be boolean")
            for key in _OPTIONAL_ANNOTATION_KEYS:
                if key in annotations and not isinstance(annotations[key], bool):
                    errors.append(f"{name}: annotation {key} must be boolean when present")
        for schema_name in ("inputSchema", "outputSchema"):
            schema = tool.get(schema_name)
            if not isinstance(schema, dict):
                errors.append(f"{name}: {schema_name} is missing")
                continue
            if schema.get("type") != "object":
                errors.append(f"{name}: {schema_name} must describe an object")
            definitions = schema.get("$defs", {})
            if not isinstance(definitions, dict):
                errors.append(f"{name}: {schema_name} $defs must be an object")
                continue
            for referenced in sorted(_referenced_definition_names(schema)):
                if referenced not in definitions:
                    errors.append(
                        f"{name}: {schema_name} has unresolved local definition {referenced}"
                    )

    seen: set[str] = set()
    duplicates: list[str] = []
    for name in names:
        if name in seen:
            duplicates.append(name)
        else:
            seen.add(name)
    if duplicates:
        errors.append(f"duplicate tool names: {', '.join(dict.fromkeys(duplicates))}")
    missing = sorted(REQUIRED_TOOL_NAMES.difference(names))
    if missing:
        errors.append(f"required tools are missing: {', '.join(missing)}")
    return tuple(errors)


def is_write_tool(name: str, annotations: dict[str, Any] | None = None) -> bool:
    """Classify a tool conservatively; only an explicit read hint is read-only."""

    del name
    return not isinstance(annotations, dict) or annotations.get("readOnlyHint") is not True


class ToolCatalog:
    """A validated, annotation-aware catalog assembled across MCP cursor pages."""

    def __init__(self, tools: Iterable[dict[str, Any]] = ()) -> None:
        self._tools: dict[str, dict[str, Any]] = {}
        self.extend(tools)

    @property
    def tools(self) -> tuple[dict[str, Any], ...]:
        """Return a detached snapshot in provider order."""

        return tuple(copy.deepcopy(list(self._tools.values())))

    def clear(self) -> None:
        """Start a new cursor traversal."""

        self._tools.clear()

    def extend(self, tools: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """Repair and add one page, rejecting duplicate names across pages."""

        repaired = repair_tool_schemas(tools)
        for tool in repaired:
            if not isinstance(tool, dict):
                raise ValueError("tool metadata must be an object")
            name = tool.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError("tool metadata must have a valid name")
            if name in self._tools:
                raise ValueError(f"duplicate tool name: {name}")
            self._tools[name] = copy.deepcopy(tool)
        return repaired

    def validation_errors(self) -> tuple[str, ...]:
        """Validate the assembled catalog."""

        return validate_tool_catalog(self._tools.values())

    def is_write_tool(self, name: str) -> bool:
        """Use live annotations, treating unknown tools as writes."""

        tool = self._tools.get(name)
        annotations = tool.get("annotations") if tool is not None else None
        return is_write_tool(name, annotations)
