"""Typed, secret-rejecting evidence builders for external Harness actions."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from .storage import sha256_file


SENSITIVE_KEYS = {"authorization", "cookie", "headers", "api_key", "apikey", "token", "signed_url", "base64"}


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in SENSITIVE_KEYS or any(part in normalized for part in ("password", "secret")):
                raise ValueError("evidence metadata contains a sensitive field")
            _reject_sensitive(child)
    elif isinstance(value, list):
        for child in value:
            _reject_sensitive(child)
    elif isinstance(value, str) and value.startswith(("https://", "http://")):
        parsed = urlsplit(value)
        if parsed.query or parsed.fragment:
            raise ValueError("evidence remote URL must not contain a query or fragment")


class EvidenceWriter:
    """Build normalized evidence from files already stored beneath one run."""

    def __init__(self, run_root: Path):
        self.run_root = Path(run_root).resolve()

    def _artifact(self, path: Path, mime: str | None = None, *, width: int | None = None, height: int | None = None, semantic_role: str | None = None) -> dict[str, Any]:
        resolved = Path(path).resolve()
        try:
            relative = resolved.relative_to(self.run_root)
        except ValueError as error:
            raise ValueError("evidence artifact must stay beneath the run") from error
        if not resolved.is_file() or resolved.is_symlink():
            raise ValueError("evidence artifact must be a regular file")
        guessed = mime or {
            ".html": "text/html", ".htm": "text/html", ".png": "image/png",
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".json": "application/json",
        }.get(resolved.suffix.lower(), "application/octet-stream")
        artifact = {"path": relative.as_posix(), "sha256": sha256_file(resolved), "mime": guessed}
        if width is not None:
            artifact["width"] = width
        if height is not None:
            artifact["height"] = height
        if semantic_role is not None:
            artifact["semantic_role"] = semantic_role
        return artifact

    def _write(self, step: str, tool: str, artifacts: Iterable[Path], result: dict[str, Any], *, sources: Iterable[Path] = (), provider: str = "local-harness", model: str = "deterministic", dimensions: tuple[int, int] | None = None, semantic_roles: Iterable[str] | None = None) -> Path:
        _reject_sensitive(result)
        artifact_paths = tuple(artifacts)
        roles = tuple(semantic_roles) if semantic_roles is not None else (None,) * len(artifact_paths)
        if len(roles) != len(artifact_paths):
            raise ValueError("semantic roles must match evidence artifacts")
        payload = {
            "schema_version": 1, "step": step,
            "provider": {"name": provider, "tool": tool, "model": model},
            "invoked_at": datetime.now(UTC).isoformat(),
            "source_artifacts": [self._artifact(path) for path in sources],
            "artifacts": [
                self._artifact(
                    path,
                    width=dimensions[0] if dimensions and Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} else None,
                    height=dimensions[1] if dimensions and Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} else None,
                    semantic_role=role,
                )
                for path, role in zip(artifact_paths, roles)
            ],
            "result": result,
        }
        evidence_dir = self.run_root / "evidence"
        evidence_dir.mkdir(exist_ok=True)
        destination = evidence_dir / f"{step.replace('.', '-')}.json"
        descriptor, temporary_name = tempfile.mkstemp(dir=evidence_dir, prefix=f".{destination.name}-")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            Path(temporary_name).replace(destination)
        finally:
            Path(temporary_name).unlink(missing_ok=True)
        return destination

    def stitch_generation(self, *, artifact_paths: Iterable[Path], render_metadata: dict[str, Any], provider_resource_ids: Iterable[str] = ()) -> Path:
        return self._write("stitch.generate", "generate_screen_from_text", artifact_paths, {"render_metadata": render_metadata, "provider_resource_ids": list(provider_resource_ids)}, provider="google-stitch", model="server")

    def imagegen(self, *, artifact_paths: Iterable[Path], width: int, height: int, metadata: dict[str, Any] | None = None) -> Path:
        if width < 1 or height < 1:
            raise ValueError("image dimensions must be positive")
        return self._write("imagegen", "imagegen", artifact_paths, metadata or {"status": "generated"}, dimensions=(width, height))

    def ocr(self, *, artifact_paths: Iterable[Path], texts: list[str], metadata: dict[str, Any] | None = None) -> Path:
        result = {"texts": texts, **(metadata or {})}
        return self._write("ocr", "ocr-business-gate", artifact_paths, result)

    def roundtrip(self, *, artifact_paths: Iterable[Path], render_metadata: dict[str, Any]) -> Path:
        return self._write("stitch.roundtrip", "upload-and-readback", artifact_paths, {"render_metadata": render_metadata}, provider="google-stitch", model="server")

    def editability(self, before_html: Path, edited_html: Path, restored_html: Path, before_render: Path, edited_render: Path, restored_render: Path) -> Path:
        paths = (before_html, edited_html, restored_html, before_render, edited_render, restored_render)
        roles = ("before_html", "edited_html", "restored_html", "before_render", "edited_render", "restored_render")
        artifacts = [self._artifact(path, semantic_role=role) for path, role in zip(paths, roles)]
        result = {
            "editable": artifacts[0]["sha256"] != artifacts[1]["sha256"] and artifacts[3]["sha256"] != artifacts[4]["sha256"],
            "restored": artifacts[0]["sha256"] == artifacts[2]["sha256"] and artifacts[3]["sha256"] == artifacts[5]["sha256"],
            "hashes": {
                "before_html": artifacts[0]["sha256"], "edited_html": artifacts[1]["sha256"], "restored_html": artifacts[2]["sha256"],
                "before_render": artifacts[3]["sha256"], "edited_render": artifacts[4]["sha256"], "restored_render": artifacts[5]["sha256"],
            },
        }
        if not result["editable"] or not result["restored"]:
            raise ValueError("editability requires a changed edit and exact restore hash parity")
        return self._write("editability", "edit-restore-probe", paths, result, semantic_roles=roles, provider="google-stitch", model="server")

    def visual_review(self, *, artifact_paths: Iterable[Path], source_artifact_paths: Iterable[Path], layout_score: float, scores: dict[str, Any]) -> Path:
        return self._write("visual-judge", "compare", artifact_paths, {"layout_score": layout_score, "scores": scores}, sources=source_artifact_paths)
