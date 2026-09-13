import json
import hashlib
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from stitch_harness.orchestrator import ApprovalDecision, ApprovalRequired, Harness
from stitch_harness.state import RunState
from stitch_harness.storage import ArtifactRecord, Receipt


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
            RunState.ART_GENERATED,
            RunState.ART_ACCEPTED,
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

    def awaiting_approval_with_artifacts(self):
        started = self.harness.start(self.project, "login", now=FIXED_TIME)
        run = self.harness.store.load(self.project, started.run_id)
        artifacts = {
            "artifacts/art.png": b"accepted-art",
            "artifacts/roundtrip.html": b"<main>accepted</main>",
            "artifacts/stitch-final.png": b"stitch-render",
            "comparison/side-by-side.png": b"side-by-side",
            "comparison/overlay.png": b"overlay",
            "comparison/diff-heatmap.png": b"difference",
        }
        for relative, content in artifacts.items():
            path = run.path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        run = self.harness.store.update_state(run, RunState.STITCH_GENERATED)
        run = self.harness.store.update_state(run, RunState.SOURCE_ACCEPTED)
        art = ArtifactRecord.from_path(run.path, run.path / "artifacts/art.png", "image/png")
        run = self.harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "imagegen", outputs=[art]))
        run = self.harness.store.update_state(run, RunState.ART_GENERATED)
        run = self.harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "ocr"))
        run = self.harness.store.update_state(run, RunState.ART_ACCEPTED)
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
            ArtifactRecord.from_path(run.path, run.path / relative, "image/png")
            for relative in (
                "comparison/side-by-side.png",
                "comparison/overlay.png",
                "comparison/diff-heatmap.png",
            )
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
        self.assertEqual(status.state, RunState.PREFLIGHT_PASSED)
        self.assertEqual(status.next_action.kind, "stitch.reconcile-read")

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
                    "result": {"render_metadata": {"width": 1350, "height": 768, "scale": 1}},
                }
            ),
            encoding="utf-8",
        )

        status = self.harness.resume(self.project, started.run_id, evidence)

        self.assertEqual(status.state, RunState.SOURCE_ACCEPTED)
        self.assertEqual(status.next_action.kind, "imagegen.generate")

    def test_automatic_scores_cannot_approve(self):
        started = self.harness.start(self.project, "login", now=FIXED_TIME)
        run = self.harness.store.load(self.project, started.run_id)
        for state in (
            RunState.STITCH_GENERATED,
            RunState.SOURCE_ACCEPTED,
            RunState.ART_GENERATED,
            RunState.ART_ACCEPTED,
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

    def test_imagegen_wrong_canvas_does_not_advance(self):
        run = self.run_at_state(RunState.SOURCE_ACCEPTED)
        evidence = self.evidence_for(run, "imagegen", {"status": "generated"}, width=1280, height=768)

        status = self.harness.resume(self.project, run.run_id, evidence)

        self.assertEqual(status.state, RunState.SOURCE_ACCEPTED)
        self.assertEqual(status.exit_code, 1)
        self.assertIn("1350", " ".join(status.errors))

    def test_ocr_missing_copy_does_not_advance(self):
        run = self.run_at_state(RunState.ART_GENERATED)
        evidence = self.evidence_for(run, "ocr", {"texts": ["WeKefu Desktop"]})

        status = self.harness.resume(self.project, run.run_id, evidence)

        self.assertEqual(status.state, RunState.ART_GENERATED)
        self.assertEqual(status.exit_code, 1)
        self.assertIn("统一接待多个客户渠道", " ".join(status.errors))

    def test_failed_editability_probe_does_not_advance(self):
        run = self.run_at_state(RunState.ROUNDTRIPPED)
        evidence = self.evidence_for(run, "editability", {"editable": False, "restored": False})

        status = self.harness.resume(self.project, run.run_id, evidence)

        self.assertEqual(status.state, RunState.ROUNDTRIPPED)
        self.assertEqual(status.exit_code, 1)

    def test_flattened_roundtrip_does_not_advance(self):
        run = self.run_at_state(RunState.ART_ACCEPTED)
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
                    "result": {"render_metadata": {"width": 1350, "height": 768, "scale": 1}},
                }
            ),
            encoding="utf-8",
        )

        status = self.harness.resume(self.project, run.run_id, evidence)

        self.assertEqual(status.state, RunState.ART_ACCEPTED)
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
