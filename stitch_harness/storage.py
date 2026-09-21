"""Atomic run storage and tamper-evident receipt chaining."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import PageSpec
from .state import RunState, transition

RECEIPT_STEP_SLUGS = {
    "preflight": "preflight",
    "stitch.generate": "stitch-generate",
    "art-decision": "art-decision",
    "imagegen": "imagegen",
    "ocr": "ocr",
    "stitch.normalize": "stitch-normalize",
    "stitch.roundtrip": "stitch-roundtrip",
    "editability": "editability",
    "visual-judge": "visual-judge",
    "reconciliation": "reconciliation",
    "user-approval": "user-approval",
}

EXPECTED_RECEIPT_STEP = {
    RunState.DRAFT: "preflight",
    RunState.PREFLIGHT_PASSED: "stitch.generate",
    RunState.STITCH_GENERATED: "stitch.generate",
    RunState.AWAITING_ART_DECISION: "art-decision",
    RunState.ART_ENHANCEMENT_APPROVED: "imagegen",
    RunState.STITCH_ONLY_SELECTED: "editability",
    RunState.ART_GENERATED: "ocr",
    RunState.ART_ACCEPTED: "stitch.normalize",
    RunState.SEMANTIC_NORMALIZED: "stitch.roundtrip",
    RunState.ROUNDTRIPPED: "editability",
    RunState.EDITABILITY_VERIFIED: "visual-judge",
    RunState.AWAITING_USER_APPROVAL: "user-approval",
    RunState.RECONCILING: "reconciliation",
}

COMPARISON_ARTIFACTS = (
    "comparison/side-by-side.png",
    "comparison/overlay.png",
    "comparison/diff-heatmap.png",
)
PENDING_RECEIPT_NAME = ".receipt-pending.json"
RECEIPT_FILE_PATTERN = re.compile(r"^(?P<sequence>0*[1-9][0-9]*)-[a-z0-9-]+\.json$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _fsync_directory(path: Path) -> None:
    """Persist directory-entry changes on platforms that expose directory fsync."""

    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _durable_unlink(path: Path) -> None:
    path.unlink()
    _fsync_directory(path.parent)


def _receipt_sequence(path: Path) -> int | None:
    match = RECEIPT_FILE_PATTERN.fullmatch(path.name)
    return int(match.group("sequence")) if match is not None else None


def _sorted_receipt_paths(receipts_dir: Path) -> list[Path]:
    paths = list(receipts_dir.glob("*.json"))
    return sorted(paths, key=lambda path: (_receipt_sequence(path) is None, _receipt_sequence(path) or 0, path.name))


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
        _fsync_directory(path.parent)
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
    ) -> ArtifactRecord:
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
    ) -> Receipt:
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

    def _checkpoint(self, name: str) -> None:
        """Test-only failure boundary; production stores do nothing."""

        del name

    def _recover_pending(self, run_path: Path) -> None:
        journal_path = run_path / PENDING_RECEIPT_NAME
        if not journal_path.exists():
            return
        if journal_path.is_symlink() or not journal_path.is_file():
            raise ValueError("pending receipt journal must be a regular file")
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("pending receipt journal is invalid") from error
        if not isinstance(journal, dict) or journal.get("schema_version") != 1:
            raise ValueError("pending receipt journal schema mismatch")
        receipt_name = journal.get("receipt_name")
        receipt_payload = journal.get("receipt")
        expected_hash = journal.get("receipt_sha256")
        if (
            not isinstance(receipt_name, str)
            or RECEIPT_FILE_PATTERN.fullmatch(receipt_name) is None
            or not isinstance(receipt_payload, dict)
            or not isinstance(expected_hash, str)
            or hashlib.sha256(_canonical_bytes(receipt_payload)).hexdigest() != expected_hash
        ):
            raise ValueError("pending receipt journal content mismatch")
        manifest_path = run_path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        step = receipt_payload.get("step")
        if (
            step not in RECEIPT_STEP_SLUGS
            or not receipt_name.endswith(f"-{RECEIPT_STEP_SLUGS[step]}.json")
            or receipt_payload.get("run_id") != manifest.get("run_id")
            or receipt_payload.get("page_id") != manifest.get("page_id")
        ):
            raise ValueError("pending receipt journal identity mismatch")
        previous = receipt_payload.get("previous_receipt_sha256")
        current = manifest.get("latest_receipt_sha256")
        if current not in {previous, expected_hash}:
            raise ValueError("pending receipt journal does not extend the manifest chain")
        receipt_path = run_path / "receipts" / receipt_name
        if receipt_path.exists():
            if receipt_path.is_symlink() or not receipt_path.is_file() or sha256_file(receipt_path) != expected_hash:
                raise ValueError("pending receipt file does not match its journal")
        else:
            _atomic_json(receipt_path, receipt_payload)
        if current != expected_hash:
            manifest["latest_receipt_sha256"] = expected_hash
            _atomic_json(manifest_path, manifest)
        _durable_unlink(journal_path)

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
        self._recover_pending(run.path)
        manifest_path = run.path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        run = replace(run, latest_receipt_sha256=manifest.get("latest_receipt_sha256"))
        if receipt.run_id != run.run_id or receipt.page_id != run.page_id:
            raise ValueError("receipt identity does not match run")
        expected_step = EXPECTED_RECEIPT_STEP.get(run.state)
        if receipt.step != expected_step:
            raise ValueError(f"state {run.state.value} requires {expected_step!r} receipt evidence")
        receipts_dir = run.path / "receipts"
        receipt_paths = list(receipts_dir.glob("*.json"))
        sequences = [_receipt_sequence(path) for path in receipt_paths]
        if any(sequence is None for sequence in sequences):
            raise ValueError("receipt filename is invalid")
        sequence = max((sequence for sequence in sequences if sequence is not None), default=0) + 1
        chained = replace(receipt, previous_receipt_sha256=run.latest_receipt_sha256)
        receipt_path = receipts_dir / f"{sequence:03d}-{RECEIPT_STEP_SLUGS[receipt.step]}.json"
        receipt_payload = chained.to_dict()
        receipt_hash = hashlib.sha256(_canonical_bytes(receipt_payload)).hexdigest()
        journal = {
            "schema_version": 1,
            "receipt_name": receipt_path.name,
            "receipt_sha256": receipt_hash,
            "receipt": receipt_payload,
        }
        _atomic_json(run.path / PENDING_RECEIPT_NAME, journal)
        self._checkpoint("pending-written")
        _atomic_json(receipt_path, receipt_payload)
        self._checkpoint("receipt-written")
        manifest["latest_receipt_sha256"] = receipt_hash
        _atomic_json(manifest_path, manifest)
        self._checkpoint("manifest-written")
        _durable_unlink(run.path / PENDING_RECEIPT_NAME)
        return replace(run, latest_receipt_sha256=receipt_hash)

    def load(self, project_root: Path, run_id: str) -> Run:
        return self.load_from_path(project_root / ".stitch" / "runs" / run_id, run_id)

    def load_from_path(self, run_path: Path, run_id: str) -> Run:
        """Load and validate a run manifest from an explicit run directory."""

        if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
            raise ValueError("run_id must not contain a path")
        self._recover_pending(run_path)
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

    def update_states(
        self,
        run: Run,
        targets: Iterable[RunState],
        *,
        manifest_updates: dict[str, Any] | None = None,
    ) -> Run:
        """Validate a transition sequence and persist its final state atomically."""

        next_state = run.state
        for target in targets:
            next_state = transition(next_state, target)
        manifest_path = run.path / "manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["state"] = next_state.value
        if manifest_updates:
            payload.update(manifest_updates)
        _atomic_json(manifest_path, payload)
        return replace(run, state=next_state)

    def update_state(self, run: Run, target: RunState) -> Run:
        return self.update_states(run, (target,))

    def verify_chain(self, run: Run) -> ChainVerification:
        errors: list[str] = []
        previous: str | None = None
        approval_invalidated = False
        receipt_paths = _sorted_receipt_paths(run.path / "receipts")
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

    def has_accepted_receipt(self, run: Run, step: str) -> bool:
        """Return whether a verified passed receipt already locks a workflow step."""

        verification = self.verify_chain(run)
        if not verification.valid:
            raise ValueError("cannot inspect accepted receipts on an invalid chain")
        for receipt_path in (run.path / "receipts").glob("*.json"):
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            if payload.get("step") == step and payload.get("result") == "passed":
                return True
        return False

    def has_accepted_receipt_for_artifacts(
        self,
        run: Run,
        step: str,
        expected_sources: tuple[tuple[str, str, str], ...],
    ) -> bool:
        """Return whether an accepted passed receipt binds the given source artifacts.

        Each source is `(path, sha256, mime)`. Used to detect "same artifacts are
        re-compared" without blocking the next round when an earlier comparison
        bound a different set of artifacts. The receipt stores its source artifacts
        under the ``inputs`` field (see ``Receipt.to_dict``); the visual-judge
        evidence envelope stores the same pair under ``source_artifacts``.

        This predicate does NOT call ``verify_chain``: callers may legitimately
        invoke it while a receipt chain is mid-edit (for example, when an earlier
        round's artifacts have been replaced with new bytes for the next round),
        and the predicate's job is purely to detect a binding match, not to police
        chain integrity.
        """

        if not expected_sources:
            return False
        expected = set(expected_sources)
        receipts_dir = run.path / "receipts"
        if not receipts_dir.is_dir():
            return False
        for receipt_path in receipts_dir.glob("*.json"):
            try:
                payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("step") != step or payload.get("result") != "passed":
                continue
            bound = payload.get("inputs") or []
            bound_set = {
                (item.get("path"), item.get("sha256"), item.get("mime"))
                for item in bound
                if isinstance(item, dict)
            }
            if bound_set == expected:
                return True
        return False

    def required_approval_artifacts(self, run: Run) -> dict[str, str]:
        """Derive the exact review set from accepted producer receipts."""

        verification = self.verify_chain(run)
        if not verification.valid:
            raise ValueError("cannot derive approval artifacts from an invalid receipt chain")

        outputs_by_step: dict[str, list[dict[str, Any]]] = {}
        for receipt_path in _sorted_receipt_paths(run.path / "receipts"):
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            outputs_by_step[payload["step"]] = list(payload.get("outputs", []))

        manifest = json.loads((run.path / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("art_mode") == "keep_stitch":
            source = outputs_by_step.get("stitch.generate", [])
            source_html = [item for item in source if item.get("mime") == "text/html"]
            source_images = [
                item for item in source if str(item.get("mime", "")).startswith("image/")
            ]
            if len(source_html) != 1 or len(source_images) != 1:
                raise ValueError("stitch-only approval requires one source HTML and render")
            return {
                str(item["path"]): str(item["sha256"])
                for item in (source_html[0], source_images[0])
            }

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
        for receipt_path in _sorted_receipt_paths(run.path / "receipts"):
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

    def required_roundtrip_artifacts(self, run: Run) -> tuple[ArtifactRecord, ArtifactRecord]:
        """Return the exact accepted roundtrip HTML and final render."""

        verification = self.verify_chain(run)
        if not verification.valid:
            raise ValueError("cannot derive editability sources from an invalid receipt chain")
        roundtrip: list[dict[str, Any]] = []
        for receipt_path in _sorted_receipt_paths(run.path / "receipts"):
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            if payload.get("step") == "stitch.roundtrip":
                roundtrip = list(payload.get("outputs", []))
        html = [item for item in roundtrip if item.get("mime") == "text/html"]
        render = [item for item in roundtrip if item.get("mime") == "image/png"]
        if len(html) != 1 or len(render) != 1:
            raise ValueError("editability requires one accepted roundtrip HTML and PNG render")
        return (
            ArtifactRecord(str(html[0]["path"]), str(html[0]["sha256"]), "text/html", html[0].get("width"), html[0].get("height")),
            ArtifactRecord(str(render[0]["path"]), str(render[0]["sha256"]), "image/png", render[0].get("width"), render[0].get("height")),
        )

    def required_source_artifacts(self, run: Run) -> tuple[ArtifactRecord, ArtifactRecord]:
        """Return the exact accepted source HTML and render for Stitch-only review."""

        verification = self.verify_chain(run)
        if not verification.valid:
            raise ValueError("cannot derive source artifacts from an invalid receipt chain")
        source: list[dict[str, Any]] = []
        for receipt_path in _sorted_receipt_paths(run.path / "receipts"):
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            if payload.get("step") == "stitch.generate" and payload.get("result") == "passed":
                source = list(payload.get("outputs", []))
        html = [item for item in source if item.get("mime") == "text/html"]
        render = [item for item in source if str(item.get("mime", "")).startswith("image/")]
        if len(html) != 1 or len(render) != 1:
            raise ValueError("editability requires one accepted source HTML and render")
        return (
            ArtifactRecord(str(html[0]["path"]), str(html[0]["sha256"]), str(html[0]["mime"]), html[0].get("width"), html[0].get("height")),
            ArtifactRecord(str(render[0]["path"]), str(render[0]["sha256"]), str(render[0]["mime"]), render[0].get("width"), render[0].get("height")),
        )

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
        for receipt_path in _sorted_receipt_paths(run.path / "receipts"):
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
