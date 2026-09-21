"""Finite, evidence-driven orchestration for Stitch delivery."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from .contracts import PageSpec
from .device_gate import validate_screen_device
from .evidence import (
    EvidenceArtifact,
    EvidenceError,
    ExternalEvidence,
    reject_sensitive_content,
)
from .html_gate import validate_html
from .ocr_gate import validate_ocr
from .preflight import default_preflight
from .semantic_normalizer import normalize_purposes
from .state import InvalidTransition, RunState
from .storage import (
    ArtifactRecord,
    Receipt,
    Run,
    RunStore,
    _atomic_json,
    _sorted_receipt_paths,
    sha256_file,
)
from .visual_gate import validate_visual_scores


class ApprovalRequired(ValueError):
    """Only an explicit human decision can approve a run."""


class RunBlockedAfterStall(RuntimeError):
    """The convergence loop stalled and the next redo cannot proceed.

    Raised by ``Harness.redo_art`` when the run is already stalled (round totals
    did not improve a full point, or the same gap id appeared in two consecutive
    verdicts) and the caller has not declared a structural rework. Also raised
    when a structural rework was already performed and the next round still
    stalls, at which point the run is moved to ``BLOCKED`` and the user must
    weigh in.
    """


@dataclass(frozen=True)
class RoundResult:
    """Outcome of recording one convergence round's visual judgment."""

    round_index: int
    total_score: int
    gap_ids: tuple[str, ...]
    stalled: bool
    stall_reason: dict[str, Any] | None


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


@dataclass(frozen=True)
class ArtEnhancementDecision:
    user_response: str


