import contextlib
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from stitch_harness.cli import main
from stitch_harness.contracts import PageSpec
from stitch_harness.evidence_writer import EvidenceWriter
from stitch_harness.orchestrator import Harness
from stitch_harness.state import RunState
from stitch_harness.storage import ArtifactRecord, Receipt


ROOT = Path(__file__).resolve().parents[1]
FIXED = datetime(2026, 9, 14, tzinfo=UTC)


class Harness060Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        (self.project / ".stitch/specs").mkdir(parents=True)
        shutil.copy2(ROOT / "tests/fixtures/page-spec.json", self.project / ".stitch/specs/login.json")

    def tearDown(self):
        self.temp.cleanup()

    def comparison_ready_run(self):
        harness = Harness(preflight=lambda _: ())
        started = harness.start(self.project, "login", now=FIXED)
        run = harness.store.load(self.project, started.run_id)
        art = run.path / "artifacts/art.png"
        html = run.path / "artifacts/roundtrip.html"
        stitch = run.path / "artifacts/stitch-final.png"
        shutil.copy2(ROOT / "tests/fixtures/images/art.png", art)
        html.write_text("<main>roundtrip</main>", encoding="utf-8")
        shutil.copy2(ROOT / "tests/fixtures/images/stitch.png", stitch)
        run = harness.store.update_state(run, RunState.STITCH_GENERATED)
        run = harness.store.update_state(run, RunState.SOURCE_ACCEPTED)
        run = harness.store.append_receipt(run, Receipt.passed(
            run.run_id, run.page_id, "imagegen",
            outputs=[ArtifactRecord.from_path(run.path, art, "image/png")],
        ))
        run = harness.store.update_state(run, RunState.ART_GENERATED)
        run = harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "ocr"))
        run = harness.store.update_state(run, RunState.ART_ACCEPTED)
        run = harness.store.append_receipt(run, Receipt.passed(
            run.run_id, run.page_id, "stitch.roundtrip",
            outputs=[
                ArtifactRecord.from_path(run.path, html, "text/html"),
                ArtifactRecord.from_path(run.path, stitch, "image/png"),
            ],
        ))
        run = harness.store.update_state(run, RunState.ROUNDTRIPPED)
        run = harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "editability"))
        return harness, harness.store.update_state(run, RunState.EDITABILITY_VERIFIED)

    def test_spec_init_is_valid_and_never_overwrites(self):
        output = self.project / ".stitch/specs/new-page.json"
        self.assertEqual(main(["spec", "init", "--project", str(self.project), "--page-id", "new-page"]), 0)
        PageSpec.load(output)
        original = output.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["spec", "init", "--project", str(self.project), "--page-id", "new-page"]), 2)
        self.assertEqual(output.read_bytes(), original)

    def test_typed_evidence_writer_hashes_artifacts_and_rejects_secret_fields(self):
        run = Harness(preflight=lambda _: ()).store.start(
            self.project, PageSpec.load(self.project / ".stitch/specs/login.json"), FIXED
        )
        artifact = run.path / "artifacts/source.html"
        artifact.write_text("<main>safe</main>", encoding="utf-8")
        writer = EvidenceWriter(run.path)
        path = writer.stitch_generation(
            artifact_paths=[artifact],
            render_metadata={"width": 1350, "height": 768, "scale": 1},
            provider_resource_ids=["projects/123/screens/" + "a" * 32],
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["step"], "stitch.generate")
        self.assertEqual(payload["artifacts"][0]["sha256"], hashlib.sha256(artifact.read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError, "sensitive"):
            writer.ocr(artifact_paths=[artifact], texts=["ok"], metadata={"authorization": "secret"})
        with self.assertRaisesRegex(ValueError, "query or fragment"):
            writer.ocr(
                artifact_paths=[artifact], texts=["ok"],
                metadata={"source": "https://lh3.googleusercontent.com/file?X-Goog-Signature=private"},
            )
        for remote in ("https://example.com/file?cache=1", "https://example.com/file#fragment"):
            with self.subTest(remote=remote), self.assertRaisesRegex(ValueError, "query or fragment"):
                writer.ocr(artifact_paths=[artifact], texts=["ok"], metadata={"source": remote})

    def test_editability_writer_requires_exact_restore_hash_parity(self):
        run = Harness(preflight=lambda _: ()).store.start(
            self.project, PageSpec.load(self.project / ".stitch/specs/login.json"), FIXED
        )
        before_html = run.path / "artifacts/before.html"
        edited_html = run.path / "artifacts/edited.html"
        restored_html = run.path / "artifacts/restored.html"
        before_render = run.path / "artifacts/before.png"
        edited_render = run.path / "artifacts/edited.png"
        restored_render = run.path / "artifacts/restored.png"
        for path, data in ((before_html,b"a"),(edited_html,b"b"),(restored_html,b"a"),(before_render,b"c"),(edited_render,b"d"),(restored_render,b"c")):
            path.write_bytes(data)
        payload = json.loads(EvidenceWriter(run.path).editability(
            before_html, edited_html, restored_html, before_render, edited_render, restored_render
        ).read_text(encoding="utf-8"))
        self.assertTrue(payload["result"]["restored"])
        self.assertEqual(payload["source_artifacts"], [])
        self.assertEqual(len(payload["artifacts"]), 6)
        self.assertEqual(
            {item["semantic_role"] for item in payload["artifacts"]},
            {"before_html", "edited_html", "restored_html", "before_render", "edited_render", "restored_render"},
        )
        self.assertEqual(
            {item["semantic_role"]: item["mime"] for item in payload["artifacts"]},
            {
                "before_html": "text/html", "edited_html": "text/html", "restored_html": "text/html",
                "before_render": "image/png", "edited_render": "image/png", "restored_render": "image/png",
            },
        )
        restored_html.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "restore"):
            EvidenceWriter(run.path).editability(
                before_html, edited_html, restored_html, before_render, edited_render, restored_render
            )

    def test_imagegen_writer_records_dimensions_required_by_canvas_gate(self):
        run = Harness(preflight=lambda _: ()).store.start(
            self.project, PageSpec.load(self.project / ".stitch/specs/login.json"), FIXED
        )
        artifact = run.path / "artifacts/art.png"
        shutil.copy2(ROOT / "tests/fixtures/images/art.png", artifact)
        payload = json.loads(EvidenceWriter(run.path).imagegen(
            artifact_paths=[artifact], width=1350, height=768
        ).read_text(encoding="utf-8"))
        self.assertEqual((payload["artifacts"][0]["width"], payload["artifacts"][0]["height"]), (1350, 768))

    def test_three_unknown_attempts_block_and_explicit_recovery_records_reason(self):
        harness = Harness(preflight=lambda _: ())
        status = harness.start(self.project, "login", now=FIXED)
        evidence = self.project / "unknown.json"
        evidence.write_text(json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}), encoding="utf-8")
        for expected_attempt in (1, 2):
            status = harness.resume(self.project, status.run_id, evidence)
            self.assertEqual(status.state, RunState.RECONCILING)
            self.assertEqual(status.reconciliation_attempts, expected_attempt)
        status = harness.resume(self.project, status.run_id, evidence)
        self.assertEqual(status.state, RunState.BLOCKED)
        self.assertEqual(status.reconciliation_attempts, 3)
        recovered = harness.recover(self.project, status.run_id, "read probes confirmed no remote screen")
        self.assertEqual(recovered.state, RunState.PREFLIGHT_PASSED)
        self.assertEqual(recovered.reconciliation_attempts, 0)
        manifest = json.loads((self.project / ".stitch/runs" / status.run_id / "manifest.json").read_text())
        self.assertEqual(manifest["last_recovery_reason"], "read probes confirmed no remote screen")

    def test_reconciliation_can_resolve_not_applied_before_attempt_limit(self):
        harness = Harness(preflight=lambda _: ())
        status = harness.start(self.project, "login", now=FIXED)
        unknown = self.project / "unknown.json"
        unknown.write_text(json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}), encoding="utf-8")
        status = harness.resume(self.project, status.run_id, unknown)
        evidence = self.project / "reconciliation.json"
        evidence.write_text(json.dumps({
            "schema_version": 1,
            "step": "stitch.generate",
            "reconciliation": {
                "outcome": "not_applied",
                "reason": "all read probes confirm no matching screen",
                "read_probes": ["get_project", "list_screens", "get_screen"],
            },
        }), encoding="utf-8")

        resolved = harness.reconcile(self.project, status.run_id, evidence)

        self.assertEqual(resolved.state, RunState.PREFLIGHT_PASSED)
        self.assertEqual(resolved.reconciliation_attempts, 0)
        manifest = json.loads((self.project / ".stitch/runs" / status.run_id / "manifest.json").read_text())
        self.assertEqual(manifest["last_reconciliation_outcome"], "not_applied")

    def test_reconciliation_can_accept_applied_write_with_full_evidence(self):
        harness = Harness(preflight=lambda _: ())
        status = harness.start(self.project, "login", now=FIXED)
        unknown = self.project / "unknown.json"
        unknown.write_text(json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}), encoding="utf-8")
        status = harness.resume(self.project, status.run_id, unknown)
        run = harness.store.load(self.project, status.run_id)
        html = run.path / "artifacts/source.html"
        image = run.path / "artifacts/source.png"
        shutil.copy2(ROOT / "tests/fixtures/login-valid.html", html)
        shutil.copy2(ROOT / "tests/fixtures/images/stitch.png", image)
        evidence = self.project / "reconciled-applied.json"
        evidence.write_text(json.dumps({
            "schema_version": 1, "step": "stitch.generate",
            "provider": {"name": "google-stitch", "tool": "generate_screen_from_text", "model": "server"},
            "invoked_at": "2026-09-14T00:00:01Z", "source_artifacts": [],
            "artifacts": [
                {"path": "artifacts/source.html", "sha256": hashlib.sha256(html.read_bytes()).hexdigest(), "mime": "text/html"},
                {"path": "artifacts/source.png", "sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "mime": "image/png"},
            ],
            "result": {"render_metadata": {"width": 1350, "height": 768, "scale": 1}},
            "reconciliation": {
                "outcome": "applied", "reason": "read probes found the unique generated screen",
                "read_probes": ["get_project", "list_screens", "get_screen"],
            },
        }), encoding="utf-8")

        resolved = harness.reconcile(self.project, status.run_id, evidence)

        self.assertEqual(resolved.state, RunState.SOURCE_ACCEPTED)
        self.assertEqual(resolved.exit_code, 0)

    def test_recovery_reason_rejects_control_characters_and_sensitive_content(self):
        harness = Harness(preflight=lambda _: ())
        status = harness.start(self.project, "login", now=FIXED)
        unknown = self.project / "unknown.json"
        unknown.write_text(json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}), encoding="utf-8")
        for _ in range(3):
            status = harness.resume(self.project, status.run_id, unknown)
        for reason in ("two\nlines", "Authorization: private", "https://example.com/?token=private"):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, "reason"):
                harness.recover(self.project, status.run_id, reason)

    def test_compare_command_uses_only_receipt_bound_sources_and_receipt_inputs(self):
        harness, run = self.comparison_ready_run()
        scores = self.project / "scores.json"
        scores.write_text(json.dumps({name: 5 for name in ("hierarchy", "density", "color", "component_quality", "completion")}), encoding="utf-8")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main([
                "compare", "--project", str(self.project), "--run", run.run_id,
                "--scores", str(scores),
            ])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(len(payload["files"]), 3)
        evidence = json.loads(Path(payload["evidence"]).read_text(encoding="utf-8"))
        self.assertEqual(evidence["result"]["layout_score"], payload["layout_score"])
        self.assertEqual(len(evidence["artifacts"]), 3)
        self.assertEqual(
            {item["path"] for item in evidence["source_artifacts"]},
            {"artifacts/art.png", "artifacts/stitch-final.png"},
        )
        status = harness.resume(self.project, run.run_id, Path(payload["evidence"]))
        self.assertEqual(status.state, RunState.AWAITING_USER_APPROVAL)
        receipt = json.loads(sorted((run.path / "receipts").glob("*.json"))[-1].read_text(encoding="utf-8"))
        self.assertEqual(
            {item["path"] for item in receipt["inputs"]},
            {"artifacts/art.png", "artifacts/stitch-final.png"},
        )

    def test_compare_rejects_caller_selected_images(self):
        _, run = self.comparison_ready_run()
        with contextlib.redirect_stderr(io.StringIO()):
            code = main([
                "compare", "--project", str(self.project), "--run", run.run_id,
                "--stitch", str(ROOT / "tests/fixtures/images/stitch.png"),
                "--art", str(ROOT / "tests/fixtures/images/art.png"),
            ])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
