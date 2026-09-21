"""Group 6 regression tests: stall detection and structural rework flag.

The harness decides ``convergence_stalled`` after at most two rounds: either the
judge total moves less than a full point, or the same gap id appears in two
consecutive verdicts. Once stalled, the next ``redo_art`` must require an
explicit structural rework flag, and a second structural rework that still
stalls must stop and hand back to the user (the run enters ``BLOCKED``).
"""

import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from stitch_harness.orchestrator import (
    ArtEnhancementDecision,
    Harness,
    RoundResult,
    RunBlockedAfterStall,
)
from stitch_harness.state import RunState

FIXTURE = Path(__file__).parent / "fixtures" / "page-spec.json"
FIXED_TIME = datetime(2026, 9, 14, 0, 0, tzinfo=UTC)
RUN_ID = "20260914T000000Z-login"


class StallDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        specs = self.project / ".stitch" / "specs"
        specs.mkdir(parents=True)
        shutil.copy2(FIXTURE, specs / "login.json")
        self.harness = Harness(preflight=lambda _project: ())
        self.harness.start(self.project, "login", now=FIXED_TIME)
        # Walk to AWAITING_USER_APPROVAL so the redo path is reachable.
        run = self.harness.store.load(self.project, RUN_ID)
        for s in (
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
            run = self.harness.store.update_state(run, s)

    def tearDown(self):
        self.temp.cleanup()

    def _record(self, total: int, gap_ids, *, structural_rework: bool = False) -> RoundResult:
        return self.harness.record_round_result(
            self.project, RUN_ID, total_score=total, gap_ids=list(gap_ids), structural_rework=structural_rework,
        )

    def _manifest(self) -> dict:
        return json.loads((self.project / ".stitch" / "runs" / RUN_ID / "manifest.json").read_text(encoding="utf-8"))

    def test_no_stall_when_score_improves_and_no_repeated_gap(self):
        first = self._record(total=20, gap_ids=["g1"])
        second = self._record(total=22, gap_ids=["g2"])
        self.assertFalse(first.stalled)
        self.assertFalse(second.stalled)
        self.assertIsNone(self._manifest().get("convergence_stalled"))

    def test_stall_when_score_does_not_improve_a_full_point(self):
        self._record(total=20, gap_ids=["g1"])
        result = self._record(total=20, gap_ids=["g2"])
        self.assertTrue(result.stalled)
        self.assertEqual(result.stall_reason["type"], "no_progress")
        manifest = self._manifest()
        self.assertTrue(manifest["convergence_stalled"])

    def test_stall_when_same_gap_id_appears_in_two_consecutive_rounds(self):
        self._record(total=15, gap_ids=["hero-lighting", "hero-pose"])
        result = self._record(total=18, gap_ids=["hero-lighting"])
        self.assertTrue(result.stalled)
        self.assertEqual(result.stall_reason["type"], "repeated_gap")
        self.assertEqual(result.stall_reason["gap_id"], "hero-lighting")

    def test_redo_after_stall_without_structural_rework_is_rejected(self):
        self._record(total=20, gap_ids=["a"])
        self._record(total=20, gap_ids=["a"], structural_rework=False)
        # Walk back to the convergence return path.
        run = self.harness.store.load(self.project, RUN_ID)
        run = self.harness.store.update_state(run, RunState.ART_GENERATED)
        with self.assertRaises(RunBlockedAfterStall):
            self.harness.redo_art(
                self.project, RUN_ID, ArtEnhancementDecision("enhance"), structural_rework=False,
            )

    def test_redo_after_stall_with_structural_rework_succeeds(self):
        self._record(total=20, gap_ids=["a"])
        self._record(total=20, gap_ids=["a"], structural_rework=False)
        run = self.harness.store.load(self.project, RUN_ID)
        run = self.harness.store.update_state(run, RunState.ART_GENERATED)
        status = self.harness.redo_art(
            self.project, RUN_ID, ArtEnhancementDecision("enhance"), structural_rework=True,
        )
        self.assertEqual(status.state, RunState.ART_ENHANCEMENT_APPROVED)
        manifest = self._manifest()
        self.assertTrue(manifest["structural_rework_done"])

    def test_second_stall_after_structural_rework_blocks_run(self):
        self._record(total=20, gap_ids=["a"])
        self._record(total=20, gap_ids=["a"], structural_rework=False)
        run = self.harness.store.load(self.project, RUN_ID)
        run = self.harness.store.update_state(run, RunState.ART_GENERATED)
        self.harness.redo_art(self.project, RUN_ID, ArtEnhancementDecision("enhance"), structural_rework=True)
        # Reject once more, then redo again — this round also stalls.
        run = self.harness.store.load(self.project, RUN_ID)
        run = self.harness.store.update_state(run, RunState.ART_GENERATED)
        with self.assertRaises(RunBlockedAfterStall):
            self.harness.redo_art(self.project, RUN_ID, ArtEnhancementDecision("enhance"), structural_rework=True)
        run = self.harness.store.load(self.project, RUN_ID)
        self.assertEqual(run.state, RunState.BLOCKED)


if __name__ == "__main__":
    unittest.main()
