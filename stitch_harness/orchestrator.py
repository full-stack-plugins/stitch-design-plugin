"""Finite, evidence-driven orchestration for Stitch delivery."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from .contracts import PageSpec
from .evidence import ExternalEvidence
from .html_gate import validate_html
from .ocr_gate import validate_ocr
from .preflight import default_preflight
from .state import InvalidTransition, RunState
from .storage import ArtifactRecord, Receipt, Run, RunStore, _atomic_json, sha256_file
from .visual_gate import validate_visual_scores


class ApprovalRequired(ValueError):
    """Only an explicit human decision can approve a run."""


@dataclass(frozen=True)
class NextAction:
    kind: str
    expected_evidence_step: str | None = None


@dataclass(frozen=True)
class RunStatus:
    run_id: str
    state: RunState
    exit_code: int
    next_action: NextAction
    errors: tuple[str, ...] = ()
    reconciliation_attempts: int = 0

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "state": self.state.value,
            "exit_code": self.exit_code,
            "next_action": {
                "kind": self.next_action.kind,
                "expected_evidence_step": self.next_action.expected_evidence_step,
            },
            "errors": list(self.errors),
            "reconciliation_attempts": self.reconciliation_attempts,
        }


@dataclass(frozen=True)
class ApprovalDecision:
    decision: str
    source: str
    artifact_hashes: dict[str, str]


_ACTIONS = {
    RunState.DRAFT: NextAction("preflight"),
    RunState.PREFLIGHT_PASSED: NextAction("stitch.generate", "stitch.generate"),
    RunState.STITCH_GENERATED: NextAction("stitch.validate-source", "stitch.generate"),
    RunState.SOURCE_ACCEPTED: NextAction("imagegen.generate", "imagegen"),
    RunState.ART_GENERATED: NextAction("ocr-and-business.validate", "ocr"),
    RunState.ART_ACCEPTED: NextAction("stitch.roundtrip", "stitch.roundtrip"),
    RunState.ROUNDTRIPPED: NextAction("stitch.editability-probe", "editability"),
    RunState.EDITABILITY_VERIFIED: NextAction("visual.compare-and-judge", "visual-judge"),
    RunState.COMPARISON_ACCEPTED: NextAction("prepare-user-review"),
    RunState.AWAITING_USER_APPROVAL: NextAction("await-user-approval"),
    RunState.APPROVED: NextAction("archive"),
    RunState.ARCHIVED: NextAction("complete"),
    RunState.RECONCILING: NextAction("stitch.reconcile-read"),
    RunState.BLOCKED: NextAction("blocked"),
}


class Harness:
    def __init__(
        self,
        *,
        preflight: Callable[[Path], tuple[str, ...]] = default_preflight,
        store: RunStore | None = None,
    ):
        self.preflight = preflight
        self.store = store or RunStore()

    @staticmethod
    def _manifest(run: Run) -> dict:
        return json.loads((run.path / "manifest.json").read_text(encoding="utf-8"))

    @classmethod
    def _attempts(cls, run: Run) -> int:
        value = cls._manifest(run).get("reconciliation_attempts", 0)
        return value if isinstance(value, int) and value >= 0 else 0

    def start(self, project_root: Path, page_id: str, *, now: datetime | None = None) -> RunStatus:
        spec = PageSpec.load(project_root / ".stitch" / "specs" / f"{page_id}.json")
        run = self.store.start(project_root, spec, now or datetime.now(UTC))
        errors = self.preflight(project_root)
        if errors:
            run = self.store.update_state(run, RunState.BLOCKED)
            return RunStatus(run.run_id, run.state, 1, _ACTIONS[run.state], errors)
        run = self.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "preflight"))
        run = self.store.update_state(run, RunState.PREFLIGHT_PASSED)
        return RunStatus(run.run_id, run.state, 0, _ACTIONS[run.state])

    def resume(self, project_root: Path, run_id: str, evidence_path: Path | None = None) -> RunStatus:
        run = self.store.load(project_root, run_id)
        verification = self.store.verify_chain(run)
        if not verification.valid:
            return RunStatus(run_id, run.state, 1, NextAction("blocked"), verification.errors)
        if evidence_path is None:
            return RunStatus(run_id, run.state, 0, _ACTIONS[run.state], reconciliation_attempts=self._attempts(run))
        raw = json.loads(evidence_path.read_text(encoding="utf-8"))
        if raw.get("result") == "unknown":
            manifest = self._manifest(run)
            if run.state == RunState.BLOCKED:
                return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], ("blocked run requires explicit recovery",), self._attempts(run))
            if run.state == RunState.RECONCILING:
                expected = manifest.get("reconciliation_step")
                if raw.get("step") != expected:
                    return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], (f"expected {expected} reconciliation evidence",), self._attempts(run))
                attempts = self._attempts(run) + 1
                manifest["reconciliation_attempts"] = attempts
                if attempts >= 3:
                    run = self.store.update_state(run, RunState.BLOCKED)
                    manifest["state"] = RunState.BLOCKED.value
                    manifest["blocked_reason"] = "three unresolved reconciliation attempts"
                _atomic_json(run.path / "manifest.json", manifest)
                run = replace(run, state=RunState(manifest["state"]))
                return RunStatus(run_id, run.state, 3 if run.state == RunState.RECONCILING else 1, _ACTIONS[run.state], reconciliation_attempts=attempts)
            expected = _ACTIONS[run.state].expected_evidence_step
            if raw.get("step") != expected:
                return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], (f"expected {expected} evidence",))
            timestamp = datetime.now(UTC).isoformat()
            receipt = Receipt(
                run.run_id,
                run.page_id,
                str(raw["step"]),
                1,
                "unknown",
                timestamp,
                timestamp,
                error="external write result is unknown",
            )
            run = self.store.append_receipt(run, receipt)
            source_state = run.state
            run = self.store.update_state(run, RunState.RECONCILING)
            manifest = self._manifest(run)
            manifest.update({"reconciliation_attempts": 1, "reconciliation_from": source_state.value, "reconciliation_step": raw["step"]})
            _atomic_json(run.path / "manifest.json", manifest)
            return RunStatus(run_id, run.state, 3, _ACTIONS[run.state], reconciliation_attempts=1)
        if run.state in {RunState.RECONCILING, RunState.BLOCKED}:
            return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], ("reconciliation must be completed through explicit recovery",), self._attempts(run))
        expected = _ACTIONS[run.state].expected_evidence_step
        if expected is None:
            return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], ("current state does not accept evidence",))
        evidence = ExternalEvidence.from_dict(raw, expected)
        errors = evidence.verify_artifacts(run.path)
        if errors:
            return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], errors)
        spec = PageSpec.load(run.path / "spec.json")
        if run.state == RunState.PREFLIGHT_PASSED:
            html_artifacts = [item for item in evidence.artifacts if item.mime == "text/html"]
            render_metadata = evidence.result.get("render_metadata")
            if len(html_artifacts) != 1 or not isinstance(render_metadata, dict):
                return RunStatus(
                    run_id,
                    run.state,
                    1,
                    _ACTIONS[run.state],
                    ("Stitch source evidence requires one HTML artifact and render metadata",),
                )
            gate = validate_html(spec, run.path / html_artifacts[0].path, render_metadata)
            if not gate.passed:
                return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], gate.failures)
        elif run.state == RunState.SOURCE_ACCEPTED:
            images = [item for item in evidence.artifacts if item.mime and item.mime.startswith("image/")]
            if len(images) != 1 or (images[0].width, images[0].height) != (spec.canvas.width, spec.canvas.height):
                return RunStatus(
                    run_id,
                    run.state,
                    1,
                    _ACTIONS[run.state],
                    (f"ImageGen output must be exactly {spec.canvas.width}x{spec.canvas.height}",),
                )
        elif run.state == RunState.ART_GENERATED:
            gate = validate_ocr(spec, evidence)
            if not gate.passed:
                return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], gate.failures)
        elif run.state == RunState.ART_ACCEPTED:
            html_artifacts = [item for item in evidence.artifacts if item.mime == "text/html"]
            render_metadata = evidence.result.get("render_metadata")
            if len(html_artifacts) != 1 or not isinstance(render_metadata, dict):
                return RunStatus(
                    run_id,
                    run.state,
                    1,
                    _ACTIONS[run.state],
                    ("Stitch roundtrip evidence requires one HTML artifact and render metadata",),
                )
            gate = validate_html(spec, run.path / html_artifacts[0].path, render_metadata)
            if not gate.passed:
                return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], gate.failures)
        elif run.state == RunState.ROUNDTRIPPED:
            hashes = evidence.result.get("hashes")
            parity = isinstance(hashes, dict) and hashes.get("before_html") == hashes.get("restored_html") and hashes.get("before_render") == hashes.get("restored_render")
            changed = isinstance(hashes, dict) and hashes.get("before_html") != hashes.get("edited_html") and hashes.get("before_render") != hashes.get("edited_render")
            if evidence.result.get("editable") is not True or evidence.result.get("restored") is not True or not parity or not changed:
                return RunStatus(
                    run_id,
                    run.state,
                    1,
                    _ACTIONS[run.state],
                    ("editability probe requires changed edit hashes and exact HTML/render restoration parity",),
                )
        elif run.state == RunState.EDITABILITY_VERIFIED:
            gate = validate_visual_scores(spec, evidence)
            layout_score = evidence.result.get("layout_score")
            failures = list(gate.failures)
            if not isinstance(layout_score, (int, float)) or layout_score < spec.comparison.layout_score_min:
                failures.append(f"layout score must be at least {spec.comparison.layout_score_min}")
            if failures:
                return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], tuple(failures))
        receipt = Receipt.passed(
            run.run_id,
            run.page_id,
            expected,
            outputs=[
                ArtifactRecord(item.path, item.sha256, item.mime or "application/octet-stream", item.width, item.height)
                for item in evidence.artifacts
            ],
        )
        resource_ids = evidence.result.get("provider_resource_ids", [])
        if isinstance(resource_ids, list) and all(isinstance(item, str) for item in resource_ids):
            receipt = replace(receipt, provider_resource_ids=tuple(resource_ids))
        run = self.store.append_receipt(run, receipt)
        target = {
            RunState.PREFLIGHT_PASSED: RunState.STITCH_GENERATED,
            RunState.STITCH_GENERATED: RunState.SOURCE_ACCEPTED,
            RunState.SOURCE_ACCEPTED: RunState.ART_GENERATED,
            RunState.ART_GENERATED: RunState.ART_ACCEPTED,
            RunState.ART_ACCEPTED: RunState.ROUNDTRIPPED,
            RunState.ROUNDTRIPPED: RunState.EDITABILITY_VERIFIED,
            RunState.EDITABILITY_VERIFIED: RunState.COMPARISON_ACCEPTED,
        }.get(run.state)
        if target is None:
            return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], ("unsupported evidence transition",))
        run = self.store.update_state(run, target)
        if target == RunState.STITCH_GENERATED:
            run = self.store.update_state(run, RunState.SOURCE_ACCEPTED)
        if target == RunState.COMPARISON_ACCEPTED:
            run = self.store.update_state(run, RunState.AWAITING_USER_APPROVAL)
        return RunStatus(run_id, run.state, 0, _ACTIONS[run.state])

    def status(self, project_root: Path, run_id: str) -> RunStatus:
        run = self.store.load(project_root, run_id)
        verification = self.store.verify_chain(run)
        return RunStatus(run_id, run.state, 0 if verification.valid else 1, _ACTIONS[run.state], verification.errors, self._attempts(run))

    def recover(self, project_root: Path, run_id: str, reason: str) -> RunStatus:
        """Resume an exhausted reconciliation only after an explicit recorded reason."""

        run = self.store.load(project_root, run_id)
        if run.state != RunState.BLOCKED:
            raise InvalidTransition("only a blocked run can be recovered")
        reason = reason.strip()
        if not reason:
            raise ValueError("recovery requires a non-empty reason")
        manifest = self._manifest(run)
        source = manifest.get("reconciliation_from")
        try:
            target = RunState(source)
        except (TypeError, ValueError) as error:
            raise InvalidTransition("blocked run has no recoverable reconciliation state") from error
        if target in {RunState.BLOCKED, RunState.RECONCILING, RunState.ARCHIVED}:
            raise InvalidTransition("blocked run recovery target is invalid")
        manifest.update({"state": target.value, "reconciliation_attempts": 0, "last_recovery_reason": reason})
        _atomic_json(run.path / "manifest.json", manifest)
        recovered = replace(run, state=target)
        return RunStatus(run_id, target, 0, _ACTIONS[target], reconciliation_attempts=0)

    def approve(self, project_root: Path, run_id: str, decision: ApprovalDecision) -> RunStatus:
        run = self.store.load(project_root, run_id)
        if run.state != RunState.AWAITING_USER_APPROVAL:
            raise InvalidTransition("run is not awaiting user approval")
        if decision.source != "user":
            raise ApprovalRequired("approval source must be an explicit user decision")
        if decision.decision == "rejected":
            run = self.store.update_state(run, RunState.ART_GENERATED)
            return RunStatus(run_id, run.state, 0, _ACTIONS[run.state])
        if decision.decision != "approved" or not decision.artifact_hashes:
            raise ApprovalRequired("approved decision requires exact artifact hashes")
        required = self.store.required_approval_artifacts(run)
        if decision.artifact_hashes != required:
            raise ApprovalRequired("approval must bind the exact required artifact set")
        records: list[ArtifactRecord] = []
        for relative, digest in decision.artifact_hashes.items():
            path = run.path / relative
            if not path.is_file() or sha256_file(path) != digest:
                raise ApprovalRequired(f"approved artifact hash mismatch: {relative}")
            records.append(ArtifactRecord.from_path(run.path, path, "application/octet-stream"))
        run = self.store.append_receipt(
            run,
            Receipt.passed(run.run_id, run.page_id, "user-approval", inputs=records),
        )
        run = self.store.update_state(run, RunState.APPROVED)
        return RunStatus(run_id, run.state, 0, _ACTIONS[run.state])
