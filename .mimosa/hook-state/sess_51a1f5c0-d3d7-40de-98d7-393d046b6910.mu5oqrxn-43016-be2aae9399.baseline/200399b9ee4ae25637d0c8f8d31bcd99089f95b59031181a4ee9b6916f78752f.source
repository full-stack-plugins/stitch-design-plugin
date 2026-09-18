"""Local HTTP MCP endpoint that lets hosts run the native MCP OAuth flow.

The host (Codex) points at ``http://127.0.0.1:<port>/mcp``. On the first
unauthenticated call this endpoint answers 401 with a RFC 9728 resource
metadata URL; the host discovers that Google is the authorization server,
performs the browser consent (PKCE + pre-registered client id), and retries
with ``Authorization: Bearer``. The bearer token is forwarded verbatim to the
upstream Stitch MCP, so token storage and refresh stay with the host.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .auth import StitchCredential
from .mcp_proxy import McpHttpSession, ProxyError, UnknownWriteResult

GOOGLE_AUTHORIZATION_SERVER = "https://accounts.google.com"
DEFAULT_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
DEFAULT_SCOPES = (DEFAULT_CLOUD_PLATFORM_SCOPE, "openid", "email")
WELL_KNOWN_PATHS = (
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-protected-resource/mcp",
)
MAX_BODY_BYTES = 8 * 1024 * 1024


def env_scopes(env: dict[str, str] | None = None) -> list[str]:
    raw = str((env if env is not None else os.environ).get("STITCH_OAUTH_SCOPES", "")).strip()
    if not raw:
        return list(DEFAULT_SCOPES)
    scopes = [scope.strip() for scope in raw.split() if scope.strip()]
    return scopes or list(DEFAULT_SCOPES)


def env_quota_project(env: dict[str, str] | None = None) -> str | None:
    source = env if env is not None else os.environ
    for name in ("GOOGLE_CLOUD_PROJECT", "STITCH_PROJECT_ID"):
        value = source.get(name, "").strip()
        if value:
            return value
    return None


@dataclass
class HttpEndpointConfig:
    """Configuration for the local OAuth-capable MCP HTTP endpoint."""

    host: str = "127.0.0.1"
    port: int = 0
    scopes: list[str] = field(default_factory=env_scopes)
    quota_project: str | None = field(default_factory=env_quota_project)

    def resource_metadata(self, base_url: str) -> dict:
        return {
            "resource": f"{base_url}/mcp",
            "authorization_servers": [GOOGLE_AUTHORIZATION_SERVER],
            "scopes_supported": list(self.scopes),
            "bearer_methods_supported": ["header"],
        }


def create_http_endpoint(
    session: McpHttpSession,
    config: HttpEndpointConfig | None = None,
    *,
    bound_base_url: str | None = None,
):
    """Build a ThreadingHTTPServer exposing the OAuth-capable MCP endpoint.

    ``bound_base_url`` pins the externally visible URL (used when the server
    binds to port 0 in tests); production binds an explicit port.
    """

    endpoint_config = config or HttpEndpointConfig()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def _send(self, status: int, body: bytes, content_type: str, headers: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", content_type)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _base_url(self) -> str:
            if bound_base_url:
                return bound_base_url
            return f"http://{endpoint_config.host}:{self.server.server_port}"

        def _metadata_url(self) -> str:
            return f"{self._base_url()}{WELL_KNOWN_PATHS[0]}"

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in WELL_KNOWN_PATHS:
                body = json.dumps(endpoint_config.resource_metadata(self._base_url()), separators=(",", ":"))
                self._send(200, body.encode("utf-8"), "application/json")
                return
            self._send(404, b'{"error":"not found"}', "application/json")

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path != "/mcp":
                self._send(404, b'{"error":"not found"}', "application/json")
                return
            authorization = self.headers.get("Authorization", "")
            token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
            if not token:
                self._send(
                    401,
                    b'{"error":"authorization required"}',
                    "application/json",
                    {"WWW-Authenticate": f'Bearer resource_metadata="{self._metadata_url()}"'},
                )
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length < 1 or length > MAX_BODY_BYTES:
                self._send(400, b'{"error":"invalid body"}', "application/json")
                return
            try:
                message = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                error = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
                self._send(400, json.dumps(error).encode("utf-8"), "application/json")
                return

            session.fixed_credential = StitchCredential(
                access_token=token,
                quota_project=endpoint_config.quota_project,
                source="host-oauth",
            )
            try:
                responses = session.send(message)
            except UnknownWriteResult as error:
                self._send_jsonrpc_error(message, -32001, str(error))
            except ProxyError as error:
                text = str(error)
                if "authentication failed" in text or "not configured" in text:
                    self._send(
                        401,
                        json.dumps({"error": text}).encode("utf-8"),
                        "application/json",
                        {"WWW-Authenticate": f'Bearer resource_metadata="{self._metadata_url()}"'},
                    )
                    return
                self._send_jsonrpc_error(message, -32000, text)
            else:
                if not responses:
                    self._send(202, b"", "text/plain")
                    return
                headers = {}
                if session.session_id:
                    headers["Mcp-Session-Id"] = session.session_id
                self._send(
                    200,
                    json.dumps(responses[0], separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
                    "application/json",
                    headers,
                )

        def _send_jsonrpc_error(self, request, code: int, message: str) -> None:
            identifier = request.get("id") if isinstance(request, dict) else None
            payload = {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}
            self._send(200, json.dumps(payload).encode("utf-8"), "application/json")

    return ThreadingHTTPServer((endpoint_config.host, endpoint_config.port), Handler)


def serve_http(session: McpHttpSession, config: HttpEndpointConfig | None = None) -> int:
    """Serve until interrupted; returns a process exit code."""

    endpoint_config = config or HttpEndpointConfig()
    server = create_http_endpoint(session, endpoint_config)
    print(
        f"Stitch MCP HTTP endpoint listening at "
        f"http://{endpoint_config.host}:{server.server_port}/mcp"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
