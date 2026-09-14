"""A secret-safe stdio proxy for the Google Stitch Streamable HTTP MCP."""

from __future__ import annotations

import http.client
import json
import math
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Iterable
from urllib.parse import urlsplit

from .secrets import SecretProvider, SecretStoreError, platform_secret_provider
from .tool_catalog import ToolCatalog
from .assets import AssetError, LocalAssetManager, SCREEN_PATTERN, UnknownAssetWriteResult, local_tool_definitions


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
    asset_transport: object | None = field(default=None, repr=False)
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
                tools = list(result["tools"])
                if not isinstance(params, dict) or "cursor" not in params:
                    tools.extend(local_tool_definitions())
                result["tools"] = self.tool_catalog.extend(tools)
            except ValueError as error:
                raise ProxyError("Stitch returned duplicate tool metadata") from error
        return messages

    @staticmethod
    def _structured_result(messages: list[dict]) -> dict:
        if len(messages) != 1 or not isinstance(messages[0].get("result"), dict):
            raise AssetError("provider read returned an invalid MCP result")
        result = messages[0]["result"]
        structured = result.get("structuredContent")
        return structured if isinstance(structured, dict) else result

    def _read_project_screens(self, project_id: str, screen_names: list[str] | None = None) -> list[dict]:
        if screen_names is not None:
            if not screen_names or len(screen_names) > 100 or len(set(screen_names)) != len(screen_names):
                raise AssetError("screenNames must contain 1 to 100 unique screen resources")
            summaries = [{"name": name} for name in screen_names]
        else:
            listed = self._structured_result(self.send({
                "jsonrpc": "2.0", "id": "local-list-screens", "method": "tools/call",
                "params": {"name": "list_screens", "arguments": {"projectId": project_id}},
            }))
            summaries = listed.get("screens")
            if not isinstance(summaries, list):
                raise AssetError("list_screens did not return a screen list; pass verified screenNames")
        screens: list[dict] = []
        for summary in summaries:
            name = summary.get("name") if isinstance(summary, dict) else None
            match = SCREEN_PATTERN.fullmatch(name) if isinstance(name, str) else None
            if match is None or match.group(1) != project_id:
                raise AssetError("list_screens returned an invalid screen name")
            detail = self._structured_result(self.send({
                "jsonrpc": "2.0", "id": "local-get-screen", "method": "tools/call",
                "params": {"name": "get_screen", "arguments": {"name": name}},
            }))
            screen = detail.get("screen", detail)
            if not isinstance(screen, dict):
                raise AssetError("get_screen did not return screen metadata")
            screens.append(screen)
        return screens

    def _local_tool_call(self, message: dict) -> list[dict] | None:
        if message.get("method") != "tools/call" or not isinstance(message.get("params"), dict):
            return None
        params = message["params"]
        name = params.get("name")
        if name not in {"stitch_local_upload_asset", "stitch_local_download_assets"}:
            return None
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            raise ProxyError("local tool arguments must be an object")
        allowed = {
            "stitch_local_upload_asset": {"projectId", "filePath", "title", "createScreenInstances"},
            "stitch_local_download_assets": {"projectId", "outputDir", "assetsSubdir", "screenNames"},
        }[name]
        if set(arguments).difference(allowed):
            raise ProxyError("local tool arguments contain unsupported fields")
        transport = self.asset_transport
        manager = LocalAssetManager(
            secret_provider=lambda: self.provider.get(),
            **({"transport": transport} if transport is not None else {}),
        )
        try:
            if name == "stitch_local_upload_asset":
                if not isinstance(arguments.get("projectId"), str) or not isinstance(arguments.get("filePath"), str):
                    raise AssetError("projectId and filePath must be strings")
                result = manager.upload_asset(
                    arguments.get("projectId"), Path(arguments.get("filePath", "")),
                    title=arguments.get("title"),
                    create_screen_instances=arguments.get("createScreenInstances", False),
                )
            else:
                project_id = arguments.get("projectId")
                if not isinstance(project_id, str) or not isinstance(arguments.get("outputDir"), str):
                    raise AssetError("projectId and outputDir must be strings")
                if "assetsSubdir" in arguments and not isinstance(arguments["assetsSubdir"], str):
                    raise AssetError("assetsSubdir must be a string")
                if "screenNames" in arguments and not isinstance(arguments["screenNames"], list):
                    raise AssetError("screenNames must be an array")
                result = manager.download_assets(
                    project_id, Path(arguments.get("outputDir", "")),
                    assets_subdir=arguments.get("assetsSubdir", "assets"),
                    screens=self._read_project_screens(project_id, arguments.get("screenNames")),
                )
        except UnknownAssetWriteResult as error:
            raise UnknownWriteResult(str(error)) from error
        except (AssetError, SecretStoreError) as error:
            raise ProxyError(str(error)) from error
        if "id" not in message:
            return []
        return [{
            "jsonrpc": "2.0", "id": message.get("id"),
            "result": {"content": [{"type": "text", "text": json.dumps(result, separators=(",", ":"))}], "structuredContent": result},
        }]

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
        local = self._local_tool_call(message)
        if local is not None:
            return local
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
            except http.client.IncompleteRead as error:
                if self._is_write(message):
                    raise UnknownWriteResult(
                        "Stitch write result is unknown; reconcile with read tools before retrying"
                    ) from error
                raise ProxyError("Stitch returned a truncated response") from error
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
        has_identifier = isinstance(message, dict) and "id" in message
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "method" not in message:
            _write_messages(output_stream, [_error(identifier, -32600, "Invalid Request")])
            continue
        if active_session is None:
            active_session = McpHttpSession(provider=platform_secret_provider())
        try:
            responses = active_session.send(message)
        except UnknownWriteResult as error:
            if has_identifier:
                _write_messages(output_stream, [_error(identifier, -32001, str(error))])
        except ProxyError as error:
            if has_identifier:
                _write_messages(output_stream, [_error(identifier, -32000, str(error))])
        else:
            if has_identifier:
                _write_messages(output_stream, responses)
    return 0
