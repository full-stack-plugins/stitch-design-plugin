#!/usr/bin/env python3
"""Run one bounded, secret-safe Stitch live canary and clean it up separately."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tarfile
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from stitch_harness.mcp_proxy import McpHttpSession, ProxyError, UnknownWriteResult  # noqa: E402
from stitch_harness.secrets import platform_secret_provider  # noqa: E402
from stitch_harness.storage import sha256_file  # noqa: E402
from stitch_harness.visual_gate import compare_images  # noqa: E402


STAGES = (
    "create_project",
    "generate",
    "read",
    "edit",
    "variant",
    "design_system_create",
    "design_system_update",
    "design_system_list",
    "design_system_apply",
    "upload",
    "download",
    "harness_compare_archive",
)
PROJECT_PATTERN = re.compile(r"^projects/([0-9]+)$")
SCREEN_PATTERN = re.compile(r"^projects/[0-9]+/screens/[A-Fa-f0-9]{32}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PUBLIC_STAGE_KEYS = frozenset(
    {
        "project_created", "screen_generated", "screen_read", "screen_edited",
        "one_variant_generated", "design_system_created", "design_system_updated",
        "design_system_listed", "design_system_applied", "asset_uploaded",
        "assets_downloaded", "comparison_created", "archive_created",
    }
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("canary clock must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _atomic_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def _public_template(started_at: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "release_candidate": "0.6.0",
        "started_at": started_at,
        "finished_at": None,
        "stages": {
            "project_created": False,
            "screen_generated": False,
            "screen_read": False,
            "screen_edited": False,
            "one_variant_generated": False,
            "design_system_created": False,
            "design_system_updated": False,
            "design_system_listed": False,
            "design_system_applied": False,
            "asset_uploaded": False,
            "assets_downloaded": False,
            "comparison_created": False,
            "archive_created": False,
        },
        "counts": {"downloaded_files": 0, "comparison_files": 0},
        "hashes": {"archive_sha256": None},
        "cleanup": {"delete_requested": False, "project_absent": False},
    }


def _validate_public_evidence(payload: dict[str, Any]) -> None:
    expected = {"schema_version", "release_candidate", "started_at", "finished_at", "stages", "counts", "hashes", "cleanup"}
    if set(payload) != expected or payload.get("schema_version") != 1 or payload.get("release_candidate") != "0.6.0":
        raise ValueError("sanitized evidence has an invalid top-level contract")
    if set(payload.get("stages", {})) != PUBLIC_STAGE_KEYS:
        raise ValueError("sanitized evidence has invalid stage fields")
    if set(payload.get("counts", {})) != {"downloaded_files", "comparison_files"}:
        raise ValueError("sanitized evidence has invalid count fields")
    if set(payload.get("cleanup", {})) != {"delete_requested", "project_absent"}:
        raise ValueError("sanitized evidence has invalid cleanup fields")
    for section in ("stages", "cleanup"):
        if not isinstance(payload.get(section), dict) or not all(isinstance(value, bool) for value in payload[section].values()):
            raise ValueError("sanitized evidence status values must be booleans")
    if not isinstance(payload.get("counts"), dict) or not all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in payload["counts"].values()
    ):
        raise ValueError("sanitized evidence counts must be non-negative integers")
    archive_hash = payload.get("hashes", {}).get("archive_sha256")
    if archive_hash is not None and (not isinstance(archive_hash, str) or SHA256_PATTERN.fullmatch(archive_hash) is None):
        raise ValueError("sanitized evidence hashes must be SHA-256 values")
    if set(payload.get("hashes", {})) != {"archive_sha256"}:
        raise ValueError("sanitized evidence contains an unsupported hash field")
    for key in ("started_at", "finished_at"):
        value = payload.get(key)
        if value is not None and (not isinstance(value, str) or not value.endswith("Z")):
            raise ValueError("sanitized evidence timestamps must be UTC strings")


def _write_public_evidence(path: Path, payload: dict[str, Any]) -> None:
    _validate_public_evidence(payload)
    _atomic_private_json(path, payload)


def _structured(messages: list[dict[str, Any]]) -> dict[str, Any]:
    if len(messages) != 1 or not isinstance(messages[0].get("result"), dict):
        raise ProxyError("Stitch returned an invalid canary response")
    result = messages[0]["result"]
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    return result


def _find_string(value: Any, keys: tuple[str, ...], pattern: re.Pattern[str] | None = None) -> str | None:
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and (pattern is None or pattern.fullmatch(candidate)):
                return candidate
        for child in value.values():
            found = _find_string(child, keys, pattern)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_string(child, keys, pattern)
            if found is not None:
                return found
    return None


class StitchBackend:
    """Live MCP backend. Opaque remote identifiers never leave private state."""

    def __init__(self) -> None:
        self.session = McpHttpSession(provider=platform_secret_provider())
        self._ready = False
        self._request_id = 0

    def _send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._request_id += 1
        request: dict[str, Any] = {"jsonrpc": "2.0", "id": f"canary-{self._request_id}", "method": method}
        if params is not None:
            request["params"] = params
        return _structured(self.session.send(request))

    def _ensure_ready(self) -> None:
        if self._ready:
            return
        initialized = self._send(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "stitch-design-live-canary", "version": "0.6.0"},
            },
        )
        if initialized.get("protocolVersion") != "2025-06-18":
            raise ProxyError("Stitch returned an unsupported canary protocol")
        self._send("tools/list", {})
        self._ready = True

    def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self._ensure_ready()
        return self._send("tools/call", {"name": name, "arguments": arguments})

    @staticmethod
    def _selected(context: dict[str, Any]) -> dict[str, str]:
        return {"id": context["screen_id"], "sourceScreen": context["screen_name"]}

    def _refresh_screen(self, context: dict[str, Any]) -> dict[str, str]:
        listed = self._call("list_screens", {"projectId": context["project_id"]})
        screen_name = _find_string(listed.get("screens", listed), ("name", "sourceScreen"), SCREEN_PATTERN)
        screen_id = _find_string(listed.get("screens", listed), ("id",))
        if screen_name is None or screen_id is None:
            raise ProxyError("Stitch did not return a usable screen instance")
        return {"screen_name": screen_name, "screen_id": screen_id}

    def execute(self, stage: str, context: dict[str, Any], workspace: Path) -> dict[str, Any]:
        if stage == "create_project":
            result = self._call("create_project", {"title": context["project_title"]})
            project_name = _find_string(result, ("name",), PROJECT_PATTERN)
            match = PROJECT_PATTERN.fullmatch(project_name or "")
            if match is None:
                raise ProxyError("Stitch did not return a project resource")
            return {"project_name": project_name, "project_id": match.group(1)}
        if stage == "generate":
            self._call(
                "generate_screen_from_text",
                {
                    "projectId": context["project_id"],
                    "prompt": "Create one minimal 390x884 mobile canary screen with a heading, body text, and primary button.",
                },
            )
            return self._refresh_screen(context)
        if stage == "read":
            self._call("get_project", {"name": context["project_name"]})
            self._call("list_screens", {"projectId": context["project_id"]})
            self._call("get_screen", {"name": context["screen_name"]})
            return {"ok": True}
        if stage == "edit":
            self._call("edit_screens", {"selectedScreenInstances": [self._selected(context)]})
            return {"ok": True}
        if stage == "variant":
            result = self._call("generate_variants", {"selectedScreenInstances": [self._selected(context)]})
            screens = result.get("screens")
            if not isinstance(screens, list) or len(screens) != 1:
                raise ProxyError("Stitch canary requires exactly one generated variant")
            return {"ok": True}
        if stage == "design_system_create":
            result = self._call("create_design_system", {"projectId": context["project_id"]})
            asset_id = _find_string(result, ("assetId",))
            if asset_id is None:
                raise ProxyError("Stitch did not return a design-system asset")
            return {"design_system_asset_id": asset_id}
        if stage == "design_system_update":
            self._call("update_design_system", {"assetId": context["design_system_asset_id"]})
            return {"ok": True}
        if stage == "design_system_list":
            result = self._call("list_design_systems", {"projectId": context["project_id"]})
            if not isinstance(result.get("designSystems"), list):
                raise ProxyError("Stitch did not return a design-system list")
            return {"ok": True}
        if stage == "design_system_apply":
            self._call("apply_design_system", {"selectedScreenInstances": [self._selected(context)]})
            return {"ok": True}
        if stage == "upload":
            source = workspace / "canary-upload.html"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("<!doctype html><meta charset=utf-8><title>Canary</title><main>Canary asset</main>\n", encoding="utf-8")
            result = self._call(
                "stitch_local_upload_asset",
                {"projectId": context["project_id"], "filePath": str(source.resolve()), "title": "Canary asset"},
            )
            if not isinstance(result.get("screens"), list):
                raise ProxyError("local upload did not return a screen list")
            return {"ok": True}
        if stage == "download":
            destination = (workspace / "downloaded").resolve()
            result = self._call(
                "stitch_local_download_assets",
                {"projectId": context["project_id"], "outputDir": str(destination)},
            )
            files = result.get("files")
            if not isinstance(files, list) or not files:
                raise ProxyError("local download returned no files")
            hashes = [item.get("sha256") for item in files if isinstance(item, dict)]
            if len(hashes) != len(files) or any(not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None for value in hashes):
                raise ProxyError("local download returned invalid hashes")
            return {"count": len(files), "hashes": hashes}
        if stage == "harness_compare_archive":
            downloaded = workspace / "downloaded"
            candidates = sorted(path for path in downloaded.rglob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})
            pair: tuple[Path, Path] | None = None
            from PIL import Image
            dimensions: dict[tuple[int, int], list[Path]] = {}
            for path in candidates:
                with Image.open(path) as source:
                    dimensions.setdefault(source.size, []).append(path)
            for paths in dimensions.values():
                if len(paths) >= 2:
                    pair = (paths[0], paths[1])
                    break
            if pair is None:
                raise ProxyError("canary comparison requires two same-size downloaded renders")
            comparison = compare_images(pair[0], pair[1], workspace / "comparison")
            archive_path = workspace.parent / "stitch-canary-private.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                archive.add(workspace, arcname="stitch-canary", recursive=True)
            return {"comparison_count": len(comparison.review_files), "archive_sha256": sha256_file(archive_path)}
        raise ValueError(f"unsupported canary stage: {stage}")

    def delete_project(self, context: dict[str, Any]) -> bool:
        result = self._call("delete_project", {"name": context["project_name"]})
        return result.get("deleted") is True

    def project_absent(self, context: dict[str, Any]) -> bool:
        result = self._call("list_projects", {})
        projects = result.get("projects")
        if not isinstance(projects, list):
            raise ProxyError("Stitch did not return a project list during cleanup")
        names = [_find_string(project, ("name",), PROJECT_PATTERN) for project in projects]
        if any(name is None for name in names):
            raise ProxyError("Stitch returned invalid project metadata during cleanup")
        return context["project_name"] not in names


def _mark_stage(evidence: dict[str, Any], stage: str, result: dict[str, Any]) -> None:
    mapping = {
        "create_project": "project_created",
        "generate": "screen_generated",
        "read": "screen_read",
        "edit": "screen_edited",
        "variant": "one_variant_generated",
        "design_system_create": "design_system_created",
        "design_system_update": "design_system_updated",
        "design_system_list": "design_system_listed",
        "design_system_apply": "design_system_applied",
        "upload": "asset_uploaded",
        "download": "assets_downloaded",
    }
    if stage in mapping:
        evidence["stages"][mapping[stage]] = True
    if stage == "download":
        evidence["counts"]["downloaded_files"] = result["count"]
    if stage == "harness_compare_archive":
        evidence["stages"]["comparison_created"] = True
        evidence["stages"]["archive_created"] = True
        evidence["counts"]["comparison_files"] = result["comparison_count"]
        evidence["hashes"]["archive_sha256"] = result["archive_sha256"]


def run_canary(
    backend: Any,
    state_path: Path,
    evidence_path: Path,
    workspace: Path,
    *,
    now: Callable[[], datetime] = _utc_now,
    nonce: str | None = None,
) -> dict[str, Any]:
    """Run every non-cleanup stage, checkpointing opaque values only in private state."""

    started = now()
    unique = (nonce or uuid.uuid4().hex[:12]).lower()
    if re.fullmatch(r"[0-9a-f]{12}", unique) is None:
        raise ValueError("canary nonce must contain exactly 12 lowercase hexadecimal characters")
    compact_time = started.astimezone(UTC).strftime("%Y%m%dt%H%M%Sz").lower()
    context: dict[str, Any] = {
        "schema_version": 1,
        "project_title": f"codex-stitch-canary-{compact_time}-{unique}",
        "workspace": str(Path(workspace).resolve()),
        "delete_attempted": False,
    }
    evidence = _public_template(_timestamp(started))
    _atomic_private_json(Path(state_path), context)
    _write_public_evidence(Path(evidence_path), evidence)
    for stage in STAGES:
        result = backend.execute(stage, context, Path(workspace).resolve())
        if not isinstance(result, dict):
            raise ValueError("canary backend result must be an object")
        context.update(result)
        context["last_completed_stage"] = stage
        _atomic_private_json(Path(state_path), context)
        _mark_stage(evidence, stage, result)
        _write_public_evidence(Path(evidence_path), evidence)
    evidence["finished_at"] = _timestamp(now())
    _write_public_evidence(Path(evidence_path), evidence)
    return evidence


def cleanup_canary(
    backend: Any,
    state_path: Path,
    evidence_path: Path,
    *,
    now: Callable[[], datetime] = _utc_now,
) -> dict[str, Any]:
    """Attempt the remote delete once, then prove absence with a read."""

    state = json.loads(Path(state_path).read_text(encoding="utf-8"))
    evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    if not state.get("project_name"):
        evidence["cleanup"]["project_absent"] = True
    else:
        if not state.get("delete_attempted", False):
            state["delete_attempted"] = True
            _atomic_private_json(Path(state_path), state)
            evidence["cleanup"]["delete_requested"] = True
            _write_public_evidence(Path(evidence_path), evidence)
            backend.delete_project(state)
        else:
            evidence["cleanup"]["delete_requested"] = True
        evidence["cleanup"]["project_absent"] = bool(backend.project_absent(state))
    evidence["finished_at"] = _timestamp(now())
    _write_public_evidence(Path(evidence_path), evidence)
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or clean up one Stitch Design live canary")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "cleanup", "verify-evidence"):
        child = commands.add_parser(name)
        child.add_argument("--state", required=name != "verify-evidence", type=Path)
        child.add_argument("--evidence", required=True, type=Path)
        if name == "run":
            child.add_argument("--workspace", required=True, type=Path)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        if args.command == "verify-evidence":
            _validate_public_evidence(json.loads(args.evidence.read_text(encoding="utf-8")))
            print("sanitized canary evidence contract passed")
            return 0
        backend = StitchBackend()
        if args.command == "run":
            evidence = run_canary(backend, args.state, args.evidence, args.workspace)
        else:
            evidence = cleanup_canary(backend, args.state, args.evidence)
        print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
        if args.command == "cleanup" and not evidence["cleanup"]["project_absent"]:
            return 2
        return 0
    except (OSError, ValueError, ProxyError, UnknownWriteResult, json.JSONDecodeError) as error:
        print(f"live canary {args.command} failed safely: {type(error).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
