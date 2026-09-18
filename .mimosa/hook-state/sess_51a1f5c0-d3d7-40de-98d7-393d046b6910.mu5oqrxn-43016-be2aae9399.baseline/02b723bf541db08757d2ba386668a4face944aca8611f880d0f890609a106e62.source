import tempfile
import unittest
from pathlib import Path
from unittest import mock

from stitch_harness.contracts import PageSpec
from stitch_harness.evidence import ExternalEvidence
from stitch_harness.visual_gate import DimensionMismatch, compare_images, validate_visual_scores


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


if __name__ == "__main__":
    unittest.main()
