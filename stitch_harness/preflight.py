"""Read-only readiness checks for a Harness run."""

from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
from pathlib import Path

from .mcp_proxy import McpHttpSession, PROTOCOL_VERSION, ProxyError
from .secrets import SecretStoreError, platform_secret_provider
from .tool_catalog import ToolCatalog


_MISSING_GLOBAL_MCP = re.compile(
    r"No MCP server named ['\"]stitch['\"] found\.\s*$",
    re.IGNORECASE,
)
_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_CODEX_PLUGIN_CACHE_ROOT = Path.home() / ".codex" / "plugins" / "cache"
_STDIO_FIELDS = frozenset(
    {"enabled", "transport", "command", "args", "cwd", "env", "remove"}
)
_HTTP_FIELDS = frozenset(
    {
        "enabled",
        "transport",
        "url",
        "bearer_token_env_var",
        "http_headers",
        "env_http_headers",
        "http_headers_helper",
        "remove",
    }
)
_SECRET_ENVIRONMENT_MARKERS = (
    "ACCESS_KEY",
    "API_KEY",
    "APIKEY",
    "AUTHORIZATION",
    "BEARER",
    "COOKIE",
    "CREDENTIAL",
    "PASSWORD",
    "PRIVATE_KEY",
    "SECRET",
    "TOKEN",
    "WEBHOOK",
)


def _codex_cli_environment() -> dict[str, str]:
    environment: dict[str, str] = {}
    for name, value in os.environ.items():
        normalized = name.upper()
        if normalized.startswith("STITCH_"):
            continue
        if any(marker in normalized for marker in _SECRET_ENVIRONMENT_MARKERS):
            continue
        environment[name] = value
    return environment


def _global_mcp_is_absent(result: subprocess.CompletedProcess[str]) -> bool:
    output = f"{result.stdout}\n{result.stderr}".strip()
    return result.returncode == 1 and _MISSING_GLOBAL_MCP.search(output) is not None


def _parse_mcp_registration(result: subprocess.CompletedProcess[str]) -> dict[str, str] | None:
    if result.returncode != 0 or result.stderr.strip():
        return None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines or lines[0].strip() != "stitch":
        return None
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if not line[:1].isspace() or ":" not in line:
            return None
        name, value = line.strip().split(":", 1)
        if not name or name in fields or not value.strip():
            return None
        fields[name] = value.strip()
    transport = fields.get("transport")
    required_fields = _STDIO_FIELDS if transport == "stdio" else _HTTP_FIELDS
    if transport not in {"stdio", "streamable_http"} or set(fields) != required_fields:
        return None
    if fields["enabled"] not in {"true", "false"}:
        return None
    return fields


def _is_plugin_owned_stdio(fields: dict[str, str]) -> bool:
    if (
        fields.get("enabled") != "true"
        or fields.get("transport") != "stdio"
        or fields.get("command") not in {"python", "python3"}
        or fields.get("args") != "scripts/stitch_mcp_proxy.py"
        or fields.get("env") != "-"
    ):
        return False
    configured_cwd = Path(fields["cwd"]).expanduser()
    if not configured_cwd.is_absolute():
        return False
    try:
        resolved_cwd = configured_cwd.resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    configured_script = (resolved_cwd / fields["args"]).resolve()
    source_script = (_PLUGIN_ROOT / "scripts" / "stitch_mcp_proxy.py").resolve()
    if configured_script == source_script:
        return True
    try:
        resolved_cwd.relative_to(_CODEX_PLUGIN_CACHE_ROOT.resolve())
        if configured_script != (resolved_cwd / "scripts" / "stitch_mcp_proxy.py").resolve():
            return False
        manifest = json.loads(
            (resolved_cwd / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
        return False
    return isinstance(manifest, dict) and manifest.get("name") == "stitch-design"


def _mcp_registration_status(result: subprocess.CompletedProcess[str]) -> str:
    if _global_mcp_is_absent(result):
        return "absent"
    fields = _parse_mcp_registration(result)
    if fields is None:
        return "invalid"
    if _is_plugin_owned_stdio(fields):
        return "plugin"
    return "conflict"


def _response_for_id(responses: list[dict], identifier: int) -> dict | None:
    final_responses = [
        response for response in responses if isinstance(response, dict) and "id" in response
    ]
    if len(final_responses) != 1:
        return None
    response = final_responses[0]
    if (
        response.get("jsonrpc") != "2.0"
        or isinstance(response.get("id"), bool)
        or type(response.get("id")) is not type(identifier)
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
                    "clientInfo": {"name": "stitch-delivery-harness", "version": "0.8.5"},
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
    cli_environment = _codex_cli_environment()
    try:
        global_mcp = subprocess.run(
            [codex, "mcp", "get", "stitch"],
            capture_output=True,
            text=True,
            check=False,
            env=cli_environment,
        )
    except OSError:
        errors.append("Codex global MCP configuration could not be read")
        return tuple(errors)
    registration_status = _mcp_registration_status(global_mcp)
    if registration_status == "conflict":
        errors.append(
            "separate global Stitch MCP detected; run `codex mcp remove stitch` and retry"
        )
        return tuple(errors)
    if registration_status == "invalid":
        errors.append("Codex global MCP configuration could not be read")
        return tuple(errors)
    try:
        result = subprocess.run(
            [codex, "plugin", "list"],
            capture_output=True,
            text=True,
            check=False,
            env=cli_environment,
        )
    except OSError:
        errors.append("Codex plugin list could not be read")
        return tuple(errors)
    if result.returncode != 0:
        errors.append("Codex plugin list could not be read")
        return tuple(errors)
    enabled = [line for line in result.stdout.splitlines() if "stitch-design@" in line and "enabled" in line]
    if len(enabled) != 1:
        errors.append(f"expected one enabled Stitch Design plugin, found {len(enabled)}")
    if not errors:
        errors.extend(stitch_read_probe(McpHttpSession(provider=provider)))
    return tuple(errors)
