"""Strict envelopes for evidence produced by external design tools."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import sha256_file


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(ValueError):
    """External evidence is incomplete, stale, or unsafe."""


@dataclass(frozen=True)
class EvidenceArtifact:
    path: str
    sha256: str
    mime: str | None = None
    width: int | None = None
    height: int | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceArtifact":
        if not isinstance(payload, dict):
            raise EvidenceError("evidence artifact must be an object")
        path = payload.get("path")
        digest = payload.get("sha256")
        if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise EvidenceError("evidence artifact path must stay beneath the run")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise EvidenceError("evidence artifact requires a lowercase SHA-256")
        mime = payload.get("mime")
        width = payload.get("width")
        height = payload.get("height")
        if mime is not None and not isinstance(mime, str):
            raise EvidenceError("artifact mime must be a string")
        if width is not None and (not isinstance(width, int) or width < 1):
            raise EvidenceError("artifact width must be positive")
        if height is not None and (not isinstance(height, int) or height < 1):
            raise EvidenceError("artifact height must be positive")
        return cls(path, digest, mime, width, height)


@dataclass(frozen=True)
class ExternalEvidence:
    step: str
    provider_name: str
    provider_tool: str
    provider_model: str
    invoked_at: str
    source_artifacts: tuple[EvidenceArtifact, ...]
    artifacts: tuple[EvidenceArtifact, ...]
    result: dict[str, Any]

    @classmethod
    def load(cls, path: Path, expected_step: str) -> "ExternalEvidence":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceError("external evidence is not valid UTF-8 JSON") from error
        return cls.from_dict(payload, expected_step)

    @classmethod
    def from_dict(cls, payload: dict[str, Any], expected_step: str) -> "ExternalEvidence":
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise EvidenceError("external evidence schema_version must be 1")
        step = payload.get("step")
        if step != expected_step:
            raise EvidenceError(f"expected {expected_step} evidence")
        provider = payload.get("provider")
        if not isinstance(provider, dict):
            raise EvidenceError("external evidence requires provider metadata")
        values = [provider.get("name"), provider.get("tool"), provider.get("model")]
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise EvidenceError("provider name, tool, and model are required")
        invoked_at = payload.get("invoked_at")
        if not isinstance(invoked_at, str) or "T" not in invoked_at:
            raise EvidenceError("external evidence requires an invocation timestamp")
        sources_data = payload.get("source_artifacts")
        artifacts_data = payload.get("artifacts")
        if not isinstance(sources_data, list) or not isinstance(artifacts_data, list) or not artifacts_data:
            raise EvidenceError("provider success requires at least one output artifact")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise EvidenceError("external evidence requires a normalized result")
        return cls(
            step,
            values[0],
            values[1],
            values[2],
            invoked_at,
            tuple(EvidenceArtifact.from_dict(item) for item in sources_data),
            tuple(EvidenceArtifact.from_dict(item) for item in artifacts_data),
            result,
        )

    def verify_artifacts(self, run_root: Path) -> tuple[str, ...]:
        errors: list[str] = []
        root = run_root.resolve()
        for artifact in (*self.source_artifacts, *self.artifacts):
            candidate = run_root / artifact.path
            try:
                candidate.resolve().relative_to(root)
            except ValueError:
                errors.append(f"path escape: {artifact.path}")
                continue
            if not candidate.is_file():
                errors.append(f"artifact missing: {artifact.path}")
            elif sha256_file(candidate) != artifact.sha256:
                errors.append(f"artifact hash mismatch: {artifact.path}")
        return tuple(errors)

