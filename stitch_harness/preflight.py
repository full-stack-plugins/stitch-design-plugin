"""Read-only readiness checks for a Harness run."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .mcp_proxy import McpHttpSession, PROTOCOL_VERSION, ProxyError
from .secrets import SecretStoreError, platform_secret_provider
from .tool_catalog import ToolCatalog


def _response_for_id(responses: list[dict], identifier: int) -> dict | None:
    final_responses = [
        response for response in responses if isinstance(response, dict) and "id" in response
    ]
    if len(final_responses) != 1:
        return None
    response = final_responses[0]
    if (
        response.get("jsonrpc") != "2.0"
        or response.get("id") != identifier
        or "error" in response
    ):
        return None
    return response


def stitch_read_probe(session: McpHttpSession) -> tuple[str, ...]:
    """Prove account-level authorization with a read-only Stitch call."""

    try:
        initialize_responses = session.send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "stitch-delivery-harness", "version": "0.5.1"},
                },
            }
        )
        initialize_response = _response_for_id(initialize_responses, 1)
        if initialize_response is None:
            return ("Stitch MCP initialize response is invalid",)
        initialize_result = initialize_response.get("result")
        if not isinstance(initialize_result, dict):
            return ("Stitch MCP initialize response is invalid",)
        capabilities = initialize_result.get("capabilities")
        if (
            initialize_result.get("protocolVersion") != PROTOCOL_VERSION
            or not isinstance(capabilities, dict)
            or not isinstance(capabilities.get("tools"), dict)
        ):
            return ("Stitch MCP initialize response is invalid",)

        session.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        catalog = ToolCatalog()
        request_id = 2
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            params = {"cursor": cursor} if cursor is not None else {}
            catalog_responses = session.send(
                {"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": params}
            )
            catalog_response = _response_for_id(catalog_responses, request_id)
            if catalog_response is None or not isinstance(catalog_response.get("result"), dict):
                return ("Stitch MCP tool catalog is invalid",)
            catalog_result = catalog_response["result"]
            tools = catalog_result.get("tools")
            if not isinstance(tools, list):
                return ("Stitch MCP tool catalog is invalid",)
            try:
                catalog.extend(tools)
            except ValueError:
                return ("Stitch MCP tool catalog is invalid",)
            next_cursor = catalog_result.get("nextCursor")
            if next_cursor is None:
                break
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
                return ("Stitch MCP tool catalog is invalid",)
            seen_cursors.add(next_cursor)
            cursor = next_cursor
            request_id += 1

        catalog_errors = catalog.validation_errors()
        if catalog_errors:
            return (f"Stitch MCP tool catalog is invalid: {'; '.join(catalog_errors)}",)
        request_id += 1
        responses = session.send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": "list_projects", "arguments": {}},
            }
        )
    except ProxyError:
        return ("Stitch read-only account probe failed",)
    response = _response_for_id(responses, request_id)
    if response is None:
        return ("Stitch read-only account probe failed",)
    result = response.get("result")
    if not isinstance(result, dict) or result.get("isError") is True:
        return ("Stitch read-only account probe failed",)
    structured_content = result.get("structuredContent")
    if not isinstance(structured_content, dict) or not isinstance(
        structured_content.get("projects"), list
    ):
        return ("Stitch read-only account probe failed",)
    return ()


def default_preflight(_project_root: Path) -> tuple[str, ...]:
    errors: list[str] = []
    provider = platform_secret_provider()
    try:
        if not provider.get():
            errors.append("Stitch credential is not configured")
    except SecretStoreError as error:
        errors.append(str(error))
    codex = shutil.which("codex")
    if codex is None:
        errors.append("Codex CLI is unavailable for plugin uniqueness check")
        return tuple(errors)
    global_mcp = subprocess.run(
        [codex, "mcp", "get", "stitch"], capture_output=True, text=True, check=False
    )
    if global_mcp.returncode == 0:
        errors.append(
            "separate global Stitch MCP detected; run `codex mcp remove stitch` and retry"
        )
        return tuple(errors)
    result = subprocess.run([codex, "plugin", "list"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        errors.append("Codex plugin list could not be read")
        return tuple(errors)
    enabled = [line for line in result.stdout.splitlines() if "stitch-design@" in line and "enabled" in line]
    if len(enabled) != 1:
        errors.append(f"expected one enabled Stitch Design plugin, found {len(enabled)}")
    if not errors:
        errors.extend(stitch_read_probe(McpHttpSession(provider=provider)))
    return tuple(errors)
