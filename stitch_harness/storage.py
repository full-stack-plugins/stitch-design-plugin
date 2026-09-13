"""Atomic run storage and tamper-evident receipt chaining."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .contracts import PageSpec
from .state import RunState, transition


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _contained_relative(root: Path, path: Path) -> str:
    root_resolved = root.resolve()
    path_resolved = path.resolve()
    try:
        relative = path_resolved.relative_to(root_resolved)
    except ValueError as error:
        raise ValueError("artifact must stay inside its run directory") from error
    return relative.as_posix()


@dataclass(frozen=True)
class ArtifactRecord:
    path: str
    sha256: str
    mime: str
    width: int | None = None
    height: int | None = None

    @classmethod
    def from_path(
        cls,
        run_root: Path,
        path: Path,
        mime: str,
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> "ArtifactRecord":
        if not path.is_file():
            raise FileNotFoundError(path)
        return cls(_contained_relative(run_root, path), sha256_file(path), mime, width, height)

    def to_dict(self) -> dict[str, Any]:
        payload = {"path": self.path, "sha256": self.sha256, "mime": self.mime}
        if self.width is not None:
            payload["width"] = self.width
        if self.height is not None:
            payload["height"] = self.height
        return payload


@dataclass(frozen=True)
class Receipt:
    run_id: str
    page_id: str
    step: str
    attempt: int
    result: str
    started_at: str
    ended_at: str
    inputs: tuple[ArtifactRecord, ...] = ()
    outputs: tuple[ArtifactRecord, ...] = ()
    checks: tuple[dict[str, Any], ...] = ()
    provider_resource_ids: tuple[str, ...] = ()
    error: str | None = None
    previous_receipt_sha256: str | None = None

    @classmethod
    def passed(
        cls,
        run_id: str,
        page_id: str,
        step: str,
        *,
        inputs: Iterable[ArtifactRecord] = (),
        outputs: Iterable[ArtifactRecord] = (),
        checks: Iterable[dict[str, Any]] = (),
        attempt: int = 1,
    ) -> "Receipt":
        timestamp = datetime.now(UTC).isoformat()
        return cls(
            run_id,
            page_id,
            step,
            attempt,
            "passed",
            timestamp,
            timestamp,
            tuple(inputs),
            tuple(outputs),
            tuple(checks),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "page_id": self.page_id,
            "step": self.step,
            "attempt": self.attempt,
            "result": self.result,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "checks": list(self.checks),
            "provider_resource_ids": list(self.provider_resource_ids),
            "error": self.error,
            "previous_receipt_sha256": self.previous_receipt_sha256,
        }


@dataclass(frozen=True)
class Run:
    run_id: str
    page_id: str
    path: Path
    state: RunState
    latest_receipt_sha256: str | None = None


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    errors: tuple[str, ...] = ()
    approval_invalidated: bool = False


class RunStore:
    """Create, update, and verify project-local Harness runs."""

    def start(self, project_root: Path, spec: PageSpec, now: datetime) -> Run:
        timestamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"{timestamp}-{spec.page_id}"
        run_path = project_root / ".stitch" / "runs" / run_id
        run_path.mkdir(parents=True, exist_ok=False)
        for child in ("artifacts", "receipts", "comparison"):
            (run_path / child).mkdir()
        _atomic_json(run_path / "spec.json", spec.source)
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "page_id": spec.page_id,
            "state": RunState.DRAFT.value,
            "latest_receipt_sha256": None,
        }
        _atomic_json(run_path / "manifest.json", manifest)
        return Run(run_id, spec.page_id, run_path, RunState.DRAFT)

    def append_receipt(self, run: Run, receipt: Receipt) -> Run:
        if receipt.run_id != run.run_id or receipt.page_id != run.page_id:
            raise ValueError("receipt identity does not match run")
        receipts_dir = run.path / "receipts"
        sequence = len(list(receipts_dir.glob("*.json"))) + 1
        chained = replace(receipt, previous_receipt_sha256=run.latest_receipt_sha256)
        receipt_path = receipts_dir / f"{sequence:03d}-{receipt.step}.json"
        _atomic_json(receipt_path, chained.to_dict())
        receipt_hash = sha256_file(receipt_path)
        manifest_path = run.path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["latest_receipt_sha256"] = receipt_hash
        _atomic_json(manifest_path, manifest)
        return replace(run, latest_receipt_sha256=receipt_hash)

    def load(self, project_root: Path, run_id: str) -> Run:
        if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
            raise ValueError("run_id must not contain a path")
        run_path = project_root / ".stitch" / "runs" / run_id
        manifest_path = run_path / "manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if payload.get("run_id") != run_id:
            raise ValueError("run manifest identity mismatch")
        return Run(
            run_id,
            str(payload["page_id"]),
            run_path,
            RunState(payload["state"]),
            payload.get("latest_receipt_sha256"),
        )

    def update_state(self, run: Run, target: RunState) -> Run:
        next_state = transition(run.state, target)
        manifest_path = run.path / "manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["state"] = next_state.value
        _atomic_json(manifest_path, payload)
        return replace(run, state=next_state)

    def verify_chain(self, run: Run) -> ChainVerification:
        errors: list[str] = []
        previous: str | None = None
        approval_invalidated = False
        receipt_paths = sorted((run.path / "receipts").glob("*.json"))
        for receipt_path in receipt_paths:
            try:
                payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                errors.append(f"invalid receipt: {receipt_path.name}")
                continue
            if payload.get("previous_receipt_sha256") != previous:
                errors.append(f"previous receipt hash mismatch: {receipt_path.name}")
            for direction in ("inputs", "outputs"):
                for item in payload.get(direction, []):
                    relative = Path(str(item.get("path", "")))
                    candidate = run.path / relative
                    try:
                        _contained_relative(run.path, candidate)
                    except ValueError:
                        errors.append(f"artifact path escape: {relative}")
                        continue
                    if not candidate.is_file() or sha256_file(candidate) != item.get("sha256"):
                        errors.append(f"artifact hash mismatch: {relative}")
                        if payload.get("step") == "user-approval":
                            approval_invalidated = True
            previous = sha256_file(receipt_path)
        if run.latest_receipt_sha256 != previous:
            errors.append("manifest latest receipt hash mismatch")
        return ChainVerification(not errors, tuple(errors), approval_invalidated)
