"""Secret-safe local upload and atomic Stitch asset export tools."""

from __future__ import annotations

import base64
import hashlib
import html
import http.client
import ipaddress
import json
import os
import re
import shutil
import stat
import tempfile
import urllib.error
import urllib.request
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit


UPLOAD_ORIGIN = "https://stitch.googleapis.com"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
MAX_EXPORT_BYTES = 100 * 1024 * 1024
MAX_SCREENS = 100
MAX_EXPORT_FILES = 500
MAX_REFERENCED_URLS = 500
UPLOAD_MIMES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".html": "text/html", ".htm": "text/html",
}
DOWNLOAD_MIMES = {
    "text/html": ".html", "text/markdown": ".md", "text/css": ".css",
    "application/javascript": ".js", "text/javascript": ".js",
    "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
    "image/svg+xml": ".svg", "font/woff": ".woff", "font/woff2": ".woff2",
}
# Registrable domains owned by Google that serve Stitch artifacts. `withgoogle.com`
# is Stitch's own web domain (stitch.withgoogle.com); the other four cover the FIFE
# image hosts, the API host, and the static asset host observed in live responses.
ALLOWED_DOWNLOAD_HOSTS = ("googleusercontent.com", "googleapis.com", "google.com", "gstatic.com", "withgoogle.com")
PROJECT_PATTERN = re.compile(r"^[0-9]+$")
SCREEN_PATTERN = re.compile(r"^projects/([0-9]+)/screens/([A-Za-z0-9_-]{1,128})$")
REFERENCE_URL_PATTERN = re.compile(r'''(?:src|href)=["'](https://[^"']+)["']''', re.IGNORECASE)


class AssetError(ValueError):
    """A local asset request is unsafe or has an ambiguous remote result."""


class AssetLimitError(AssetError):
    """An asset violates a byte limit that best-effort mode must not relax."""


