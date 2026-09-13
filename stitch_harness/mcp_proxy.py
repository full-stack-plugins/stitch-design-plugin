"""A secret-safe stdio proxy for the Google Stitch Streamable HTTP MCP."""

from __future__ import annotations

import json
import math
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import IO, Iterable
from urllib.parse import urlsplit

from .secrets import SecretProvider, SecretStoreError, platform_secret_provider
from .tool_catalog import ToolCatalog


STITCH_ENDPOINT = "https://stitch.googleapis.com/mcp"
PROTOCOL_VERSION = "2025-06-18"
MIN_REQUEST_TIMEOUT = 1.0
MAX_REQUEST_TIMEOUT = 600.0


class ProxyError(RuntimeError):
    """A sanitized proxy failure safe to return to the MCP client."""


class UnknownWriteResult(ProxyError):
    """A write may have reached Stitch but no definitive response arrived."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _default_opener():
    return urllib.request.build_opener(_NoRedirect())


def _json_messages(payload: bytes) -> list[dict]:
    if not payload.strip():
        return []
    try:
        decoded = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ProxyError("Stitch returned malformed JSON") from error
    if isinstance(decoded, dict):
        return [decoded]
    if isinstance(decoded, list) and all(isinstance(item, dict) for item in decoded):
        return decoded
    raise ProxyError("Stitch returned an invalid JSON-RPC payload")


def _sse_messages(payload: bytes) -> list[dict]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProxyError("Stitch returned malformed SSE") from error
    messages: list[dict] = []
    data_lines: list[str] = []
    for line in [*text.splitlines(), ""]:
        if not line:
            if data_lines:
                messages.extend(_json_messages("\n".join(data_lines).encode("utf-8")))
                data_lines.clear()
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    return messages


@dataclass
class McpHttpSession:
    """One upstream MCP session with controlled authentication refresh."""

    provider: SecretProvider = field(repr=False)
    endpoint: str = STITCH_ENDPOINT
    opener: object | None = field(default=None, repr=False)
    timeout: float = 300.0
    session_id: str | None = None
    tool_catalog: ToolCatalog = field(default_factory=ToolCatalog, repr=False)
    _cached_secret: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        parsed = urlsplit(self.endpoint)
        if self.endpoint != STITCH_ENDPOINT and parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("Stitch endpoint must be the official HTTPS endpoint or loopback")
        if self.endpoint == STITCH_ENDPOINT and parsed.scheme != "https":
            raise ValueError("official Stitch endpoint must use HTTPS")
        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or not math.isfinite(self.timeout)
            or not MIN_REQUEST_TIMEOUT <= self.timeout <= MAX_REQUEST_TIMEOUT
        ):
            raise ValueError(
                f"Stitch timeout must be between {MIN_REQUEST_TIMEOUT:g} and "
                f"{MAX_REQUEST_TIMEOUT:g} seconds"
            )
        self.timeout = float(self.timeout)
        if self.opener is None:
            self.opener = _default_opener()

    def _is_write(self, message: dict) -> bool:
        if message.get("method") != "tools/call":
            return False
        params = message.get("params")
        if not isinstance(params, dict):
            return True
        name = params.get("name")
        if not isinstance(name, str) or not name:
            return True
        return self.tool_catalog.is_write_tool(name)

    def _repair_tool_list(self, request: dict, messages: list[dict]) -> list[dict]:
        if request.get("method") != "tools/list":
            return messages
        params = request.get("params")
        if not isinstance(params, dict) or "cursor" not in params:
            self.tool_catalog.clear()
        for message in messages:
            result = message.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
                continue
            try:
                result["tools"] = self.tool_catalog.extend(result["tools"])
            except ValueError as error:
                raise ProxyError("Stitch returned duplicate tool metadata") from error
        return messages

    def _request(self, message: dict, secret: str):
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "X-Goog-Api-Key": secret,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        body = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")

    def send(self, message: dict) -> list[dict]:
        """Send one MCP message, refreshing authentication at most once."""

        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise ProxyError("invalid JSON-RPC request")
        for auth_attempt in range(2):
            if self._cached_secret is None or auth_attempt > 0:
                try:
                    self._cached_secret = self.provider.get()
                except SecretStoreError as error:
                    raise ProxyError("Stitch credential could not be read") from error
            secret = self._cached_secret
            if not secret:
                raise ProxyError("Stitch credential is not configured")
            request = self._request(message, secret)
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    status = getattr(response, "status", 200)
                    payload = response.read()
                    session_id = response.headers.get("Mcp-Session-Id")
                    if session_id:
                        self.session_id = session_id
                    if status == 202 and not payload:
                        return []
                    content_type = response.headers.get_content_type()
                    if content_type == "text/event-stream":
                        return self._repair_tool_list(message, _sse_messages(payload))
                    return self._repair_tool_list(message, _json_messages(payload))
            except urllib.error.HTTPError as error:
                if error.code == 401 and auth_attempt == 0:
                    error.close()
                    continue
                if error.code == 401:
                    error.close()
                    raise ProxyError("Stitch authentication failed after one credential refresh") from error
                if error.code == 403:
                    error.close()
                    raise ProxyError("Stitch permission denied") from error
                if (error.code == 408 or 500 <= error.code <= 599) and self._is_write(message):
                    error.close()
                    raise UnknownWriteResult(
                        "Stitch write result is unknown; reconcile with read tools before retrying"
                    ) from error
                error.close()
                raise ProxyError(f"Stitch returned HTTP {error.code}") from error
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                if self._is_write(message):
                    raise UnknownWriteResult(
                        "Stitch write result is unknown; reconcile with read tools before retrying"
                    ) from error
                raise ProxyError("Stitch connection failed") from error
        raise ProxyError("Stitch authentication failed")


def _error(identifier, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}


def _write_messages(output_stream: IO[str], messages: Iterable[dict]) -> None:
    for message in messages:
        output_stream.write(json.dumps(message, separators=(",", ":"), ensure_ascii=False) + "\n")
        output_stream.flush()


def serve_stdio(
    input_stream: IO[str] = sys.stdin,
    output_stream: IO[str] = sys.stdout,
    session: McpHttpSession | None = None,
) -> int:
    """Forward newline-delimited JSON-RPC until stdin reaches EOF."""

    active_session = session
    for raw_line in input_stream:
        try:
            message = json.loads(raw_line)
        except json.JSONDecodeError:
            _write_messages(output_stream, [_error(None, -32700, "Parse error")])
            continue
        identifier = message.get("id") if isinstance(message, dict) else None
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "method" not in message:
            _write_messages(output_stream, [_error(identifier, -32600, "Invalid Request")])
            continue
        if active_session is None:
            active_session = McpHttpSession(provider=platform_secret_provider())
        try:
            responses = active_session.send(message)
        except UnknownWriteResult as error:
            _write_messages(output_stream, [_error(identifier, -32001, str(error))])
        except ProxyError as error:
            _write_messages(output_stream, [_error(identifier, -32000, str(error))])
        else:
            _write_messages(output_stream, responses)
    return 0
