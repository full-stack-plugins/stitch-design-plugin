"""Group 4 regression tests: visual_review records its real producer and labels
the deterministic layout score's algorithm version.

Covers:
- 4.1 visual_review accepts a real producer (provider, model, tool) instead of
  inheriting ``local-harness``/``deterministic``.
- 4.2 visual_review places the deterministic layout algorithm version into the
  ``result`` payload so consumers can distinguish layout from judge scores.
- 4.3 loading and validation remain tolerant of legacy evidence files that
  predate the algorithm_version field.
"""

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from stitch_harness.evidence import ExternalEvidence
from stitch_harness.evidence_writer import EvidenceWriter


class VisualReviewProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        specs = self.project / ".stitch" / "specs"
        specs.mkdir(parents=True)
        # Minimal spec load only validates field shape; the producer tests do
        # not need a real harness run, only an EvidenceWriter rooted here.
        self.run_root = self.project / "run"
        self.run_root.mkdir()
        (self.run_root / "artifacts").mkdir()
        self.writer = EvidenceWriter(self.run_root)

    def tearDown(self):
        self.temp.cleanup()

    def _png(self, name: str, color: str = "white") -> Path:
        path = self.run_root / "artifacts" / name
        Image.new("RGB", (8, 8), color).save(path)
        return path

    def test_visual_review_records_real_producer(self):
        """4.1: producer block reflects the actual judge, not local/deterministic."""
        art = self._png("art.png")
        stitch = self._png("stitch-final.png")
        side = self._png("side.png")
        overlay = self._png("overlay.png")
        heatmap = self._png("heatmap.png")

        evidence_path = self.writer.visual_review(
            artifact_paths=[side, overlay, heatmap],
            source_artifact_paths=[art, stitch],
            layout_score=0.95,
            scores={
                "hierarchy": 4, "density": 4, "color": 4,
                "component_quality": 4, "completion": 4,
            },
            provider="stitch-judge",
            model="v1",
            tool="score",
        )
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["provider"], {"name": "stitch-judge", "tool": "score", "model": "v1"})

    def test_visual_review_labels_layout_algorithm_version(self):
        """4.2: result payload carries the deterministic layout algorithm version."""
        art = self._png("art.png")
        stitch = self._png("stitch-final.png")
        side = self._png("side.png")
        overlay = self._png("overlay.png")
        heatmap = self._png("heatmap.png")

        evidence_path = self.writer.visual_review(
            artifact_paths=[side, overlay, heatmap],
            source_artifact_paths=[art, stitch],
            layout_score=0.97,
            scores={"hierarchy": 5, "density": 5, "color": 5, "component_quality": 5, "completion": 5},
            provider="stitch-judge",
            model="v1",
            algorithm_version="coarse-edge-mae-v2",
        )
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        self.assertIn("layout_algorithm", payload["result"])
        self.assertEqual(payload["result"]["layout_algorithm"], "coarse-edge-mae-v2")
        self.assertEqual(payload["result"]["layout_score"], 0.97)

    def test_visual_review_legacy_call_without_producer_still_validates(self):
        """4.3: legacy callers (cli.py) without producer kwargs still produce
        valid evidence with the deterministic provider recorded. Validation must
        not require algorithm_version on historical files.
        """
        art = self._png("art.png")
        stitch = self._png("stitch-final.png")
        side = self._png("side.png")
        overlay = self._png("overlay.png")
        heatmap = self._png("heatmap.png")

        evidence_path = self.writer.visual_review(
            artifact_paths=[side, overlay, heatmap],
            source_artifact_paths=[art, stitch],
            layout_score=0.92,
            scores={"hierarchy": 4, "density": 4, "color": 4, "component_quality": 4, "completion": 4},
        )
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        # Deterministic default provider is recorded (legacy behavior).
        self.assertEqual(payload["provider"]["name"], "local-harness")
        # algorithm_version is allowed to be absent on legacy calls — validation
        # tolerates both shapes.
        evidence = ExternalEvidence.from_dict(payload, "visual-judge")
        self.assertEqual(evidence.step, "visual-judge")

    def test_legacy_evidence_without_algorithm_version_loads_cleanly(self):
        """4.3: hand-crafted evidence without layout_algorithm loads without error."""
        # Provide minimal artifact entries; the validator requires at least one.
        legacy = {
            "schema_version": 1,
            "step": "visual-judge",
            "provider": {"name": "local-harness", "tool": "compare", "model": "deterministic"},
            "invoked_at": "2026-09-14T00:00:00Z",
            "source_artifacts": [
                {"path": "artifacts/art.png", "sha256": "a" * 64, "mime": "image/png"}
            ],
            "artifacts": [
                {"path": "comparison/side-by-side.png", "sha256": "b" * 64, "mime": "image/png"}
            ],
            "result": {
                "layout_score": 0.9,
                "scores": {
                    "hierarchy": 5, "density": 5, "color": 5,
                    "component_quality": 5, "completion": 5,
                },
            },
        }
        # Must not raise on the missing layout_algorithm key.
        evidence = ExternalEvidence.from_dict(legacy, "visual-judge")
        self.assertEqual(evidence.step, "visual-judge")


if __name__ == "__main__":
    unittest.main()
