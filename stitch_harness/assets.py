"""Secret-safe local upload and atomic Stitch asset export tools."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import shutil
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
ALLOWED_DOWNLOAD_HOSTS = ("googleusercontent.com", "googleapis.com", "google.com", "gstatic.com")
PROJECT_PATTERN = re.compile(r"^[0-9]+$")
SCREEN_PATTERN = re.compile(r"^projects/([0-9]+)/screens/([A-Fa-f0-9]{32})$")
REFERENCE_URL_PATTERN = re.compile(r'''(?:src|href)=["'](https://[^"']+)["']''', re.IGNORECASE)


class AssetError(ValueError):
    """A local asset request is unsafe or has an ambiguous remote result."""


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
    }, ["outputDir", "count", "files"])
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
            }, ["projectId", "outputDir"]),
            "outputSchema": download_output,
            "annotations": {"readOnlyHint": True, "openWorldHint": True, "idempotentHint": True, "destructiveHint": False},
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
            if declared_size < 0 or declared_size > limit:
                raise AssetError("download exceeds maximum size")
        except ValueError as error:
            raise AssetError("download Content-Length is invalid") from error
    try:
        body = response.read(limit + 1)
    except TypeError:
        body = response.read()
    if len(body) > limit:
        raise AssetError("download exceeds maximum size")
    return body


def _download_url_allowed(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and not parsed.username and not parsed.password and any(
        host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_DOWNLOAD_HOSTS
    )


class LocalAssetManager:
    """Execute local virtual tools with injected transports for offline tests."""

    def __init__(self, secret_provider: Callable[[], str], transport: Callable[..., Any] = _secure_transport):
        self.secret_provider = secret_provider
        self.transport = transport

    def upload_asset(self, project_id: str, file_path: Path, *, title: str | None = None, create_screen_instances: bool = False) -> dict[str, Any]:
        _validate_project(project_id)
        path = Path(file_path)
        if not path.is_absolute():
            raise AssetError("filePath must be an absolute path")
        if path.is_symlink() or not path.is_file():
            raise AssetError("filePath must be a regular file and not a symlink")
        mime = UPLOAD_MIMES.get(path.suffix.lower())
        if mime is None:
            raise AssetError("unsupported upload file type")
        size = path.stat().st_size
        if size < 1 or size > MAX_UPLOAD_BYTES:
            raise AssetError("upload file size is outside the allowed range")
        if title is not None and (not isinstance(title, str) or not title.strip() or len(title) > 256):
            raise AssetError("title must be a non-empty string up to 256 characters")
        if not isinstance(create_screen_instances, bool):
            raise AssetError("createScreenInstances must be boolean")
        raw = path.read_bytes()
        if mime == "image/png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise AssetError("upload content does not match PNG type")
        if mime == "image/jpeg" and not raw.startswith(b"\xff\xd8\xff"):
            raise AssetError("upload content does not match JPEG type")
        if mime == "image/webp" and not (raw.startswith(b"RIFF") and raw[8:12] == b"WEBP"):
            raise AssetError("upload content does not match WEBP type")
        secret = self.secret_provider()
        if not secret:
            raise AssetError("Stitch credential is not configured")
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
            headers={"Content-Type": "application/json", "X-Goog-Api-Key": secret}, method="POST",
        )
        try:
            with self.transport(request, timeout=120) as response:
                if getattr(response, "status", 200) != 200:
                    raise AssetError(f"upload returned HTTP {response.status}")
                result = json.loads(_read_limited(response, 1024 * 1024).decode("utf-8"))
        except (urllib.error.URLError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AssetError("upload result is unknown; reconcile with read tools before retrying") from error
        results = result.get("results") if isinstance(result, dict) else None
        if not isinstance(results, list) or not results:
            raise AssetError("upload result is unknown; reconcile with read tools before retrying")
        names: list[dict[str, str]] = []
        for item in results:
            name = item.get("screen", {}).get("name") if isinstance(item, dict) else None
            match = SCREEN_PATTERN.fullmatch(name) if isinstance(name, str) else None
            if match is None or match.group(1) != project_id:
                raise AssetError("upload result is unknown; reconcile with read tools before retrying")
            names.append({"name": name})
        return {"screens": names}

    def download_assets(self, project_id: str, output_dir: Path, *, assets_subdir: str = "assets", screens: Iterable[dict[str, Any]]) -> dict[str, Any]:
        _validate_project(project_id)
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
        output.mkdir(mode=0o700, parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".stitch-assets-", dir=output))
        records: list[dict[str, Any]] = []
        total = 0
        referenced_urls: list[str] = []
        try:
            for index, screen in enumerate(screens):
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
                        raise AssetError("download URL must use HTTPS on an allowlisted Google host")
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
                    records.append({"path": (relative_root / filename).as_posix(), "sha256": hashlib.sha256(body).hexdigest(), "mime": mime, "size": len(body)})
                    if mime == "text/html":
                        try:
                            html_text = body.decode("utf-8")
                        except UnicodeDecodeError as error:
                            raise AssetError("downloaded HTML is not valid UTF-8") from error
                        for reference in REFERENCE_URL_PATTERN.findall(html_text):
                            reference = html.unescape(reference)
                            if reference not in referenced_urls:
                                referenced_urls.append(reference)
            for index, url in enumerate(referenced_urls):
                if not _download_url_allowed(url):
                    raise AssetError("referenced asset URL must use HTTPS on an allowlisted Google host")
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
                except (urllib.error.URLError, OSError) as error:
                    raise AssetError("referenced asset download failed") from error
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
                records.append({"path": (relative_root / filename).as_posix(), "sha256": hashlib.sha256(body).hexdigest(), "mime": mime, "size": len(body)})
            destination.parent.mkdir(parents=True, exist_ok=True)
            stage.replace(destination)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        return {"outputDir": str(output), "count": len(records), "files": records}
