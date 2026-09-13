"""Read-only readiness checks for a Harness run."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .mcp_proxy import McpHttpSession, ProxyError
from .secrets import SecretStoreError, platform_secret_provider


def stitch_read_probe(session: McpHttpSession) -> tuple[str, ...]:
    """Prove account-level authorization with a read-only Stitch call."""

    try:
        session.send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "stitch-delivery-harness", "version": "0.5.1"},
                },
            }
        )
        session.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        responses = session.send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_projects", "arguments": {}},
            }
        )
    except ProxyError:
        return ("Stitch read-only account probe failed",)
    if len(responses) != 1 or "error" in responses[0]:
        return ("Stitch read-only account probe failed",)
    result = responses[0].get("result")
    if not isinstance(result, dict) or result.get("isError") is True:
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