_ACTIONS = {
    RunState.DRAFT: NextAction("preflight"),
    RunState.PREFLIGHT_PASSED: NextAction("stitch.generate", "stitch.generate"),
    RunState.STITCH_GENERATED: NextAction("stitch.validate-source", "stitch.generate"),
    RunState.SOURCE_ACCEPTED: NextAction("prepare-art-enhancement-decision"),
    RunState.AWAITING_ART_DECISION: NextAction("await-art-enhancement-decision"),
    RunState.ART_ENHANCEMENT_APPROVED: NextAction("imagegen.generate", "imagegen"),
    RunState.STITCH_ONLY_SELECTED: NextAction("stitch.editability-probe", "editability"),
    RunState.ART_GENERATED: NextAction("ocr-and-business.validate", "ocr"),
    RunState.ART_ACCEPTED: NextAction("stitch.normalize-semantics", "stitch.normalize"),
    RunState.SEMANTIC_NORMALIZED: NextAction("stitch.roundtrip", "stitch.roundtrip"),
    RunState.ROUNDTRIPPED: NextAction("stitch.editability-probe", "editability"),
    RunState.EDITABILITY_VERIFIED: NextAction("visual.compare-and-judge", "visual-judge"),
    RunState.COMPARISON_ACCEPTED: NextAction("prepare-user-review"),
    RunState.AWAITING_USER_APPROVAL: NextAction("await-user-approval"),
    RunState.APPROVED: NextAction("archive"),
    RunState.ARCHIVED: NextAction("complete"),
    RunState.RECONCILING: NextAction("stitch.reconcile-read"),
    RunState.BLOCKED: NextAction("blocked"),
    RunState.CANCELLED: NextAction("cancelled"),
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

    @staticmethod
    def _sanitize_reason(reason: str) -> str:
        if not isinstance(reason, str):
            raise ValueError("reason must be a string")
        normalized = reason.strip()
        if (
            not normalized
            or len(normalized) > 500
            or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
        ):
            raise ValueError("reason must be one sanitized line without sensitive content")
        try:
            reject_sensitive_content({"reason": normalized})
        except EvidenceError as error:
            raise ValueError("reason must be sanitized and contain no sensitive content") from error
        return normalized

    def _restore_reconciliation(self, run: Run, manifest: dict, reason: str, outcome: str) -> Run:
        try:
            target = RunState(manifest.get("reconciliation_from"))
        except (TypeError, ValueError) as error:
            raise InvalidTransition("reconciliation has no valid source state") from error
        if target in {RunState.BLOCKED, RunState.RECONCILING, RunState.ARCHIVED}:
            raise InvalidTransition("reconciliation source state is invalid")
        reconciliation_target = manifest.pop("reconciliation_target", None)
        manifest.update({
            "state": target.value,
            "reconciliation_attempts": 0,
            "last_reconciliation_outcome": outcome,
            "last_reconciliation_reason": reason,
            **(
                {"last_reconciliation_target": reconciliation_target}
                if reconciliation_target is not None
                else {}
            ),
        })
        _atomic_json(run.path / "manifest.json", manifest)
        return replace(run, state=target)

    def _validate_evidence_for_state(
        self,
        run: Run,
        state: RunState,
        evidence: ExternalEvidence,
    ) -> tuple[str, ...]:
        spec = PageSpec.load(run.path / "spec.json")
        if state == RunState.PREFLIGHT_PASSED:
            html_artifacts = [item for item in evidence.artifacts if item.mime == "text/html"]
            render_metadata = evidence.result.get("render_metadata")
            if len(html_artifacts) != 1 or not isinstance(render_metadata, dict):
                return ("Stitch source evidence requires one HTML artifact and render metadata",)
            device = validate_screen_device(spec, evidence)
            if not device.passed:
                return device.failures
            gate = validate_html(spec, run.path / html_artifacts[0].path, render_metadata)
            return gate.failures
        if state == RunState.ART_ENHANCEMENT_APPROVED:
            images = [item for item in evidence.artifacts if item.mime and item.mime.startswith("image/")]
            if len(images) != 1 or (images[0].width, images[0].height) != (spec.canvas.width, spec.canvas.height):
                return (f"ImageGen output must be exactly {spec.canvas.width}x{spec.canvas.height}",)
            return ()
        if state == RunState.ART_GENERATED:
            return validate_ocr(spec, evidence).failures
        if state == RunState.ART_ACCEPTED:
            sources = [item for item in evidence.source_artifacts if item.mime == "text/html"]
            outputs = [item for item in evidence.artifacts if item.mime == "text/html"]
            mapping = evidence.result.get("purpose_mapping")
            render_metadata = evidence.result.get("render_metadata")
            if (
                len(sources) != 1
                or len(outputs) != 1
                or not isinstance(mapping, dict)
                or not all(isinstance(key, str) and isinstance(value, str) for key, value in mapping.items())
                or not isinstance(render_metadata, dict)
            ):
                return ("semantic normalization requires one source HTML, one output HTML, a purpose mapping and render metadata",)
            source_path = run.path / sources[0].path
            output_path = run.path / outputs[0].path
            try:
                expected = normalize_purposes(source_path.read_text(encoding="utf-8"), mapping)
                actual = output_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError, ValueError) as error:
                return (str(error),)
            if actual != expected:
                return ("normalized HTML contains changes outside the declared purpose mapping",)
            return validate_html(spec, output_path, render_metadata).failures
        if state == RunState.SEMANTIC_NORMALIZED:
            html_artifacts = [item for item in evidence.artifacts if item.mime == "text/html"]
            render_metadata = evidence.result.get("render_metadata")
            if len(html_artifacts) != 1 or not isinstance(render_metadata, dict):
                return ("Stitch roundtrip evidence requires one HTML artifact and render metadata",)
            return validate_html(spec, run.path / html_artifacts[0].path, render_metadata).failures
        if state in {RunState.ROUNDTRIPPED, RunState.STITCH_ONLY_SELECTED}:
            expected_mimes = {
                "before_html": "text/html", "edited_html": "text/html", "restored_html": "text/html",
                "before_render": "image/png", "edited_render": "image/png", "restored_render": "image/png",
            }
            by_role = {item.semantic_role: item for item in evidence.artifacts if item.semantic_role is not None}
            artifact_hashes = {role: item.sha256 for role, item in by_role.items()}
            hashes = evidence.result.get("hashes")
            correct_shape = (
                len(evidence.artifacts) == 6
                and len(evidence.source_artifacts) == 2
                and len({item.path for item in evidence.artifacts}) == 6
                and set(by_role) == set(expected_mimes)
                and all(by_role[role].mime == mime for role, mime in expected_mimes.items())
                and hashes == artifact_hashes
            )
            if not correct_shape:
                return ("editability artifact hashes require six unique typed semantic artifacts and two before sources",)
            try:
                expected_before = (
                    self.store.required_source_artifacts(run)
                    if state == RunState.STITCH_ONLY_SELECTED
                    else self.store.required_roundtrip_artifacts(run)
                )
            except ValueError as error:
                return (str(error),)
            expected_before_set = {(item.path, item.sha256, item.mime) for item in expected_before}
            actual_before_set = {
                (by_role[role].path, by_role[role].sha256, by_role[role].mime)
                for role in ("before_html", "before_render")
                if role in by_role
            }
            source_before_set = {(item.path, item.sha256, item.mime) for item in evidence.source_artifacts}
            roundtrip_bound = actual_before_set == expected_before_set and source_before_set == expected_before_set
            parity = hashes["before_html"] == hashes["restored_html"] and hashes["before_render"] == hashes["restored_render"]
            changed = hashes["before_html"] != hashes["edited_html"] and hashes["before_render"] != hashes["edited_render"]
            if evidence.result.get("editable") is not True or evidence.result.get("restored") is not True or not parity or not changed or not roundtrip_bound:
                return ("editability artifact hashes require six unique semantic artifacts whose before HTML/render bind the roundtrip receipt",)
            return ()
        if state == RunState.EDITABILITY_VERIFIED:
            failures = list(validate_visual_scores(spec, evidence).failures)
            layout_score = evidence.result.get("layout_score")
            if isinstance(layout_score, bool) or not isinstance(layout_score, (int, float)) or layout_score < spec.comparison.layout_score_min:
                failures.append(f"layout score must be at least {spec.comparison.layout_score_min}")
            if failures:
                return tuple(failures)
            expected_sources = self.store.required_comparison_artifacts(run)
            expected_source_set = {(item.path, item.sha256, item.mime) for item in expected_sources}
            actual_source_set = {(item.path, item.sha256, item.mime) for item in evidence.source_artifacts}
            if len(evidence.source_artifacts) != 2 or actual_source_set != expected_source_set:
                failures.append("visual evidence must bind the accepted art and final Stitch receipt artifacts")
            return tuple(failures)
        return ("unsupported evidence transition",)

    @staticmethod
    def _target_states(state: RunState) -> tuple[RunState, ...]:
        return {
            RunState.PREFLIGHT_PASSED: (
                RunState.STITCH_GENERATED,
                RunState.SOURCE_ACCEPTED,
                RunState.AWAITING_ART_DECISION,
            ),
            RunState.STITCH_GENERATED: (RunState.SOURCE_ACCEPTED, RunState.AWAITING_ART_DECISION),
            RunState.ART_ENHANCEMENT_APPROVED: (RunState.ART_GENERATED,),
            RunState.ART_GENERATED: (RunState.ART_ACCEPTED,),
            RunState.ART_ACCEPTED: (RunState.SEMANTIC_NORMALIZED,),
            RunState.SEMANTIC_NORMALIZED: (RunState.ROUNDTRIPPED,),
            RunState.ROUNDTRIPPED: (RunState.EDITABILITY_VERIFIED,),
            RunState.STITCH_ONLY_SELECTED: (RunState.AWAITING_USER_APPROVAL,),
            RunState.EDITABILITY_VERIFIED: (
                RunState.COMPARISON_ACCEPTED,
                RunState.AWAITING_USER_APPROVAL,
            ),
            RunState.COMPARISON_ACCEPTED: (RunState.AWAITING_USER_APPROVAL,),
        }.get(state, ())

    def decide_art(
        self,
        project_root: Path,
        run_id: str,
        decision: ArtEnhancementDecision,
    ) -> RunStatus:
        run = self.store.load(project_root, run_id)
        if run.state != RunState.AWAITING_ART_DECISION:
            raise InvalidTransition("run is not awaiting an art enhancement decision")
        return self._apply_art_decision(run, decision, allow_redo=False)

    def redo_art(
        self,
        project_root: Path,
        run_id: str,
        decision: ArtEnhancementDecision,
        *,
        structural_rework: bool = False,
    ) -> RunStatus:
        """Apply an enhance decision on the convergence return path.

        The first enhance is recorded with a fresh ``art-decision`` receipt at
        ``AWAITING_ART_DECISION`` via ``decide_art``; every subsequent enhance
        (after the user rejected a previous candidate) is recorded with this
        entry point so the receipt contract stays aligned with the current state.

        ``structural_rework`` must be ``True`` when the latest ``visual_history``
        entry shows a stall; the orchestrator refuses the redo with
        ``RunBlockedAfterStall`` otherwise. If a previous structural rework was
        already performed and this redo also stalls, the run is moved to
        ``BLOCKED`` and the user must weigh in.
        """
        run = self.store.load(project_root, run_id)
        if run.state != RunState.ART_GENERATED:
            raise InvalidTransition("run is not on a convergence return path")
        if decision.user_response != "enhance":
            raise ApprovalRequired(
                "the convergence return path only supports the enhance response; "
                "keep_stitch and cancel are handled at AWAITING_ART_DECISION"
            )
        manifest = self._manifest(run)
        history = list(manifest.get("visual_history") or [])
        stalled_now = bool(manifest.get("convergence_stalled"))
        rework_done = bool(manifest.get("structural_rework_done"))
        if stalled_now and not structural_rework:
            raise RunBlockedAfterStall(
                "convergence loop stalled; redo_art requires structural_rework=True"
            )
        if stalled_now and structural_rework and rework_done:
            # Two structural reworks have failed: stop and hand back.
            self.store.update_state(run, RunState.BLOCKED)
            manifest = self._manifest(run)
            manifest["blocked_reason"] = (
                "structural rework did not break the stall; handing back to the user"
            )
            _atomic_json(run.path / "manifest.json", manifest)
            raise RunBlockedAfterStall(manifest["blocked_reason"])
        return self._apply_art_decision(run, decision, allow_redo=True, structural_rework=structural_rework)

    def record_round_result(
        self,
        project_root: Path,
        run_id: str,
        *,
        total_score: int,
        gap_ids: list[str] | tuple[str, ...],
        structural_rework: bool = False,
    ) -> RoundResult:
        """Append one convergence round to the run manifest and detect stall.

        The Skill calls this after each visual-judge evidence is accepted. The
        helper is idempotent against manifest shape: it appends to
        ``visual_history`` and, when a stall is detected on the latest pair of
        rounds, records ``convergence_stalled`` and ``stall_reason``.
        """
        if not 0 <= total_score <= 25:
            raise ValueError("total_score must be within 0..25 (5 axes x 1..5)")
        normalized_gap_ids = tuple(str(gap_id) for gap_id in gap_ids if gap_id)
        run = self.store.load(project_root, run_id)
        manifest = self._manifest(run)
        history = list(manifest.get("visual_history") or [])
        round_index = len(history) + 1
        entry = {
            "round": round_index,
            "total_score": int(total_score),
            "gap_ids": list(normalized_gap_ids),
            "structural_rework": bool(structural_rework),
        }
        history.append(entry)
        stalled = False
        stall_reason: dict[str, Any] | None = None
        if len(history) >= 2:
            previous, latest = history[-2], history[-1]
            score_gain = latest["total_score"] - previous["total_score"]
            if score_gain < 1:
                stalled = True
                stall_reason = {"type": "no_progress", "score_gain": score_gain}
            else:
                previous_gaps = set(previous["gap_ids"])
                repeated = [gap for gap in latest["gap_ids"] if gap in previous_gaps]
                if repeated:
                    stalled = True
                    stall_reason = {"type": "repeated_gap", "gap_id": repeated[0]}
        manifest["visual_history"] = history
        if stalled:
            manifest["convergence_stalled"] = True
            manifest["stall_reason"] = stall_reason
        if structural_rework:
            manifest["structural_rework_done"] = True
        _atomic_json(run.path / "manifest.json", manifest)
        return RoundResult(
            round_index=round_index,
            total_score=int(total_score),
            gap_ids=normalized_gap_ids,
            stalled=stalled,
            stall_reason=stall_reason,
        )

    def _apply_art_decision(
        self,
        run: Run,
        decision: ArtEnhancementDecision,
        *,
        allow_redo: bool,
        structural_rework: bool = False,
    ) -> RunStatus:
        targets = {
            "enhance": RunState.ART_ENHANCEMENT_APPROVED,
            "keep_stitch": RunState.STITCH_ONLY_SELECTED,
            "cancel": RunState.CANCELLED,
        }
        target = targets.get(decision.user_response)
        if target is None:
            raise ApprovalRequired(
                "user response must be exactly enhance, keep_stitch, or cancel; "
                "ambiguous confirmation must not be inferred"
            )
        manifest_updates: dict[str, Any] = {}
        spec = PageSpec.load(run.path / "spec.json")
        previous_imagegen = self._count_accepted_receipts(run, "imagegen")
        if target is RunState.ART_ENHANCEMENT_APPROVED:
            rounds_used = previous_imagegen + 1
            if rounds_used > spec.comparison.max_rounds:
                run = self.store.update_state(run, RunState.BLOCKED)
                manifest = self._manifest(run)
                manifest["blocked_reason"] = (
                    f"visual delivery budget exhausted after {spec.comparison.max_rounds} rounds"
                )
                _atomic_json(run.path / "manifest.json", manifest)
                return RunStatus(run.run_id, run.state, 1, _ACTIONS[run.state], errors=(manifest["blocked_reason"],))
            manifest_updates["delivery_rounds"] = rounds_used
        if allow_redo:
            # Skip the art-decision receipt: the redo entry point already implies
            # an explicit user response, and the next receipt is imagegen.
            redo_updates = {"art_mode": decision.user_response, **manifest_updates}
            if structural_rework:
                redo_updates["structural_rework_done"] = True
            committed = self.store.update_states(
                run,
                (target,),
                manifest_updates=redo_updates,
            )
            return RunStatus(run.run_id, committed.state, 0, _ACTIONS[committed.state])
        run = self.store.append_receipt(
            run,
            Receipt.passed(
                run.run_id,
                run.page_id,
                "art-decision",
                checks=({"decision": decision.user_response, "source": "explicit-user-response"},),
            ),
        )
        run = self.store.update_states(
            run,
            (target,),
            manifest_updates={"art_mode": decision.user_response, **manifest_updates},
        )
        return RunStatus(run.run_id, run.state, 0, _ACTIONS[run.state])

    @staticmethod
    def _count_accepted_receipts(run: Run, step: str) -> int:
        receipts_dir = run.path / "receipts"
        if not receipts_dir.is_dir():
            return 0
        total = 0
        for receipt_path in receipts_dir.glob("*.json"):
            try:
                payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("step") == step and payload.get("result") == "passed":
                total += 1
        return total

    @staticmethod
    def _matching_receipt_hash(
        run: Run,
        receipt: Receipt,
        *,
        previous_receipt_sha256: str | None = None,
    ) -> str | None:
        receipt_paths = _sorted_receipt_paths(run.path / "receipts")
        for receipt_path in reversed(receipt_paths):
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            if (
                payload.get("step") == receipt.step
                and payload.get("result") == receipt.result
                and payload.get("inputs") == [item.to_dict() for item in receipt.inputs]
                and payload.get("outputs") == [item.to_dict() for item in receipt.outputs]
                and payload.get("checks") == list(receipt.checks)
                and payload.get("provider_resource_ids") == list(receipt.provider_resource_ids)
                and (
                    previous_receipt_sha256 is None
                    or payload.get("previous_receipt_sha256") == previous_receipt_sha256
                )
            ):
                return sha256_file(receipt_path)
        return None

    @staticmethod
    def _latest_unknown_receipt(run: Run, step: str) -> tuple[str, dict] | None:
        for receipt_path in reversed(_sorted_receipt_paths(run.path / "receipts")):
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            if payload.get("step") == step and payload.get("result") == "unknown":
                return sha256_file(receipt_path), payload
        return None

    def _commit_evidence(
        self,
        run: Run,
        effective_state: RunState,
        evidence: ExternalEvidence,
        *,
        manifest_updates: dict | None = None,
        required_previous_receipt_sha256: str | None = None,
    ) -> RunStatus:
        inputs = [
            ArtifactRecord(item.path, item.sha256, item.mime or "application/octet-stream", item.width, item.height)
            for item in evidence.source_artifacts
        ]
        outputs = [
            ArtifactRecord(item.path, item.sha256, item.mime or "application/octet-stream", item.width, item.height)
            for item in evidence.artifacts
        ]
        resource_ids = evidence.result.get("provider_resource_ids", [])
        if not isinstance(resource_ids, list) or not all(isinstance(item, str) for item in resource_ids):
            resource_ids = []
        receipt = Receipt.passed(
            run.run_id, run.page_id, evidence.step,
            inputs=inputs, outputs=outputs,
        )
        receipt = replace(receipt, provider_resource_ids=tuple(resource_ids))
        shadow = replace(run, state=effective_state)
        if self._matching_receipt_hash(
            run,
            receipt,
            previous_receipt_sha256=required_previous_receipt_sha256,
        ) is None:
            shadow = self.store.append_receipt(shadow, receipt)
        else:
            shadow = replace(shadow, latest_receipt_sha256=self.store.load_from_path(run.path, run.run_id).latest_receipt_sha256)
        targets = self._target_states(effective_state)
        if not targets:
            return RunStatus(run.run_id, run.state, 1, _ACTIONS[run.state], ("unsupported evidence transition",))
        committed = self.store.update_states(
            shadow,
            targets,
            manifest_updates=manifest_updates if manifest_updates else None,
        )
        return RunStatus(run.run_id, committed.state, 0, _ACTIONS[committed.state])

    def _validate_reconciliation_probes(
        self,
        run: Run,
        probes: object,
        *,
        outcome: str,
        unknown_ended_at: datetime,
    ) -> tuple[tuple[ArtifactRecord, ...], tuple[dict, ...]]:
        if not isinstance(probes, list) or len(probes) != 3 or not all(isinstance(item, dict) for item in probes):
            raise ValueError("reconciliation requires three typed read probe entries")
        required_keys = {"tool", "invoked_at", "response_id", "status", "result_sha256", "artifact"}
        tools: list[str] = []
        response_ids: set[str] = set()
        paths: set[str] = set()
        records: list[ArtifactRecord] = []
        checks: list[dict] = []
        for probe in probes:
            if set(probe) != required_keys:
                raise ValueError("reconciliation probe fields do not match the typed contract")
            reject_sensitive_content(probe)
            tool = probe["tool"]
            if not isinstance(tool, str):
                raise ValueError("reconciliation probe tool must be a string")
            tools.append(tool)
            timestamp = probe["invoked_at"]
            if not isinstance(timestamp, str):
                raise ValueError("reconciliation probe requires a timezone timestamp")
            try:
                parsed_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError("reconciliation probe requires a timezone timestamp") from error
            if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
                raise ValueError("reconciliation probe requires a timezone timestamp")
            if parsed_time <= unknown_ended_at:
                raise ValueError("reconciliation probe timestamp is stale")
            response_id = probe["response_id"]
            if isinstance(response_id, bool) or not isinstance(response_id, (str, int)) or not str(response_id).strip() or len(str(response_id)) > 128:
                raise ValueError("reconciliation probe response id is invalid")
            if str(response_id) in response_ids:
                raise ValueError("reconciliation probe response ids must be unique")
            response_ids.add(str(response_id))
            status = probe["status"]
            if not isinstance(status, str):
                raise ValueError("reconciliation probe status must be a string")
            if status not in {"found", "empty", "not_found", "unavailable", "skipped"}:
                raise ValueError("reconciliation probe status is invalid")
            artifact_data = probe["artifact"]
            if not isinstance(artifact_data, dict) or set(artifact_data) != {"path", "sha256", "mime"}:
                raise ValueError("reconciliation probe artifact is invalid")
            artifact = EvidenceArtifact.from_dict(artifact_data)
            if artifact.mime != "application/json" or not artifact.path.startswith("artifacts/"):
                raise ValueError("reconciliation probe artifact must be run-local JSON")
            if artifact.path in paths:
                raise ValueError("reconciliation probe artifacts must be unique")
            paths.add(artifact.path)
            candidate = run.path / artifact.path
            root = run.path.resolve()
            current = run.path
            for component in Path(artifact.path).parts:
                current = current / component
                if current.is_symlink():
                    raise ValueError("reconciliation probe artifact path must not contain a symlink")
            try:
                candidate.resolve(strict=True).relative_to(root)
            except (FileNotFoundError, ValueError) as error:
                raise ValueError("reconciliation probe artifact must stay contained under the run") from error
            if not candidate.is_file():
                raise ValueError("reconciliation probe artifact is missing")
            try:
                artifact_bytes = candidate.read_bytes()
            except OSError as error:
                raise ValueError("reconciliation probe artifact could not be read") from error
            if hashlib.sha256(artifact_bytes).hexdigest() != artifact.sha256:
                raise ValueError("reconciliation probe artifact hash mismatch")
            try:
                artifact_payload = json.loads(artifact_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("reconciliation probe artifact must be valid UTF-8 JSON") from error
            reject_sensitive_content(artifact_payload)
            expected_payload_keys = {"tool", "invoked_at", "response_id", "status", "result"}
            if not isinstance(artifact_payload, dict) or set(artifact_payload) != expected_payload_keys:
                raise ValueError("reconciliation probe artifact content does not match its declaration")
            result = artifact_payload["result"]
            inventory_result = (
                tool == "list_screens"
                and status == "found"
                and outcome == "not_applied"
                and isinstance(result, dict)
                and result.get("target_found") is False
            )
            valid_result_keys = (
                {"target_found", "project_id", "complete", "title_hashes"}
                if inventory_result
                else ({"target_found", "reason"} if status == "skipped" else {"target_found"})
            )
            title_hashes = result.get("title_hashes") if isinstance(result, dict) else None
            if (
                not isinstance(result, dict)
                or set(result) != valid_result_keys
                or not isinstance(result.get("target_found"), bool)
                or (status == "skipped" and result.get("reason") != "no_candidate_id")
                or (
                    inventory_result
                    and (
                        not isinstance(result.get("project_id"), str)
                        or not isinstance(result.get("complete"), bool)
                        or not isinstance(title_hashes, list)
                        or len(title_hashes) > 100
                        or len(set(title_hashes)) != len(title_hashes)
                        or not all(
                            isinstance(item, str)
                            and re.fullmatch(r"[0-9a-f]{64}", item) is not None
                            for item in title_hashes
                        )
                    )
                )
            ):
                raise ValueError("reconciliation probe result contract is invalid")
            if (
                artifact_payload["tool"] != tool
                or artifact_payload["invoked_at"] != timestamp
                or artifact_payload["response_id"] != response_id
                or artifact_payload["status"] != status
            ):
                raise ValueError("reconciliation probe artifact content does not match its declaration")
            result_hash = hashlib.sha256(
                json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if probe["result_sha256"] != result_hash:
                raise ValueError("reconciliation result hash does not match the parsed result")
            records.append(ArtifactRecord(artifact.path, artifact.sha256, artifact.mime))
            checks.append({
                "tool": tool, "invoked_at": timestamp, "response_id": response_id,
                "status": status, "result_sha256": result_hash,
                "target_found": result["target_found"],
                **({"reason": result["reason"]} if "reason" in result else {}),
                **(
                    {
                        "project_id": result["project_id"],
                        "complete": result["complete"],
                        "title_hashes": tuple(result["title_hashes"]),
                    }
                    if inventory_result
                    else {}
                ),
            })
        if set(tools) != {"get_project", "list_screens", "get_screen"} or len(set(tools)) != 3:
            raise ValueError("reconciliation requires get_project, list_screens, and get_screen")
        contracts = {
            check["tool"]: (check["status"], check["target_found"])
            for check in checks
        }
        if outcome == "applied":
            valid_contract = all(contracts[tool] == ("found", True) for tool in contracts)
        else:
            legacy_contract = (
                contracts.get("get_project") == ("found", True)
                and contracts.get("list_screens") == ("not_found", False)
                and contracts.get("get_screen") == ("not_found", False)
            )
            manifest_target = self._manifest(run).get("reconciliation_target")
            list_check = next(
                (check for check in checks if check["tool"] == "list_screens"),
                {},
            )
            expected_title_hash = (
                hashlib.sha256(manifest_target["expected_title"].strip().encode("utf-8")).hexdigest()
                if isinstance(manifest_target, dict)
                and isinstance(manifest_target.get("expected_title"), str)
                else None
            )
            no_candidate_contract = (
                isinstance(manifest_target, dict)
                and contracts.get("get_project") == ("found", True)
                and contracts.get("list_screens") == ("found", False)
                and contracts.get("get_screen") == ("skipped", False)
                and list_check.get("project_id") == manifest_target.get("project_id")
                and list_check.get("complete") is True
                and expected_title_hash not in list_check.get("title_hashes", ())
                and next(
                    (check.get("reason") for check in checks if check["tool"] == "get_screen"),
                    None,
                ) == "no_candidate_id"
            )
            valid_contract = legacy_contract or no_candidate_contract
        if not valid_contract:
            raise ValueError(f"reconciliation {outcome} probe contract is contradictory")
        return tuple(records), tuple(checks)

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
                if attempts >= 3:
                    run = self.store.update_states(
                        run,
                        (RunState.BLOCKED,),
                        manifest_updates={
                            "reconciliation_attempts": attempts,
                            "blocked_reason": "three unresolved reconciliation attempts",
                        },
                    )
                else:
                    run = self.store.update_states(
                        run,
                        (),
                        manifest_updates={"reconciliation_attempts": attempts},
                    )
                return RunStatus(run_id, run.state, 3 if run.state == RunState.RECONCILING else 1, _ACTIONS[run.state], reconciliation_attempts=attempts)
            expected = _ACTIONS[run.state].expected_evidence_step
            if raw.get("step") != expected:
                return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], (f"expected {expected} evidence",))
            target = raw.get("target")
            if target is not None:
                if not isinstance(target, dict) or set(target) != {"project_id", "expected_title"}:
                    return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], ("unknown write target is invalid",))
                project_id = target.get("project_id")
                expected_title = target.get("expected_title")
                if (
                    not isinstance(project_id, str)
                    or not project_id.isdigit()
                    or not isinstance(expected_title, str)
                    or not expected_title.strip()
                    or len(expected_title) > 256
                ):
                    return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], ("unknown write target is invalid",))
                try:
                    reject_sensitive_content(target)
                except EvidenceError:
                    return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], ("unknown write target is invalid",))
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
            source_state = run.state
            committed_unknown = self._latest_unknown_receipt(run, str(raw["step"]))
            if committed_unknown is None or committed_unknown[0] != run.latest_receipt_sha256:
                run = self.store.append_receipt(run, receipt)
            run = self.store.update_states(
                run,
                (RunState.RECONCILING,),
                manifest_updates={
                    "reconciliation_attempts": 1,
                    "reconciliation_from": source_state.value,
                    "reconciliation_step": raw["step"],
                    **({"reconciliation_target": target} if target is not None else {}),
                },
            )
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
        gate_errors = self._validate_evidence_for_state(run, run.state, evidence)
        if gate_errors:
            return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], gate_errors)
        return self._commit_evidence(run, run.state, evidence)

    def status(self, project_root: Path, run_id: str) -> RunStatus:
        run = self.store.load(project_root, run_id)
        verification = self.store.verify_chain(run)
        return RunStatus(run_id, run.state, 0 if verification.valid else 1, _ACTIONS[run.state], verification.errors, self._attempts(run))

    def recover(self, project_root: Path, run_id: str, reason: str) -> RunStatus:
        """Resume an exhausted reconciliation only after an explicit recorded reason."""

        reason = self._sanitize_reason(reason)
        run = self.store.load(project_root, run_id)
        if run.state != RunState.BLOCKED:
            raise InvalidTransition("only a blocked run can be recovered")
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

    def reconcile(self, project_root: Path, run_id: str, evidence_path: Path) -> RunStatus:
        """Resolve an unknown write from the required read probes before exhaustion."""

        run = self.store.load(project_root, run_id)
        if run.state != RunState.RECONCILING:
            raise InvalidTransition("only a reconciling run accepts reconciliation evidence")
        verification = self.store.verify_chain(run)
        if not verification.valid:
            return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], verification.errors, self._attempts(run))
        raw = json.loads(evidence_path.read_text(encoding="utf-8"))
        manifest = self._manifest(run)
        if raw.get("schema_version") != 1 or raw.get("step") != manifest.get("reconciliation_step"):
            raise ValueError("reconciliation evidence does not match the unknown write step")
        reconciliation = raw.get("reconciliation")
        if not isinstance(reconciliation, dict):
            raise ValueError("reconciliation evidence requires a reconciliation object")
        outcome = reconciliation.get("outcome")
        if outcome not in {"not_applied", "applied"}:
            raise ValueError("reconciliation outcome must be not_applied or applied")
        unknown_receipt = self._latest_unknown_receipt(run, manifest["reconciliation_step"])
        if unknown_receipt is None:
            raise ValueError("reconciliation cannot find the current unknown write receipt")
        unknown_receipt_hash, unknown_payload = unknown_receipt
        try:
            unknown_ended_at = datetime.fromisoformat(str(unknown_payload["ended_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError) as error:
            raise ValueError("unknown write receipt timestamp is invalid") from error
        probe_records, probe_checks = self._validate_reconciliation_probes(
            run,
            reconciliation.get("read_probes"),
            outcome=outcome,
            unknown_ended_at=unknown_ended_at,
        )
        reason = self._sanitize_reason(reconciliation.get("reason"))
        reconciliation_receipt = Receipt.passed(
            run.run_id,
            run.page_id,
            "reconciliation",
            inputs=probe_records,
            checks=probe_checks,
            attempt=self._attempts(run),
        )
        reconciliation_receipt_hash = self._matching_receipt_hash(
            run,
            reconciliation_receipt,
            previous_receipt_sha256=unknown_receipt_hash,
        )
        if outcome == "not_applied":
            if reconciliation_receipt_hash is None:
                run = self.store.append_receipt(run, reconciliation_receipt)
                reconciliation_receipt_hash = run.latest_receipt_sha256
                manifest = self._manifest(run)
            restored = self._restore_reconciliation(run, manifest, reason, outcome)
            return RunStatus(run_id, restored.state, 0, _ACTIONS[restored.state])

        expected = manifest["reconciliation_step"]
        evidence = ExternalEvidence.from_dict(raw, expected)
        errors = evidence.verify_artifacts(run.path)
        if errors:
            return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], errors, self._attempts(run))
        try:
            source_state = RunState(manifest["reconciliation_from"])
        except (KeyError, ValueError) as error:
            raise InvalidTransition("reconciliation has no valid source state") from error
        gate_errors = self._validate_evidence_for_state(run, source_state, evidence)
        if gate_errors:
            return RunStatus(run_id, run.state, 1, _ACTIONS[run.state], gate_errors, self._attempts(run))
        if reconciliation_receipt_hash is None:
            run = self.store.append_receipt(run, reconciliation_receipt)
            reconciliation_receipt_hash = run.latest_receipt_sha256
        return self._commit_evidence(
            run,
            source_state,
            evidence,
            manifest_updates={
                "reconciliation_attempts": 0,
                "last_reconciliation_outcome": outcome,
                "last_reconciliation_reason": reason,
            },
            required_previous_receipt_sha256=reconciliation_receipt_hash,
        )

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
