import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from stitch_harness.cli import main
from stitch_harness.orchestrator import ArtEnhancementDecision, Harness
from stitch_harness.state import RunState
from stitch_harness.storage import ArtifactRecord, Receipt


class HarnessCliTests(unittest.TestCase):
    def test_no_arguments_returns_contract_exit_code(self):
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            code = main([])

        self.assertEqual(code, 2)
        self.assertIn("usage:", stderr.getvalue().lower())


class CompareCliRegressionTests(unittest.TestCase):
    """Group 2 regressions for the compare command."""

    FIXTURE = Path(__file__).parent / "fixtures" / "page-spec.json"
    FIXED_TIME = datetime(2026, 9, 14, 0, 0, tzinfo=UTC)
    COMPARISON = (
        "comparison/side-by-side.png",
        "comparison/overlay.png",
        "comparison/diff-heatmap.png",
    )

    def _png(self, path, size=(4, 4)):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, "white").save(path)

    def _build_project(self):
        temp = tempfile.TemporaryDirectory()
        project = Path(temp.name)
        specs = project / ".stitch" / "specs"
        specs.mkdir(parents=True)
        shutil.copy2(self.FIXTURE, specs / "login.json")
        harness = Harness(preflight=lambda _project: ())
        started = harness.start(project, "login", now=self.FIXED_TIME)
        run = harness.store.load(project, started.run_id)

        self._png(run.path / "artifacts/art.png")
        self._png(run.path / "artifacts/stitch-final.png")
        (run.path / "artifacts/stitch.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
        for r in self.COMPARISON:
            self._png(run.path / r)

        # Walk states via update_state (which only validates the transition graph).
        # The run starts in PREFLIGHT_PASSED (after start() succeeds), so begin
        # the walk from STITCH_GENERATED.
        art = ArtifactRecord.from_path(run.path, run.path / "artifacts/art.png", "image/png")
        roundtrip = [
            ArtifactRecord.from_path(run.path, run.path / "artifacts/stitch.html", "text/html"),
            ArtifactRecord.from_path(run.path, run.path / "artifacts/stitch-final.png", "image/png"),
        ]

        run = harness.store.update_state(run, RunState.STITCH_GENERATED)
        run = harness.store.update_state(run, RunState.SOURCE_ACCEPTED)
        run = harness.store.update_state(run, RunState.AWAITING_ART_DECISION)
        run = harness.store.update_state(run, RunState.ART_ENHANCEMENT_APPROVED)
        run = harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "imagegen", outputs=[art]))
        run = harness.store.update_state(run, RunState.ART_GENERATED)
        run = harness.store.update_state(run, RunState.ART_ACCEPTED)
        run = harness.store.update_state(run, RunState.SEMANTIC_NORMALIZED)
        run = harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "stitch.roundtrip", outputs=roundtrip))
        run = harness.store.update_state(run, RunState.ROUNDTRIPPED)
        run = harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "editability"))
        run = harness.store.update_state(run, RunState.EDITABILITY_VERIFIED)
        return temp, project, harness, run

    def _scores(self, project):
        path = project / "scores.json"
        path.write_text(json.dumps({n: 5 for n in ("hierarchy", "density", "color", "component_quality", "completion")}), encoding="utf-8")
        return path

    def test_compare_without_scores_fails_fast_and_writes_no_evidence(self):
        temp, project, harness, run = self._build_project()
        try:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = main(["compare", "--project", str(project), "--run", run.run_id])
            evidence = run.path / "evidence/visual-judge.json"
            self.assertEqual(code, 2)
            self.assertFalse(evidence.exists())
            self.assertIn("--scores", stderr.getvalue())
        finally:
            temp.cleanup()

    def test_compare_with_incomplete_scores_fails_fast(self):
        temp, project, harness, run = self._build_project()
        try:
            bad_scores = project / "bad-scores.json"
            bad_scores.write_text(json.dumps({"hierarchy": 5, "density": 5, "color": 5, "component_quality": 5}), encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = main(["compare", "--project", str(project), "--run", run.run_id, "--scores", str(bad_scores)])
            evidence = run.path / "evidence/visual-judge.json"
            self.assertEqual(code, 2)
            self.assertFalse(evidence.exists())
            self.assertIn("completion", stderr.getvalue())
        finally:
            temp.cleanup()

    def test_compare_same_artifacts_rejected_after_passed_round(self):
        temp, project, harness, run = self._build_project()
        try:
            scores = self._scores(project)
            first = main(["compare", "--project", str(project), "--run", run.run_id, "--scores", str(scores)])
            self.assertEqual(first, 0)

            # Mirror what the orchestrator does after a passing compare: append the
            # visual-judge receipt with the artifacts that just bound it.
            art = ArtifactRecord.from_path(run.path, run.path / "artifacts/art.png", "image/png")
            stitch = ArtifactRecord.from_path(run.path, run.path / "artifacts/stitch-final.png", "image/png")
            comparisons = [ArtifactRecord.from_path(run.path, run.path / rel, "image/png") for rel in self.COMPARISON]
            run = harness.store.append_receipt(
                run,
                Receipt.passed(run.run_id, run.page_id, "visual-judge",
                               inputs=[art, stitch], outputs=comparisons),
            )

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                second = main(["compare", "--project", str(project), "--run", run.run_id, "--scores", str(scores)])
            self.assertEqual(second, 2)
            self.assertIn("same artifacts", stderr.getvalue())
        finally:
            temp.cleanup()

    def test_compare_with_changed_artifacts_allows_next_round(self):
        """Regression: a new round with re-bound artifacts must succeed."""
        temp, project, harness, run = self._build_project()
        try:
            scores = self._scores(project)
            first = main(["compare", "--project", str(project), "--run", run.run_id, "--scores", str(scores)])
            self.assertEqual(first, 0)

            # Lock the first round by appending a visual-judge receipt that binds
            # the current artifacts.
            art_record = ArtifactRecord.from_path(run.path, run.path / "artifacts/art.png", "image/png")
            stitch_record = ArtifactRecord.from_path(run.path, run.path / "artifacts/stitch-final.png", "image/png")
            comparisons = [ArtifactRecord.from_path(run.path, run.path / rel, "image/png") for rel in self.COMPARISON]
            run = harness.store.append_receipt(
                run,
                Receipt.passed(run.run_id, run.page_id, "visual-judge",
                               inputs=[art_record, stitch_record], outputs=comparisons),
            )

            # Write the second-round art to a NEW filename so the previous round's
            # imagegen receipt remains valid (its recorded sha256 still matches the
            # file). This mirrors a real ImageGen round that creates a new asset
            # path rather than overwriting.
            from PIL import Image as _Image
            new_art_path = run.path / "artifacts/art-round-2.png"
            _Image.new("RGB", (4, 4), "white").save(new_art_path)

            # Walk the run back through the convergence return path: user rejects
            # at AWAITING_USER_APPROVAL -> ART_GENERATED, redo_art re-enhances.
            self.assertEqual(run.state, RunState.EDITABILITY_VERIFIED)
            run = harness.store.update_state(run, RunState.COMPARISON_ACCEPTED)
            run = harness.store.update_state(run, RunState.AWAITING_USER_APPROVAL)
            run = harness.store.update_state(run, RunState.ART_GENERATED)
            status = harness.redo_art(project, run.run_id, ArtEnhancementDecision("enhance"))
            self.assertEqual(status.state, RunState.ART_ENHANCEMENT_APPROVED)
            run = harness.store.load(project, run.run_id)
            # Rebuild the producer chain for the second round.
            new_art_record = ArtifactRecord.from_path(run.path, new_art_path, "image/png")
            run = harness.store.append_receipt(
                run,
                Receipt.passed(run.run_id, run.page_id, "imagegen", outputs=[new_art_record]),
            )
            run = harness.store.update_state(run, RunState.ART_GENERATED)
            run = harness.store.update_state(run, RunState.ART_ACCEPTED)
            run = harness.store.update_state(run, RunState.SEMANTIC_NORMALIZED)
            roundtrip = [
                ArtifactRecord.from_path(run.path, run.path / "artifacts/stitch.html", "text/html"),
                ArtifactRecord.from_path(run.path, run.path / "artifacts/stitch-final.png", "image/png"),
            ]
            run = harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "stitch.roundtrip", outputs=roundtrip))
            run = harness.store.update_state(run, RunState.ROUNDTRIPPED)
            run = harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "editability"))
            run = harness.store.update_state(run, RunState.EDITABILITY_VERIFIED)
            import io as _io
            from contextlib import redirect_stderr as _rs
            buf = _io.StringIO()
            with _rs(buf):
                second = main(["compare", "--project", str(project), "--run", run.run_id, "--scores", str(scores)])
            if second != 0:
                self.fail(f"second compare failed: {buf.getvalue()}")
            self.assertEqual(second, 0, "second round with changed artifacts must be allowed")
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
