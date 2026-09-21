import tempfile
import unittest
from pathlib import Path
from unittest import mock

from stitch_harness.contracts import PageSpec
from stitch_harness.evidence import ExternalEvidence
from stitch_harness.visual_gate import (
    DimensionMismatch,
    compare_images,
    validate_visual_scores,
)

FIXTURES = Path(__file__).parent / "fixtures"


class VisualGateTests(unittest.TestCase):
    def setUp(self):
        self.spec = PageSpec.load(FIXTURES / "page-spec.json")

    def test_comparison_writes_three_review_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            result = compare_images(
                FIXTURES / "images" / "stitch.png",
                FIXTURES / "images" / "art.png",
                Path(directory),
            )

            self.assertEqual(
                {path.name for path in result.review_files},
                {"side-by-side.png", "overlay.png", "diff-heatmap.png"},
            )
            self.assertTrue(all(path.is_file() for path in result.review_files))

    def test_comparison_failure_publishes_no_partial_review_images(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve() / "comparison"
            original = Image.Image.save
            calls = 0

            def fail_second(image, path, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated image write failure")
                return original(image, path, *args, **kwargs)

            with mock.patch.object(Image.Image, "save", new=fail_second), self.assertRaisesRegex(OSError, "failure"):
                compare_images(FIXTURES / "images/stitch.png", FIXTURES / "images/art.png", output)

            self.assertFalse(any(output.glob("*.png")))

    def test_retry_failure_preserves_previous_complete_comparison(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve() / "comparison"
            first = compare_images(FIXTURES / "images/stitch.png", FIXTURES / "images/art.png", output)
            before = {path.name: path.read_bytes() for path in first.review_files}
            with mock.patch.object(Image.Image, "save", side_effect=OSError("simulated retry failure")), self.assertRaisesRegex(OSError, "retry failure"):
                compare_images(
                    FIXTURES / "images/stitch.png", FIXTURES / "images/art.png", output,
                    replace_existing=True,
                )
            self.assertEqual({path.name: path.read_bytes() for path in output.glob("*.png")}, before)

    def test_mismatched_dimensions_fail_before_scoring(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(DimensionMismatch):
            compare_images(
                FIXTURES / "images" / "stitch.png",
                FIXTURES / "images" / "wide.png",
                Path(directory),
            )

    def test_layout_score_ignores_texture_but_detects_geometry_shift(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = Image.new("RGB", (400, 300), "white")
            base_draw = ImageDraw.Draw(base)
            base_draw.rounded_rectangle((40, 40, 360, 120), radius=16, fill="#eef2ff", outline="#6366f1", width=2)
            base_draw.rounded_rectangle((80, 150, 360, 270), radius=16, fill="#f8fafc", outline="#94a3b8", width=2)
            textured = base.copy()
            texture_draw = ImageDraw.Draw(textured)
            for x in range(82, 358, 4):
                texture_draw.line((x, 152, x, 268), fill="#cbd5e1", width=1)
            shifted = Image.new("RGB", base.size, "white")
            shifted_draw = ImageDraw.Draw(shifted)
            shifted_draw.rounded_rectangle((40, 40, 360, 120), radius=16, fill="#eef2ff", outline="#6366f1", width=2)
            shifted_draw.rounded_rectangle((80, 180, 360, 299), radius=16, fill="#f8fafc", outline="#94a3b8", width=2)
            base.save(root / "base.png")
            textured.save(root / "textured.png")
            shifted.save(root / "shifted.png")

            texture_result = compare_images(root / "base.png", root / "textured.png", root / "texture-review")
            shift_result = compare_images(root / "base.png", root / "shifted.png", root / "shift-review")

            self.assertGreaterEqual(texture_result.layout_score, 0.95)
            self.assertGreater(texture_result.layout_score, shift_result.layout_score)

    def test_every_visual_dimension_must_reach_threshold(self):
        evidence = ExternalEvidence.from_dict(
            {
                "schema_version": 1,
                "step": "visual-judge",
                "provider": {"name": "test-judge", "tool": "score", "model": "1"},
                "invoked_at": "2026-09-14T00:00:00Z",
                "source_artifacts": [{"path": "comparison/side-by-side.png", "sha256": "a" * 64}],
                "artifacts": [{"path": "artifacts/visual.json", "sha256": "b" * 64, "mime": "application/json"}],
                "result": {
                    "scores": {"hierarchy": 5, "density": 3, "color": 5, "component_quality": 5, "completion": 5}
                },
            },
            "visual-judge",
        )

        result = validate_visual_scores(self.spec, evidence)

        self.assertFalse(result.passed)
        self.assertIn("density", " ".join(result.failures))

    def test_has_accepted_receipt_for_artifacts_matches_only_on_full_source_set(self):
        """Regression: visual-judge lock must compare the full (path, sha256, mime) set."""
        import shutil
        import tempfile
        from datetime import UTC, datetime
        from pathlib import Path

        from stitch_harness.orchestrator import Harness
        from stitch_harness.state import RunState
        from stitch_harness.storage import ArtifactRecord, Receipt

        fixture = Path("tests/fixtures/page-spec.json")
        fixed_time = datetime(2026, 9, 14, 0, 0, tzinfo=UTC)
        temp = tempfile.TemporaryDirectory()
        try:
            project = Path(temp.name)
            specs = project / ".stitch" / "specs"
            specs.mkdir(parents=True)
            shutil.copy2(fixture, specs / "login.json")
            harness = Harness(preflight=lambda _project: ())
            started = harness.start(project, "login", now=fixed_time)
            run = harness.store.load(project, started.run_id)

            (run.path / "artifacts").mkdir(parents=True, exist_ok=True)
            art_path = run.path / "artifacts/art.png"
            stitch_path = run.path / "artifacts/stitch-final.png"
            art_path.write_bytes(b"art")
            stitch_path.write_bytes(b"stitch")
            art_record = ArtifactRecord.from_path(run.path, art_path, "image/png")
            stitch_record = ArtifactRecord.from_path(run.path, stitch_path, "image/png")

            comparison_paths = (
                "comparison/side-by-side.png",
                "comparison/overlay.png",
                "comparison/diff-heatmap.png",
            )
            for relative in comparison_paths:
                (run.path / relative).parent.mkdir(parents=True, exist_ok=True)
                (run.path / relative).write_bytes(b"cmp")

            run = harness.store.update_state(run, RunState.STITCH_GENERATED)
            run = harness.store.update_state(run, RunState.SOURCE_ACCEPTED)
            run = harness.store.update_state(run, RunState.AWAITING_ART_DECISION)
            run = harness.store.update_state(run, RunState.ART_ENHANCEMENT_APPROVED)
            run = harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "imagegen", outputs=[art_record]))
            run = harness.store.update_state(run, RunState.ART_GENERATED)
            run = harness.store.update_state(run, RunState.ART_ACCEPTED)
            run = harness.store.update_state(run, RunState.SEMANTIC_NORMALIZED)
            (run.path / "artifacts/stitch.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
            roundtrip = [
                ArtifactRecord.from_path(run.path, run.path / "artifacts/stitch.html", "text/html"),
                stitch_record,
            ]
            run = harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "stitch.roundtrip", outputs=roundtrip))
            run = harness.store.update_state(run, RunState.ROUNDTRIPPED)
            run = harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "editability"))
            run = harness.store.update_state(run, RunState.EDITABILITY_VERIFIED)
            comparisons = [ArtifactRecord.from_path(run.path, run.path / relative, "image/png") for relative in comparison_paths]
            run = harness.store.append_receipt(
                run,
                Receipt.passed(
                    run.run_id, run.page_id, "visual-judge",
                    inputs=[art_record, stitch_record],
                    outputs=comparisons,
                ),
            )

            matched = (
                (art_record.path, art_record.sha256, art_record.mime),
                (stitch_record.path, stitch_record.sha256, stitch_record.mime),
            )
            self.assertTrue(harness.store.has_accepted_receipt_for_artifacts(run, "visual-judge", matched))

            # Hash mismatch: must NOT match (artifacts changed for a new round).
            different_art_path = run.path / "artifacts/art.png"
            different_art_path.write_bytes(b"art-v2")
            different_art = ArtifactRecord.from_path(run.path, different_art_path, "image/png")
            self.assertFalse(harness.store.has_accepted_receipt_for_artifacts(
                run, "visual-judge",
                ((different_art.path, different_art.sha256, different_art.mime),
                 (stitch_record.path, stitch_record.sha256, stitch_record.mime)),
            ))
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