class UnknownAssetWriteResult(AssetError):
    """A local upload may have reached Stitch without a definitive response."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _secure_transport(request, *, timeout=120):
    return urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout)


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def local_tool_definitions() -> list[dict[str, Any]]:
    """Return complete MCP metadata for the two non-provider local tools."""

    upload_output = _schema({"screens": {"type": "array", "items": _schema({"name": {"type": "string"}}, ["name"])}}, ["screens"])
    download_output = _schema({
        "outputDir": {"type": "string"}, "count": {"type": "integer"},
        "files": {"type": "array", "items": _schema({
            "path": {"type": "string"}, "sha256": {"type": "string"},
            "mime": {"type": "string"}, "size": {"type": "integer"},
        }, ["path", "sha256", "mime", "size"])},
        "warnings": {"type": "array", "items": _schema({
            "kind": {"type": "string"}, "host": {"type": "string"},
            "reason": {"type": "string"},
        }, ["kind", "host", "reason"])},
    }, ["outputDir", "count", "files", "warnings"])
    return [
        {
            "name": "stitch_local_upload_asset",
            "description": "Upload one reviewed local HTML or image file without placing base64 in model output.",
            "inputSchema": _schema({
                "projectId": {"type": "string", "pattern": "^[0-9]+$"},
                "filePath": {"type": "string"}, "title": {"type": "string"},
                "createScreenInstances": {"type": "boolean", "default": False},
            }, ["projectId", "filePath"]),
            "outputSchema": upload_output,
            "annotations": {"readOnlyHint": False, "openWorldHint": True, "idempotentHint": False, "destructiveHint": False},
        },
        {
            "name": "stitch_local_download_assets",
            "description": "Read Stitch screen metadata and atomically export validated project assets.",
            "inputSchema": _schema({
                "projectId": {"type": "string", "pattern": "^[0-9]+$"},
                "outputDir": {"type": "string"},
                "assetsSubdir": {"type": "string", "default": "assets"},
                "referencedAssetPolicy": {
                    "type": "string",
                    "enum": ["best_effort", "strict"],
                    "default": "best_effort",
                },
                "screenNames": {
                    "type": "array",
                    "items": {"type": "string", "pattern": r"^projects/[0-9]+/screens/[A-Za-z0-9_-]{1,128}$"},
                    "minItems": 1,
                    "maxItems": MAX_SCREENS,
                    "uniqueItems": True,
                },
            }, ["projectId", "outputDir"]),
            "outputSchema": download_output,
            "annotations": {"readOnlyHint": False, "openWorldHint": True, "idempotentHint": False, "destructiveHint": False},
        },
    ]


def _validate_project(project_id: str) -> None:
    if not isinstance(project_id, str) or PROJECT_PATTERN.fullmatch(project_id) is None:
        raise AssetError("projectId must be a bare numeric string")


def _safe_subdir(value: str) -> Path:
    windows = PureWindowsPath(value)
    path = Path(value)
    if not value or "\\" in value or windows.is_absolute() or windows.drive or path.is_absolute() or ".." in path.parts:
        raise AssetError("assetsSubdir must be a contained relative path")
    return path


def _read_limited(response, limit: int) -> bytes:
    declared = response.headers.get("Content-Length")
    if declared is not None:
        try:
            declared_size = int(declared)
        except ValueError as error:
            raise AssetLimitError("download Content-Length is invalid") from error
        if declared_size < 0 or declared_size > limit:
            raise AssetLimitError("download exceeds maximum size")
    body = response.read(limit + 1)
    if len(body) > limit:
        raise AssetLimitError("download exceeds maximum size")
    return body


def _download_url_allowed(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and not parsed.username and not parsed.password and any(
        host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_DOWNLOAD_HOSTS
    )


def _referenced_url_allowed(url: str) -> bool:
    """Allow public HTTPS HTML dependencies without a finite CDN allowlist."""

    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or parsed.username or parsed.password or not host:
        return False
    if parsed.port not in {None, 443}:
        return False
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return "." in host
    return False


def _rejected_url_reason(url: str) -> str:
    """Describe a rejected URL by host only.

    Download URLs carry signatures and must never be echoed, but a bare
    "not allowlisted" message leaves the operator unable to tell which host was
    refused. The hostname is what the allowlist decision turns on, so report it.
    """

    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower() or "unparseable"
    return f"host {host!r} (scheme {parsed.scheme or 'none'!r})"


def _read_regular_file(path: Path, limit: int) -> bytes:
    """Read one absolute non-symlink file through the descriptor that was checked."""

    current = path
    while current != current.parent:
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                raise AssetError("filePath must not contain a symlink component")
        except FileNotFoundError as error:
            raise AssetError("filePath must identify an existing regular file") from error
        current = current.parent
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    directory_descriptor: int | None = None
    try:
        supports_safe_walk = (
            hasattr(os, "O_DIRECTORY")
            and hasattr(os, "O_NOFOLLOW")
            and os.open in os.supports_dir_fd
        )
        if supports_safe_walk:
            directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                directory_flags |= os.O_CLOEXEC
            directory_descriptor = os.open(path.anchor, directory_flags)
            for component in path.parts[1:-1]:
                next_descriptor = os.open(component, directory_flags, dir_fd=directory_descriptor)
                os.close(directory_descriptor)
                directory_descriptor = next_descriptor
            descriptor = os.open(path.name, flags, dir_fd=directory_descriptor)
        else:
            descriptor = os.open(path, flags)
    except OSError as error:
        raise AssetError("filePath could not be opened safely") from error
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise AssetError("filePath must be a regular file")
        if metadata.st_size < 1 or metadata.st_size > limit:
            raise AssetError("upload file size is outside the allowed range")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) != metadata.st_size or len(data) > limit:
            raise AssetError("upload file changed while it was being read")
        return data
    finally:
        os.close(descriptor)


def _validate_file_content(mime: str, body: bytes, *, upload: bool = False) -> None:
    if mime == "image/png" and not body.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AssetError("file content does not match PNG type")
    if mime == "image/jpeg" and not body.startswith(b"\xff\xd8\xff"):
        raise AssetError("file content does not match JPEG type")
    if mime == "image/webp" and not (body.startswith(b"RIFF") and body[8:12] == b"WEBP"):
        raise AssetError("file content does not match WEBP type")
    if mime == "image/svg+xml":
        try:
            svg = body.decode("utf-8").lstrip("\ufeff\t\r\n ")
        except UnicodeDecodeError as error:
            raise AssetError("file content does not match SVG type") from error
        if not (svg.startswith("<svg") or (svg.startswith("<?xml") and "<svg" in svg[:1024])):
            raise AssetError("file content does not match SVG type")
    if upload and mime == "text/html":
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise AssetError("HTML upload must be valid UTF-8") from error
        if "<" not in text or ">" not in text:
            raise AssetError("file content does not look like HTML")


class LocalAssetManager:
    """Execute local virtual tools with injected transports for offline tests."""

    def __init__(
        self,
        secret_provider: Callable[[], str],
        transport: Callable[..., Any] = _secure_transport,
        auth_headers_provider: Callable[[], dict[str, str]] | None = None,
    ):
        self.secret_provider = secret_provider
        self.transport = transport
        self.auth_headers_provider = auth_headers_provider

    def _upload_headers(self) -> dict[str, str]:
        if self.auth_headers_provider is not None:
            return {"Content-Type": "application/json", **self.auth_headers_provider()}
        secret = self.secret_provider()
        if not secret:
            raise AssetError("Stitch credential is not configured")
        return {"Content-Type": "application/json", "X-Goog-Api-Key": secret}

    def upload_asset(self, project_id: str, file_path: Path, *, title: str | None = None, create_screen_instances: bool = False) -> dict[str, Any]:
        _validate_project(project_id)
        path = Path(file_path)
        if not path.is_absolute():
            raise AssetError("filePath must be an absolute path")
        mime = UPLOAD_MIMES.get(path.suffix.lower())
        if mime is None:
            raise AssetError("unsupported upload file type")
        if title is not None and (not isinstance(title, str) or not title.strip() or len(title) > 256):
            raise AssetError("title must be a non-empty string up to 256 characters")
        if not isinstance(create_screen_instances, bool):
            raise AssetError("createScreenInstances must be boolean")
        raw = _read_regular_file(path, MAX_UPLOAD_BYTES)
        _validate_file_content(mime, raw, upload=True)
        file_object = {"fileContentBase64": base64.b64encode(raw).decode("ascii"), "mimeType": mime}
        screen = {"screenType": "DOCUMENT" if mime == "text/html" else "IMAGE", "isCreatedByClient": True}
        screen["htmlCode" if mime == "text/html" else "screenshot"] = file_object
        if mime == "text/html":
            screen["generatedBy"] = "StitchLocalAssetTool"
        if title:
            screen["title"] = title
        payload = {"parent": f"projects/{project_id}", "requests": [{"screen": screen}], "createScreenInstances": bool(create_screen_instances)}
        request = urllib.request.Request(
            f"{UPLOAD_ORIGIN}/v1/projects/{project_id}/screens:batchCreate",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=self._upload_headers(), method="POST",
        )
        try:
            with self.transport(request, timeout=120) as response:
                status_code = getattr(response, "status", 200)
                if status_code == 408 or 500 <= status_code <= 599:
                    raise UnknownAssetWriteResult("upload result is unknown; reconcile with read tools before retrying")
                if status_code != 200:
                    raise AssetError(f"upload returned HTTP {status_code}")
                if response.headers.get_content_type().lower() != "application/json":
                    raise UnknownAssetWriteResult("upload result is unknown; reconcile with read tools before retrying")
                try:
                    response_body = _read_limited(response, 1024 * 1024)
                except AssetError as error:
                    raise UnknownAssetWriteResult("upload result is unknown; reconcile with read tools before retrying") from error
                result = json.loads(response_body.decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 408 or 500 <= error.code <= 599:
                raise UnknownAssetWriteResult("upload result is unknown; reconcile with read tools before retrying") from error
            raise AssetError(f"upload returned HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError, OSError, http.client.IncompleteRead, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise UnknownAssetWriteResult("upload result is unknown; reconcile with read tools before retrying") from error
        results = result.get("results") if isinstance(result, dict) else None
        if not isinstance(results, list) or not results or len(results) > MAX_SCREENS:
            raise UnknownAssetWriteResult("upload result is unknown; reconcile with read tools before retrying")
        names: list[dict[str, str]] = []
        seen_names: set[str] = set()
        for item in results:
            name = item.get("screen", {}).get("name") if isinstance(item, dict) else None
            match = SCREEN_PATTERN.fullmatch(name) if isinstance(name, str) else None
            if match is None or match.group(1) != project_id:
                raise UnknownAssetWriteResult("upload result is unknown; reconcile with read tools before retrying")
            if name in seen_names:
                raise UnknownAssetWriteResult("upload result is unknown; reconcile with read tools before retrying")
            seen_names.add(name)
            names.append({"name": name})
        return {"screens": names}

    def download_assets(
        self,
        project_id: str,
        output_dir: Path,
        *,
        assets_subdir: str = "assets",
        screens: Iterable[dict[str, Any]],
        referenced_asset_policy: str = "best_effort",
    ) -> dict[str, Any]:
        _validate_project(project_id)
        if referenced_asset_policy not in {"best_effort", "strict"}:
            raise AssetError("referencedAssetPolicy must be best_effort or strict")
        relative_root = _safe_subdir(assets_subdir)
        output_path = Path(output_dir)
        if not output_path.is_absolute():
            raise AssetError("outputDir must be an absolute path")
        output = output_path.resolve()
        destination = output / relative_root
        try:
            destination.resolve(strict=False).relative_to(output)
        except ValueError as error:
            raise AssetError("output path must be contained under outputDir") from error
        if destination.exists():
            raise AssetError("asset destination already exists")
        materialized_screens = list(screens)
        if len(materialized_screens) > MAX_SCREENS:
            raise AssetError(f"asset export supports at most {MAX_SCREENS} screens")
        output.mkdir(mode=0o700, parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".stitch-assets-", dir=output))
        records: list[dict[str, Any]] = []
        warnings: list[dict[str, str]] = []
        total = 0
        referenced_urls: list[str] = []

        def require_file_capacity(additional: int = 1) -> None:
            if len(records) + additional > MAX_EXPORT_FILES:
                raise AssetError(f"asset export supports at most {MAX_EXPORT_FILES} files")

        try:
            for index, screen in enumerate(materialized_screens):
                if not isinstance(screen, dict):
                    raise AssetError("screen metadata must be an object")
                name = screen.get("name")
                match = SCREEN_PATTERN.fullmatch(name) if isinstance(name, str) else None
                if match is None or match.group(1) != project_id:
                    raise AssetError("screen metadata does not belong to projectId")
                screen_id = match.group(2).lower()
                for field, stem in (("htmlCode", "screen"), ("screenshot", "screenshot"), ("designMd", "DESIGN")):
                    resource = screen.get(field)
                    url = resource.get("downloadUrl") if isinstance(resource, dict) else None
                    if url is None:
                        continue
                    if not isinstance(url, str) or not _download_url_allowed(url):
                        raise AssetError(
                            "download URL must use HTTPS on an allowlisted Google host; "
                            f"rejected {_rejected_url_reason(url)}"
                        )
                    request = urllib.request.Request(url, headers={"Accept": "*/*"}, method="GET")
                    try:
                        with self.transport(request, timeout=120) as response:
                            if getattr(response, "status", 200) != 200:
                                raise AssetError(f"download returned HTTP {response.status}")
                            mime = response.headers.get_content_type().lower()
                            extension = DOWNLOAD_MIMES.get(mime)
                            if extension is None:
                                raise AssetError("download Content-Type is not allowed")
                            body = _read_limited(response, MAX_DOWNLOAD_BYTES)
                            _validate_file_content(mime, body)
                    except (urllib.error.URLError, OSError) as error:
                        raise AssetError("asset download failed") from error
                    total += len(body)
                    if total > MAX_EXPORT_BYTES:
                        raise AssetError("asset export exceeds maximum total size")
                    filename = f"{index + 1:03d}-{screen_id}-{stem}{extension}"
                    staged = stage / filename
                    descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(body)
                        stream.flush()
                        os.fsync(stream.fileno())
                    require_file_capacity()
                    records.append({"path": (relative_root / filename).as_posix(), "sha256": hashlib.sha256(body).hexdigest(), "mime": mime, "size": len(body)})
                    if mime == "text/html":
                        try:
                            html_text = body.decode("utf-8")
                        except UnicodeDecodeError as error:
                            raise AssetError("downloaded HTML is not valid UTF-8") from error
                        for reference in REFERENCE_URL_PATTERN.findall(html_text):
                            reference = html.unescape(reference)
                            if reference not in referenced_urls:
                                if len(referenced_urls) >= MAX_REFERENCED_URLS:
                                    raise AssetError(
                                        f"asset export supports at most {MAX_REFERENCED_URLS} referenced URLs"
                                    )
                                referenced_urls.append(reference)
            for index, url in enumerate(referenced_urls):
                if not _referenced_url_allowed(url):
                    raise AssetError(
                        "referenced asset URL must use safe public HTTPS; "
                        f"rejected {_rejected_url_reason(url)}"
                    )
                request = urllib.request.Request(url, headers={"Accept": "*/*"}, method="GET")
                try:
                    with self.transport(request, timeout=120) as response:
                        if getattr(response, "status", 200) != 200:
                            raise AssetError(f"referenced asset returned HTTP {response.status}")
                        mime = response.headers.get_content_type().lower()
                        extension = DOWNLOAD_MIMES.get(mime)
                        if extension is None or mime == "text/html":
                            raise AssetError("referenced asset Content-Type is not allowed")
                        body = _read_limited(response, MAX_DOWNLOAD_BYTES)
                        _validate_file_content(mime, body)
                except AssetLimitError:
                    raise
                except (urllib.error.URLError, OSError, AssetError) as error:
                    if referenced_asset_policy == "strict":
                        if isinstance(error, AssetError):
                            raise
                        raise AssetError("referenced asset download failed") from error
                    warnings.append({
                        "kind": "referenced_asset_skipped",
                        "host": (urlsplit(url).hostname or "unparseable").lower(),
                        "reason": str(error) if isinstance(error, AssetError) else "download failed",
                    })
                    continue
                total += len(body)
                if total > MAX_EXPORT_BYTES:
                    raise AssetError("asset export exceeds maximum total size")
                filename = f"referenced-{index + 1:03d}{extension}"
                staged = stage / filename
                descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(body)
                    stream.flush()
                    os.fsync(stream.fileno())
                require_file_capacity()
                records.append({"path": (relative_root / filename).as_posix(), "sha256": hashlib.sha256(body).hexdigest(), "mime": mime, "size": len(body)})
            destination.parent.mkdir(parents=True, exist_ok=True)
            stage.replace(destination)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        return {
            "outputDir": str(output),
            "count": len(records),
            "files": records,
            "warnings": warnings,
        }
