import json
import hashlib
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from stitch_harness.orchestrator import ArtEnhancementDecision, ApprovalDecision, ApprovalRequired, Harness
from stitch_harness.evidence_writer import EvidenceWriter
from stitch_harness.cli import main
from stitch_harness.state import RunState
from stitch_harness.storage import ArtifactRecord, Receipt, RunStore


FIXTURE = Path(__file__).parent / "fixtures" / "page-spec.json"
FIXED_TIME = datetime(2026, 9, 14, 0, 0, tzinfo=UTC)


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        specs = self.project / ".stitch" / "specs"
        specs.mkdir(parents=True)
        shutil.copy2(FIXTURE, specs / "login.json")
        self.harness = Harness(preflight=lambda _project: ())

    def tearDown(self):
        self.temp.cleanup()

    def run_at_state(self, target):
        started = self.harness.start(self.project, "login", now=FIXED_TIME)
        run = self.harness.store.load(self.project, started.run_id)
        ordered = [
            RunState.STITCH_GENERATED,
            RunState.SOURCE_ACCEPTED,
            RunState.AWAITING_ART_DECISION,
            RunState.ART_ENHANCEMENT_APPROVED,
            RunState.ART_GENERATED,
            RunState.ART_ACCEPTED,
            RunState.SEMANTIC_NORMALIZED,
            RunState.ROUNDTRIPPED,
            RunState.EDITABILITY_VERIFIED,
        ]
        if target == RunState.PREFLIGHT_PASSED:
            return run
        for state in ordered:
            run = self.harness.store.update_state(run, state)
            if state == target:
                return run
        raise AssertionError(f"unsupported test state: {target}")

    def evidence_for(self, run, step, result, *, width=None, height=None):
        artifact = run.path / "artifacts" / f"{step}.json"
        artifact.write_text(json.dumps(result), encoding="utf-8")
        item = {
            "path": f"artifacts/{step}.json",
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "mime": "application/json",
        }
        if width is not None:
            item["width"] = width
        if height is not None:
            item["height"] = height
        evidence = self.project / f"{step}-evidence.json"
        evidence.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "step": step,
                    "provider": {"name": "test-provider", "tool": step, "model": "1"},
                    "invoked_at": "2026-09-14T00:00:01Z",
                    "source_artifacts": [],
                    "artifacts": [item],
                    "result": result,
                }
            ),
            encoding="utf-8",
        )
        return evidence

    def awaiting_approval_with_artifacts(
        self,
        *,
        comparison_mime="image/png",
        comparison_paths=(
            "comparison/side-by-side.png",
            "comparison/overlay.png",
            "comparison/diff-heatmap.png",
        ),
    ):
        started = self.harness.start(self.project, "login", now=FIXED_TIME)
        run = self.harness.store.load(self.project, started.run_id)
        artifacts = {
            "artifacts/art.png": b"accepted-art",
            "artifacts/roundtrip.html": b"<main>accepted</main>",
            "artifacts/stitch-final.png": b"stitch-render",
        }
        for index, relative in enumerate(comparison_paths):
            artifacts[relative] = f"comparison-{index}".encode()
        for relative, content in artifacts.items():
            path = run.path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        run = self.harness.store.update_state(run, RunState.STITCH_GENERATED)
        run = self.harness.store.update_state(run, RunState.SOURCE_ACCEPTED)
        run = self.harness.store.update_state(run, RunState.AWAITING_ART_DECISION)
        run = self.harness.store.append_receipt(
            run,
            Receipt.passed(
                run.run_id,
                run.page_id,
                "art-decision",
                checks=({"decision": "enhance", "source": "explicit-user-response"},),
            ),
        )
        run = self.harness.store.update_states(
            run,
            (RunState.ART_ENHANCEMENT_APPROVED,),
            manifest_updates={"art_mode": "enhance"},
        )
        art = ArtifactRecord.from_path(run.path, run.path / "artifacts/art.png", "image/png")
        run = self.harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "imagegen", outputs=[art]))
        run = self.harness.store.update_state(run, RunState.ART_GENERATED)
        run = self.harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "ocr"))
        run = self.harness.store.update_state(run, RunState.ART_ACCEPTED)
        run = self.harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "stitch.normalize"))
        run = self.harness.store.update_state(run, RunState.SEMANTIC_NORMALIZED)
        roundtrip = [
            ArtifactRecord.from_path(run.path, run.path / "artifacts/roundtrip.html", "text/html"),
            ArtifactRecord.from_path(run.path, run.path / "artifacts/stitch-final.png", "image/png"),
        ]
        run = self.harness.store.append_receipt(
            run, Receipt.passed(run.run_id, run.page_id, "stitch.roundtrip", outputs=roundtrip)
        )
        run = self.harness.store.update_state(run, RunState.ROUNDTRIPPED)
        run = self.harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "editability"))
        run = self.harness.store.update_state(run, RunState.EDITABILITY_VERIFIED)
        comparisons = [
            ArtifactRecord.from_path(run.path, run.path / relative, comparison_mime)
            for relative in comparison_paths
        ]
        run = self.harness.store.append_receipt(
            run, Receipt.passed(run.run_id, run.page_id, "visual-judge", outputs=comparisons)
        )
        run = self.harness.store.update_state(run, RunState.COMPARISON_ACCEPTED)
        return self.harness.store.update_state(run, RunState.AWAITING_USER_APPROVAL)

    def test_start_stops_after_preflight_and_requests_stitch_generation(self):
        status = self.harness.start(self.project, "login", now=FIXED_TIME)

        self.assertEqual(status.state, RunState.PREFLIGHT_PASSED)
        self.assertEqual(status.next_action.kind, "stitch.generate")
        self.assertEqual(status.exit_code, 0)

    def test_unknown_write_requires_read_reconciliation(self):
        started = self.harness.start(self.project, "login", now=FIXED_TIME)
        evidence = self.project / "unknown.json"
        evidence.write_text(
            json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}),
            encoding="utf-8",
        )

        status = self.harness.resume(self.project, started.run_id, evidence)

        self.assertEqual(status.exit_code, 3)
        self.assertEqual(status.state, RunState.RECONCILING)
        self.assertEqual(status.reconciliation_attempts, 1)
        self.assertEqual(status.next_action.kind, "stitch.reconcile-read")

    def test_reconciling_state_and_metadata_survive_one_manifest_commit_crash(self):
        class CrashAfterReconcilingCommit(RunStore):
            def update_states(self, run, targets, *, manifest_updates=None):
                targets = tuple(targets)
                updated = super().update_states(run, targets, manifest_updates=manifest_updates)
                if targets and targets[-1] == RunState.RECONCILING:
                    raise OSError("simulated power loss after reconciliation commit")
                return updated

        harness = Harness(preflight=lambda _project: (), store=CrashAfterReconcilingCommit())
        started = harness.start(self.project, "login", now=FIXED_TIME)
        evidence = self.project / "unknown-atomic.json"
        evidence.write_text(
            json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(OSError, "power loss"):
            harness.resume(self.project, started.run_id, evidence)

        manifest = json.loads(
            (self.project / ".stitch/runs" / started.run_id / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["state"], RunState.RECONCILING.value)
        self.assertEqual(manifest["reconciliation_from"], RunState.PREFLIGHT_PASSED.value)
        self.assertEqual(manifest["reconciliation_step"], "stitch.generate")
        self.assertEqual(manifest["reconciliation_attempts"], 1)

    def test_unknown_receipt_without_transition_metadata_recovers_idempotently(self):
        started = self.harness.start(self.project, "login", now=FIXED_TIME)
        run = self.harness.store.load(self.project, started.run_id)
        timestamp = datetime.now(UTC).isoformat()
        run = self.harness.store.append_receipt(
            run,
            Receipt(
                run.run_id,
                run.page_id,
                "stitch.generate",
                1,
                "unknown",
                timestamp,
                timestamp,
                error="external write result is unknown",
            ),
        )
        evidence = self.project / "unknown-retry.json"
        evidence.write_text(
            json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}),
            encoding="utf-8",
        )

        status = self.harness.resume(self.project, started.run_id, evidence)

        self.assertEqual(status.state, RunState.RECONCILING)
        self.assertEqual(status.reconciliation_attempts, 1)
        receipts = list((run.path / "receipts").glob("*.json"))
        self.assertEqual(len(receipts), 2)
        self.assertEqual(
            sum(json.loads(path.read_text(encoding="utf-8"))["result"] == "unknown" for path in receipts),
            1,
        )
        manifest = json.loads((run.path / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["reconciliation_from"], RunState.PREFLIGHT_PASSED.value)
        self.assertEqual(manifest["reconciliation_step"], "stitch.generate")

    def test_stitch_evidence_is_html_gated_before_imagegen(self):
        started = self.harness.start(self.project, "login", now=FIXED_TIME)
        run = self.harness.store.load(self.project, started.run_id)
        html = run.path / "artifacts" / "source.html"
        image = run.path / "artifacts" / "source.png"
        shutil.copy2(Path(__file__).parent / "fixtures" / "login-valid.html", html)
        shutil.copy2(Path(__file__).parent / "fixtures" / "images" / "stitch.png", image)
        evidence = self.project / "stitch-evidence.json"
        evidence.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "step": "stitch.generate",
                    "provider": {"name": "google-stitch", "tool": "generate_screen_from_text", "model": "server"},
                    "invoked_at": "2026-09-14T00:00:01Z",
                    "source_artifacts": [],
                    "artifacts": [
                        {"path": "artifacts/source.html", "sha256": hashlib.sha256(html.read_bytes()).hexdigest(), "mime": "text/html"},
                        {"path": "artifacts/source.png", "sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "mime": "image/png", "width": 1350, "height": 768},
                    ],
                    "result": {"render_metadata": {"width": 1350, "height": 768, "scale": 1}, "screen": {"deviceType": "DESKTOP", "width": 1350, "height": 768}},
                }
            ),
            encoding="utf-8",
        )

        status = self.harness.resume(self.project, started.run_id, evidence)

        self.assertEqual(status.state, RunState.AWAITING_ART_DECISION)
        self.assertEqual(status.next_action.kind, "await-art-enhancement-decision")

    def test_art_enhancement_decision_requires_an_exact_user_response(self):
        for decision, expected_state, expected_action in (
            ("enhance", RunState.ART_ENHANCEMENT_APPROVED, "imagegen.generate"),
            ("keep_stitch", RunState.STITCH_ONLY_SELECTED, "stitch.editability-probe"),
            ("cancel", RunState.CANCELLED, "cancelled"),
        ):
            with self.subTest(decision=decision), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                specs = project / ".stitch" / "specs"
                specs.mkdir(parents=True)
                shutil.copy2(FIXTURE, specs / "login.json")
                harness = Harness(preflight=lambda _project: ())
                started = harness.start(project, "login", now=FIXED_TIME)
                run = harness.store.load(project, started.run_id)
                run = harness.store.update_state(run, RunState.STITCH_GENERATED)
                run = harness.store.update_state(run, RunState.SOURCE_ACCEPTED)
                run = harness.store.update_state(run, RunState.AWAITING_ART_DECISION)
                status = harness.decide_art(
                    project,
                    run.run_id,
                    ArtEnhancementDecision(decision),
                )
                self.assertEqual(status.state, expected_state)
                self.assertEqual(status.next_action.kind, expected_action)

    def test_ambiguous_confirmation_cannot_be_mapped_to_an_art_decision(self):
        run = self.run_at_state(RunState.SOURCE_ACCEPTED)
        run = self.harness.store.update_state(run, RunState.AWAITING_ART_DECISION)

        for response in ("确认", "做按", "可以", "继续", "user"):
            with self.subTest(response=response), self.assertRaises(ApprovalRequired):
                self.harness.decide_art(
                    self.project,
                    run.run_id,
                    ArtEnhancementDecision(response),
                )

    def test_imagegen_evidence_is_rejected_before_art_enhancement_choice(self):
        run = self.run_at_state(RunState.SOURCE_ACCEPTED)
        run = self.harness.store.update_state(run, RunState.AWAITING_ART_DECISION)
        evidence = self.evidence_for(run, "imagegen", {"status": "generated"}, width=1350, height=768)

        status = self.harness.resume(self.project, run.run_id, evidence)

        self.assertEqual(status.state, RunState.AWAITING_ART_DECISION)
        self.assertEqual(status.exit_code, 1)

    def test_keep_stitch_path_verifies_source_editability_and_binds_source_for_approval(self):
        started = self.harness.start(self.project, "login", now=FIXED_TIME)
        run = self.harness.store.load(self.project, started.run_id)
        source_html = run.path / "artifacts/source.html"
        source_render = run.path / "artifacts/source.png"
        source_html.write_text("<main>source</main>", encoding="utf-8")
        source_render.write_bytes(b"source-render")
        run = self.harness.store.append_receipt(
            run,
            Receipt.passed(
                run.run_id,
                run.page_id,
                "stitch.generate",
                outputs=(
                    ArtifactRecord.from_path(run.path, source_html, "text/html"),
                    ArtifactRecord.from_path(run.path, source_render, "image/png"),
                ),
            ),
        )
        run = self.harness.store.update_state(run, RunState.STITCH_GENERATED)
        run = self.harness.store.update_state(run, RunState.SOURCE_ACCEPTED)
        run = self.harness.store.update_state(run, RunState.AWAITING_ART_DECISION)
        status = self.harness.decide_art(
            self.project,
            run.run_id,
            ArtEnhancementDecision("keep_stitch"),
        )
        run = self.harness.store.load(self.project, status.run_id)
        edited_html = run.path / "artifacts/edited.html"
        restored_html = run.path / "artifacts/restored.html"
        edited_render = run.path / "artifacts/edited.png"
        restored_render = run.path / "artifacts/restored.png"
        edited_html.write_text("<main>edited</main>", encoding="utf-8")
        restored_html.write_bytes(source_html.read_bytes())
        edited_render.write_bytes(b"edited-render")
        restored_render.write_bytes(source_render.read_bytes())
        evidence = EvidenceWriter(run.path).editability(
            source_html,
            edited_html,
            restored_html,
            source_render,
            edited_render,
            restored_render,
        )

        resolved = self.harness.resume(self.project, run.run_id, evidence)

        self.assertEqual(resolved.state, RunState.AWAITING_USER_APPROVAL)
        self.assertEqual(
            self.harness.store.required_approval_artifacts(
                self.harness.store.load(self.project, run.run_id)
            ),
            {
                "artifacts/source.html": hashlib.sha256(source_html.read_bytes()).hexdigest(),
                "artifacts/source.png": hashlib.sha256(source_render.read_bytes()).hexdigest(),
            },
        )

    def test_art_decision_cli_records_the_explicit_user_choice(self):
        started = self.harness.start(self.project, "login", now=FIXED_TIME)
        run = self.harness.store.load(self.project, started.run_id)
        run = self.harness.store.update_state(run, RunState.STITCH_GENERATED)
        run = self.harness.store.update_state(run, RunState.SOURCE_ACCEPTED)
        self.harness.store.update_state(run, RunState.AWAITING_ART_DECISION)

        code = main([
            "art-decision",
            "--project", str(self.project),
            "--run", run.run_id,
            "--user-response", "enhance",
        ])

        self.assertEqual(code, 0)
        loaded = self.harness.store.load(self.project, run.run_id)
        self.assertEqual(loaded.state, RunState.ART_ENHANCEMENT_APPROVED)

    def test_art_decision_cli_rejects_the_removed_source_override(self):
        code = main([
            "art-decision",
            "--project", str(self.project),
            "--run", "unused",
            "--decision", "enhance",
            "--source", "user",
        ])

        self.assertNotEqual(code, 0)

    def test_automatic_scores_cannot_approve(self):
        started = self.harness.start(self.project, "login", now=FIXED_TIME)
        run = self.harness.store.load(self.project, started.run_id)
        for state in (
            RunState.STITCH_GENERATED,
            RunState.SOURCE_ACCEPTED,
            RunState.AWAITING_ART_DECISION,
            RunState.ART_ENHANCEMENT_APPROVED,
            RunState.ART_GENERATED,
            RunState.ART_ACCEPTED,
            RunState.SEMANTIC_NORMALIZED,
            RunState.ROUNDTRIPPED,
            RunState.EDITABILITY_VERIFIED,
            RunState.COMPARISON_ACCEPTED,
            RunState.AWAITING_USER_APPROVAL,
        ):
            run = self.harness.store.update_state(run, state)

        with self.assertRaises(ApprovalRequired):
            self.harness.approve(
                self.project,
                run.run_id,
                ApprovalDecision(decision="approved", source="visual-judge", artifact_hashes={}),
            )

    def test_approval_rejects_incomplete_required_artifact_set(self):
        run = self.awaiting_approval_with_artifacts()
        required = self.harness.store.required_approval_artifacts(run)
        required.pop("comparison/overlay.png")

        with self.assertRaisesRegex(ApprovalRequired, "exact required artifact set"):
            self.harness.approve(
                self.project,
                run.run_id,
                ApprovalDecision("approved", "user", required),
            )

    def test_modified_approved_artifact_invalidates_approval(self):
        run = self.awaiting_approval_with_artifacts()
        required = self.harness.store.required_approval_artifacts(run)
        approved = self.harness.approve(
            self.project,
            run.run_id,
            ApprovalDecision("approved", "user", required),
        )
        loaded = self.harness.store.load(self.project, approved.run_id)
        (loaded.path / "artifacts/art.png").write_bytes(b"modified-after-approval")

        verification = self.harness.store.verify_approval(loaded)

        self.assertFalse(verification.valid)
        self.assertTrue(verification.approval_invalidated)
        self.assertIn("approved artifact hash mismatch", " ".join(verification.errors))

    def test_required_comparisons_must_have_image_mime(self):
        run = self.awaiting_approval_with_artifacts(comparison_mime="text/plain")

        with self.assertRaisesRegex(ValueError, "image MIME"):
            self.harness.store.required_approval_artifacts(run)

    def test_required_comparisons_must_use_the_three_expected_paths(self):
        run = self.awaiting_approval_with_artifacts(
            comparison_paths=(
                "comparison/side-by-side.png",
                "artifacts/overlay.png",
                "comparison/diff-heatmap.png",
            )
        )

        with self.assertRaisesRegex(ValueError, "three comparison images"):
            self.harness.store.required_approval_artifacts(run)

    def test_imagegen_wrong_canvas_does_not_advance(self):
        run = self.run_at_state(RunState.ART_ENHANCEMENT_APPROVED)
        evidence = self.evidence_for(run, "imagegen", {"status": "generated"}, width=1280, height=768)

        status = self.harness.resume(self.project, run.run_id, evidence)

        self.assertEqual(status.state, RunState.ART_ENHANCEMENT_APPROVED)
        self.assertEqual(status.exit_code, 1)
        self.assertIn("1350", " ".join(status.errors))

    def test_ocr_missing_copy_does_not_advance(self):
        run = self.run_at_state(RunState.ART_GENERATED)
        evidence = self.evidence_for(run, "ocr", {"texts": ["WeKefu Desktop"]})

        status = self.harness.resume(self.project, run.run_id, evidence)

        self.assertEqual(status.state, RunState.ART_GENERATED)
        self.assertEqual(status.exit_code, 1)
        self.assertIn("统一接待多个客户渠道", " ".join(status.errors))

    def test_semantic_normalization_evidence_is_verified_before_roundtrip(self):
        run = self.run_at_state(RunState.ART_ACCEPTED)
        raw = run.path / "artifacts/raw-roundtrip.html"
        normalized = run.path / "artifacts/normalized-roundtrip.html"
        source = (Path(__file__).parent / "fixtures/login-valid.html").read_text(encoding="utf-8")
        raw.write_text(source.replace('data-purpose="headline"', 'data-purpose="old-headline"'), encoding="utf-8")
        normalized.write_text(source, encoding="utf-8")
        evidence = EvidenceWriter(run.path).semantic_normalization(
            source_html=raw,
            normalized_html=normalized,
            purpose_mapping={"old-headline": "headline"},
            render_metadata={"width": 1350, "height": 768, "scale": 1},
        )

        status = self.harness.resume(self.project, run.run_id, evidence)

        self.assertEqual(status.state, RunState.SEMANTIC_NORMALIZED)
        self.assertEqual(status.next_action.kind, "stitch.roundtrip")

    def test_failed_editability_probe_does_not_advance(self):
        run = self.run_at_state(RunState.ROUNDTRIPPED)
        evidence = self.evidence_for(run, "editability", {"editable": False, "restored": False})

        status = self.harness.resume(self.project, run.run_id, evidence)

        self.assertEqual(status.state, RunState.ROUNDTRIPPED)
        self.assertEqual(status.exit_code, 1)

    def test_editability_result_hashes_must_match_six_verified_semantic_artifacts(self):
        run = self.run_at_state(RunState.ROUNDTRIPPED)
        roles = {
            "before_html": ("before.html", b"before", "text/html"),
            "edited_html": ("edited.html", b"edited", "text/html"),
            "restored_html": ("restored.html", b"before", "text/html"),
            "before_render": ("before.png", b"before-render", "image/png"),
            "edited_render": ("edited.png", b"edited-render", "image/png"),
            "restored_render": ("restored.png", b"before-render", "image/png"),
        }
        artifacts = []
        hashes = {}
        for role, (name, body, mime) in roles.items():
            path = run.path / "artifacts" / name
            path.write_bytes(body)
            digest = hashlib.sha256(body).hexdigest()
            hashes[role] = digest
            artifacts.append({"path": f"artifacts/{name}", "sha256": digest, "mime": mime, "semantic_role": role})
        hashes["before_html"] = hashes["restored_html"] = "0" * 64
        evidence = self.project / "editability-tampered.json"
        evidence.write_text(json.dumps({
            "schema_version": 1, "step": "editability",
            "provider": {"name": "google-stitch", "tool": "edit-restore-probe", "model": "server"},
            "invoked_at": "2026-09-14T00:00:01Z", "source_artifacts": [], "artifacts": artifacts,
            "result": {"editable": True, "restored": True, "hashes": hashes},
        }), encoding="utf-8")

        status = self.harness.resume(self.project, run.run_id, evidence)

        self.assertEqual(status.state, RunState.ROUNDTRIPPED)
        self.assertEqual(status.exit_code, 1)
        self.assertIn("artifact hashes", " ".join(status.errors))

    def test_flattened_roundtrip_does_not_advance(self):
        run = self.run_at_state(RunState.SEMANTIC_NORMALIZED)
        html = run.path / "artifacts" / "roundtrip.html"
        image = run.path / "artifacts" / "roundtrip.png"
        shutil.copy2(Path(__file__).parent / "fixtures" / "login-flattened.html", html)
        shutil.copy2(Path(__file__).parent / "fixtures" / "images" / "stitch.png", image)
        evidence = self.project / "roundtrip-evidence.json"
        evidence.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "step": "stitch.roundtrip",
                    "provider": {"name": "google-stitch", "tool": "upload", "model": "server"},
                    "invoked_at": "2026-09-14T00:00:01Z",
                    "source_artifacts": [],
                    "artifacts": [
                        {"path": "artifacts/roundtrip.html", "sha256": hashlib.sha256(html.read_bytes()).hexdigest(), "mime": "text/html"},
                        {"path": "artifacts/roundtrip.png", "sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "mime": "image/png", "width": 1350, "height": 768},
                    ],
                    "result": {"render_metadata": {"width": 1350, "height": 768, "scale": 1}, "screen": {"deviceType": "DESKTOP", "width": 1350, "height": 768}},
                }
            ),
            encoding="utf-8",
        )

        status = self.harness.resume(self.project, run.run_id, evidence)

        self.assertEqual(status.state, RunState.SEMANTIC_NORMALIZED)
        self.assertEqual(status.exit_code, 1)
        self.assertIn("flattened", " ".join(status.errors))

    def test_low_visual_score_does_not_advance_to_user_approval(self):
        run = self.run_at_state(RunState.EDITABILITY_VERIFIED)
        evidence = self.evidence_for(
            run,
            "visual-judge",
            {"layout_score": 0.98, "scores": {"hierarchy": 5, "density": 3, "color": 5, "component_quality": 5, "completion": 5}},
        )

        status = self.harness.resume(self.project, run.run_id, evidence)

        self.assertEqual(status.state, RunState.EDITABILITY_VERIFIED)
        self.assertEqual(status.exit_code, 1)
        self.assertIn("density", " ".join(status.errors))


if __name__ == "__main__":
    unittest.main()
