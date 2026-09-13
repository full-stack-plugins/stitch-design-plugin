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


RECEIPT_STEP_SLUGS = {
    "preflight": "preflight",
    "stitch.generate": "stitch-generate",
    "imagegen": "imagegen",
    "ocr": "ocr",
    "stitch.roundtrip": "stitch-roundtrip",
    "editability": "editability",
    "visual-judge": "visual-judge",
    "user-approval": "user-approval",
}

EXPECTED_RECEIPT_STEP = {
    RunState.DRAFT: "preflight",
    RunState.PREFLIGHT_PASSED: "stitch.generate",
    RunState.STITCH_GENERATED: "stitch.generate",
    RunState.SOURCE_ACCEPTED: "imagegen",
    RunState.ART_GENERATED: "ocr",
    RunState.ART_ACCEPTED: "stitch.roundtrip",
    RunState.ROUNDTRIPPED: "editability",
    RunState.EDITABILITY_VERIFIED: "visual-judge",
    RunState.AWAITING_USER_APPROVAL: "user-approval",
}

COMPARISON_ARTIFACTS = (
    "comparison/side-by-side.png",
    "comparison/overlay.png",
    "comparison/diff-heatmap.png",
)


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

    def __post_init__(self) -> None:
        if self.step not in RECEIPT_STEP_SLUGS:
            raise ValueError("receipt step must come from the fixed allowlist")

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
        expected_step = EXPECTED_RECEIPT_STEP.get(run.state)
        if receipt.step != expected_step:
            raise ValueError(f"state {run.state.value} requires {expected_step!r} receipt evidence")
        receipts_dir = run.path / "receipts"
        sequence = len(list(receipts_dir.glob("*.json"))) + 1
        chained = replace(receipt, previous_receipt_sha256=run.latest_receipt_sha256)
        receipt_path = receipts_dir / f"{sequence:03d}-{RECEIPT_STEP_SLUGS[receipt.step]}.json"
        _atomic_json(receipt_path, chained.to_dict())
        receipt_hash = sha256_file(receipt_path)
        manifest_path = run.path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["latest_receipt_sha256"] = receipt_hash
        _atomic_json(manifest_path, manifest)
        return replace(run, latest_receipt_sha256=receipt_hash)

    def load(self, project_root: Path, run_id: str) -> Run:
        return self.load_from_path(project_root / ".stitch" / "runs" / run_id, run_id)

    def load_from_path(self, run_path: Path, run_id: str) -> Run:
        """Load and validate a run manifest from an explicit run directory."""

        if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
            raise ValueError("run_id must not contain a path")
        manifest_path = run_path / "manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError("run manifest schema version mismatch")
        if payload.get("run_id") != run_id:
            raise ValueError("run manifest identity mismatch")
        page_id = payload.get("page_id")
        if not isinstance(page_id, str) or not page_id:
            raise ValueError("run manifest page identity is missing")
        latest_receipt = payload.get("latest_receipt_sha256")
        if latest_receipt is not None and (
            not isinstance(latest_receipt, str)
            or len(latest_receipt) != 64
            or any(character not in "0123456789abcdef" for character in latest_receipt)
        ):
            raise ValueError("run manifest latest receipt hash is invalid")
        return Run(
            run_id,
            page_id,
            run_path,
            RunState(payload["state"]),
            latest_receipt,
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
            if payload.get("step") not in RECEIPT_STEP_SLUGS:
                errors.append(f"receipt step is outside the allowlist: {receipt_path.name}")
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
                        if payload.get("step") == "user-approval":
                            errors.append(f"approved artifact hash mismatch: {relative}")
                            approval_invalidated = True
                        else:
                            errors.append(f"artifact hash mismatch: {relative}")
            previous = sha256_file(receipt_path)
        if run.latest_receipt_sha256 != previous:
            errors.append("manifest latest receipt hash mismatch")
        return ChainVerification(not errors, tuple(errors), approval_invalidated)

    def required_approval_artifacts(self, run: Run) -> dict[str, str]:
        """Derive the exact review set from accepted producer receipts."""

        verification = self.verify_chain(run)
        if not verification.valid:
            raise ValueError("cannot derive approval artifacts from an invalid receipt chain")

        outputs_by_step: dict[str, list[dict[str, Any]]] = {}
        for receipt_path in sorted((run.path / "receipts").glob("*.json")):
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            outputs_by_step[payload["step"]] = list(payload.get("outputs", []))

        imagegen = outputs_by_step.get("imagegen", [])
        roundtrip = outputs_by_step.get("stitch.roundtrip", [])
        visual = outputs_by_step.get("visual-judge", [])
        art_images = [item for item in imagegen if str(item.get("mime", "")).startswith("image/")]
        roundtrip_html = [item for item in roundtrip if item.get("mime") == "text/html"]
        stitch_images = [item for item in roundtrip if str(item.get("mime", "")).startswith("image/")]
        visual_by_path = {str(item.get("path")): item for item in visual}

        if len(art_images) != 1:
            raise ValueError("approval requires exactly one accepted art render")
        if len(roundtrip_html) != 1:
            raise ValueError("approval requires exactly one accepted roundtrip HTML artifact")
        if len(stitch_images) != 1:
            raise ValueError("approval requires exactly one final Stitch render")
        missing_comparisons = [path for path in COMPARISON_ARTIFACTS if path not in visual_by_path]
        if missing_comparisons:
            raise ValueError("approval requires all three comparison images")
        if any(
            not str(visual_by_path[path].get("mime", "")).startswith("image/")
            for path in COMPARISON_ARTIFACTS
        ):
            raise ValueError("approval comparison artifacts require an image MIME")

        required = [art_images[0], roundtrip_html[0], stitch_images[0]]
        required.extend(visual_by_path[path] for path in COMPARISON_ARTIFACTS)
        return {str(item["path"]): str(item["sha256"]) for item in required}

    def required_comparison_artifacts(self, run: Run) -> tuple[ArtifactRecord, ArtifactRecord]:
        """Return the accepted art render and final Stitch render bound by receipts."""

        verification = self.verify_chain(run)
        if not verification.valid:
            raise ValueError("cannot derive comparison sources from an invalid receipt chain")
        outputs_by_step: dict[str, list[dict[str, Any]]] = {}
        for receipt_path in sorted((run.path / "receipts").glob("*.json")):
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            outputs_by_step[payload["step"]] = list(payload.get("outputs", []))
        art = [item for item in outputs_by_step.get("imagegen", []) if str(item.get("mime", "")).startswith("image/")]
        stitch = [item for item in outputs_by_step.get("stitch.roundtrip", []) if str(item.get("mime", "")).startswith("image/")]
        if len(art) != 1 or len(stitch) != 1:
            raise ValueError("comparison requires exactly one accepted art render and one final Stitch render")

        def record(item: dict[str, Any]) -> ArtifactRecord:
            return ArtifactRecord(
                str(item["path"]), str(item["sha256"]), str(item["mime"]),
                item.get("width"), item.get("height"),
            )

        return record(art[0]), record(stitch[0])

    def verify_approval(self, run: Run) -> ChainVerification:
        """Verify the receipt chain and that approval binds the current review set."""

        chain = self.verify_chain(run)
        errors = list(chain.errors)
        approval_invalidated = chain.approval_invalidated
        try:
            required = self.required_approval_artifacts(run)
        except ValueError as error:
            errors.append(str(error))
            return ChainVerification(False, tuple(dict.fromkeys(errors)), True)

        approval_inputs: dict[str, str] | None = None
        for receipt_path in sorted((run.path / "receipts").glob("*.json")):
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            if payload.get("step") == "user-approval":
                approval_inputs = {
                    str(item.get("path")): str(item.get("sha256"))
                    for item in payload.get("inputs", [])
                }
        if approval_inputs is None:
            errors.append("user approval receipt is missing")
            approval_invalidated = True
        elif approval_inputs != required:
            errors.append("user approval does not bind the exact required artifact set")
            approval_invalidated = True
        return ChainVerification(not errors, tuple(dict.fromkeys(errors)), approval_invalidated)
