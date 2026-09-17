#!/usr/bin/env python3
"""Launch the Stitch Design local MCP proxy (stdio by default, HTTP via --http)."""

from __future__ import annotations

import sys
from pathlib import Path


def require_supported_python(version_info=sys.version_info) -> bool:
    """Reject interpreters that cannot run the supported proxy implementation."""

    if tuple(version_info[:2]) < (3, 11):
        print("Stitch Design MCP requires Python 3.11 or newer on PATH.", file=sys.stderr)
        return False
    return True


if not require_supported_python():
    raise SystemExit(1)


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from stitch_harness.mcp_proxy import McpHttpSession, serve_stdio  # noqa: E402
from stitch_harness.secrets import platform_secret_provider  # noqa: E402


def run_http(arguments: list[str]) -> int:
    from stitch_harness.http_endpoint import HttpEndpointConfig, serve_http

    config = HttpEndpointConfig()
    for index, value in enumerate(arguments):
        if value == "--port" and index + 1 < len(arguments):
            try:
                config.port = int(arguments[index + 1])
            except ValueError:
                print("Invalid --port value.", file=sys.stderr)
                return 2
    session = McpHttpSession(provider=platform_secret_provider(), enable_adc=True)
    return serve_http(session, config)


def main(arguments: list[str]) -> int:
    if arguments and arguments[0] == "--http":
        return run_http(arguments[1:])
    return serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
