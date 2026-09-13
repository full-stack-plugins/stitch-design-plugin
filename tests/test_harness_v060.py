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
        with self.assertRaisesRegex(ValueError, "signed URL"):
            writer.ocr(
                artifact_paths=[artifact], texts=["ok"],
                metadata={"source": "https://lh3.googleusercontent.com/file?X-Goog-Signature=private"},
            )

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

    def test_compare_command_writes_three_images_and_layout_evidence(self):
        harness = Harness(preflight=lambda _: ())
        run = harness.store.start(
            self.project, PageSpec.load(self.project / ".stitch/specs/login.json"), FIXED
        )
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main([
                "compare", "--project", str(self.project), "--run", run.run_id,
                "--stitch", str(ROOT / "tests/fixtures/images/stitch.png"),
                "--art", str(ROOT / "tests/fixtures/images/art.png"),
            ])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(len(payload["files"]), 3)
        evidence = json.loads(Path(payload["evidence"]).read_text(encoding="utf-8"))
        self.assertEqual(evidence["result"]["layout_score"], payload["layout_score"])
        self.assertEqual(len(evidence["artifacts"]), 3)


if __name__ == "__main__":
    unittest.main()
