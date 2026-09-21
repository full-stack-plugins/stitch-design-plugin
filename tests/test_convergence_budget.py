"""Group 1 regression tests for the convergence loop budget.

Covers the delivery round counter that ``decide_art`` increments when the run
already has an accepted imagegen receipt (i.e., this is a return from the user
rejection path), and the budget-exhaustion guard that routes the run to
``BLOCKED`` when ``delivery_rounds >= comparison.max_rounds``.
"""

import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from stitch_harness.orchestrator import ArtEnhancementDecision, Harness
from stitch_harness.state import RunState
from stitch_harness.storage import Receipt

FIXTURE = Path(__file__).parent / "fixtures" / "page-spec.json"
FIXED_TIME = datetime(2026, 9, 14, 0, 0, tzinfo=UTC)


class BudgetExhaustionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        specs = self.project / ".stitch" / "specs"
        specs.mkdir(parents=True)
        shutil.copy2(FIXTURE, specs / "login.json")
        # Default max_rounds is 3 per the contract change in Group 5.
        self.harness = Harness(preflight=lambda _project: ())

    def tearDown(self):
        self.temp.cleanup()

    def _append(self, run, step, *, inputs=(), outputs=()):
        run = self.harness.store.append_receipt(
            run,
            Receipt.passed(run.run_id, run.page_id, step, inputs=inputs, outputs=outputs),
        )
        return run

    def _walk_to_art_decision(self):
        started = self.harness.start(self.project, "login", now=FIXED_TIME)
        run = self.harness.store.load(self.project, started.run_id)
        # start() leaves the run in PREFLIGHT_PASSED after the preflight receipt.
        for s in (
            RunState.STITCH_GENERATED,
            RunState.SOURCE_ACCEPTED,
            RunState.AWAITING_ART_DECISION,
        ):
            run = self.harness.store.update_state(run, s)
        return run

    def test_first_enhance_records_round_one(self):
        run = self._walk_to_art_decision()
        status = self.harness.decide_art(self.project, run.run_id, ArtEnhancementDecision("enhance"))
        self.assertEqual(status.state, RunState.ART_ENHANCEMENT_APPROVED)
        manifest = json.loads((self.project / ".stitch/runs" / run.run_id / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest.get("delivery_rounds"), 1)

    def test_re_enhance_after_one_imagegen_increments_round_counter(self):
        run = self._walk_to_art_decision()
        run = self.harness.store.load(self.project, run.run_id)
        status = self.harness.decide_art(self.project, run.run_id, ArtEnhancementDecision("enhance"))
        self.assertEqual(status.state, RunState.ART_ENHANCEMENT_APPROVED)
        run = self.harness.store.load(self.project, run.run_id)
        run = self.harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "imagegen"))

        for s in (
            RunState.ART_GENERATED, RunState.ART_ACCEPTED, RunState.SEMANTIC_NORMALIZED,
            RunState.ROUNDTRIPPED, RunState.EDITABILITY_VERIFIED,
            RunState.COMPARISON_ACCEPTED, RunState.AWAITING_USER_APPROVAL,
        ):
            run = self.harness.store.update_state(run, s)
        run = self.harness.store.update_state(run, RunState.ART_GENERATED)

        status = self.harness.redo_art(self.project, run.run_id, ArtEnhancementDecision("enhance"))
        self.assertEqual(status.state, RunState.ART_ENHANCEMENT_APPROVED)
        manifest = json.loads((self.project / ".stitch/runs" / run.run_id / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest.get("delivery_rounds"), 2)

    def test_budget_exhaustion_blocks_run_after_three_rounds(self):
        # Three successful rounds should still proceed; the fourth must block.
        run = self._walk_to_art_decision()

        # Round 1: initial enhance.
        status = self.harness.decide_art(self.project, run.run_id, ArtEnhancementDecision("enhance"))
        self.assertEqual(status.state, RunState.ART_ENHANCEMENT_APPROVED)
        run = self.harness.store.load(self.project, run.run_id)
        run = self.harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "imagegen"))

        # Rounds 2 and 3: walk the full chain back to ART_GENERATED, then re-decide.
        for _ in range(2):
            run = self.harness.store.load(self.project, run.run_id)
            for s in (
                RunState.ART_GENERATED, RunState.ART_ACCEPTED, RunState.SEMANTIC_NORMALIZED,
                RunState.ROUNDTRIPPED, RunState.EDITABILITY_VERIFIED,
                RunState.COMPARISON_ACCEPTED, RunState.AWAITING_USER_APPROVAL,
            ):
                run = self.harness.store.update_state(run, s)
            run = self.harness.store.update_state(run, RunState.ART_GENERATED)
            status = self.harness.redo_art(self.project, run.run_id, ArtEnhancementDecision("enhance"))
            self.assertEqual(status.state, RunState.ART_ENHANCEMENT_APPROVED)
            run = self.harness.store.load(self.project, run.run_id)
            run = self.harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "imagegen"))

        # Attempt round 4 — must BLOCK.
        run = self.harness.store.load(self.project, run.run_id)
        for s in (
            RunState.ART_GENERATED, RunState.ART_ACCEPTED, RunState.SEMANTIC_NORMALIZED,
            RunState.ROUNDTRIPPED, RunState.EDITABILITY_VERIFIED,
            RunState.COMPARISON_ACCEPTED, RunState.AWAITING_USER_APPROVAL,
        ):
            run = self.harness.store.update_state(run, s)
        run = self.harness.store.update_state(run, RunState.ART_GENERATED)
        status = self.harness.redo_art(self.project, run.run_id, ArtEnhancementDecision("enhance"))
        self.assertEqual(status.state, RunState.BLOCKED)
        self.assertTrue(any("budget exhausted" in err for err in status.errors))
        manifest = json.loads((self.project / ".stitch/runs" / run.run_id / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("blocked_reason", manifest)


if __name__ == "__main__":
    unittest.main()
