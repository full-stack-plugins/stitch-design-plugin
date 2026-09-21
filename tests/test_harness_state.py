import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from stitch_harness.contracts import PageSpec
from stitch_harness.state import InvalidTransition, RunState, transition
from stitch_harness.storage import ArtifactRecord, Receipt, RunStore, sha256_file

FIXTURE = Path(__file__).parent / "fixtures" / "page-spec.json"
FIXED_TIME = datetime(2026, 9, 13, 15, 30, tzinfo=UTC)


class RunStateTests(unittest.TestCase):
    def test_cannot_skip_source_acceptance(self):
        with self.assertRaises(InvalidTransition):
            transition(RunState.STITCH_GENERATED, RunState.ART_GENERATED)

    def test_art_enhancement_requires_an_explicit_decision_state(self):
        self.assertEqual(
            transition(RunState.SOURCE_ACCEPTED, RunState.AWAITING_ART_DECISION),
            RunState.AWAITING_ART_DECISION,
        )
        with self.assertRaises(InvalidTransition):
            transition(RunState.AWAITING_ART_DECISION, RunState.ART_GENERATED)

    def test_approved_artifacts_may_advance_to_archive(self):
        self.assertEqual(transition(RunState.APPROVED, RunState.ARCHIVED), RunState.ARCHIVED)

    def test_enhanced_art_requires_semantic_normalization_before_roundtrip(self):
        self.assertEqual(
            transition(RunState.ART_ACCEPTED, RunState.SEMANTIC_NORMALIZED),
            RunState.SEMANTIC_NORMALIZED,
        )
        with self.assertRaises(InvalidTransition):
            transition(RunState.ART_ACCEPTED, RunState.ROUNDTRIPPED)

    def test_art_generated_can_return_to_art_enhancement_approved(self):
        """Convergence loop: a candidate rejected downstream may be re-enhanced.

        Path: user rejects at AWAITING_USER_APPROVAL → ART_GENERATED →
        ART_ENHANCEMENT_APPROVED (this edge) so the next decide_art("enhance")
        starts a new ImageGen round. The user-rejection edge
        AWAITING_USER_APPROVAL → ART_GENERATED already exists in the base graph;
        this regression locks in the second leg of the return path.
        """
        self.assertEqual(
            transition(RunState.ART_GENERATED, RunState.ART_ENHANCEMENT_APPROVED),
            RunState.ART_ENHANCEMENT_APPROVED,
        )

    def test_return_path_is_only_legal_from_art_generated(self):
        """Conservative scoping: only ART_GENERATED may return to ART_ENHANCEMENT_APPROVED.

        Other post-imagegen states (ART_ACCEPTED, ROUNDTRIPPED, EDITABILITY_VERIFIED,
        COMPARISON_ACCEPTED) cannot jump straight back; the operator must first
        walk the run through ART_GENERATED via the existing user-rejection edge,
        preserving the gate-by-gate re-run invariant.
        """
        for state in (
            RunState.ART_ACCEPTED,
            RunState.ROUNDTRIPPED,
            RunState.EDITABILITY_VERIFIED,
            RunState.COMPARISON_ACCEPTED,
            RunState.AWAITING_USER_APPROVAL,
        ):
            with self.subTest(state=state):
                with self.assertRaises(InvalidTransition):
                    transition(state, RunState.ART_ENHANCEMENT_APPROVED)


class RunStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = RunStore()
        self.spec = PageSpec.load(FIXTURE)

    def tearDown(self):
        self.temp.cleanup()

    def test_start_creates_unique_run_with_spec_snapshot(self):
        run = self.store.start(self.root, self.spec, FIXED_TIME)

        self.assertEqual(run.run_id, "20260913T153000Z-login")
        self.assertEqual(run.state, RunState.DRAFT)
        self.assertTrue((run.path / "spec.json").is_file())
        with self.assertRaises(FileExistsError):
            self.store.start(self.root, self.spec, FIXED_TIME)

    def test_receipt_chain_rejects_modified_artifact(self):
        run = self.store.start(self.root, self.spec, FIXED_TIME)
        artifact = run.path / "artifacts" / "source.html"
        artifact.write_text("<main>first</main>", encoding="utf-8")
        record = ArtifactRecord.from_path(run.path, artifact, "text/html")
        receipt = Receipt.passed(run.run_id, self.spec.page_id, "preflight", outputs=[record])
        self.store.append_receipt(run, receipt)

        artifact.write_text("<main>changed</main>", encoding="utf-8")
        verification = self.store.verify_chain(run)

        self.assertFalse(verification.valid)
        self.assertIn("artifact hash mismatch", verification.errors[0])

    def test_receipt_chain_links_each_previous_receipt_hash(self):
        run = self.store.start(self.root, self.spec, FIXED_TIME)
        first = self.store.append_receipt(
            run,
            Receipt.passed(run.run_id, self.spec.page_id, "preflight"),
        )
        first = self.store.update_state(first, RunState.PREFLIGHT_PASSED)
        second = self.store.append_receipt(first, Receipt.passed(run.run_id, self.spec.page_id, "stitch.generate"))

        receipts = sorted((run.path / "receipts").glob("*.json"))
        self.assertEqual(len(receipts), 2)
        self.assertEqual(second.latest_receipt_sha256, sha256_file(receipts[-1]))
        self.assertTrue(self.store.verify_chain(second).valid)

    def test_unknown_receipt_step_is_rejected_before_a_filename_is_created(self):
        run = self.store.start(self.root, self.spec, FIXED_TIME)

        with self.assertRaisesRegex(ValueError, "allowlist"):
            self.store.append_receipt(
                run,
                Receipt.passed(run.run_id, run.page_id, "../../escaped"),
            )

        self.assertEqual(list((run.path / "receipts").iterdir()), [])

    def test_receipt_step_must_match_the_current_run_state(self):
        run = self.store.start(self.root, self.spec, FIXED_TIME)

        with self.assertRaisesRegex(ValueError, "requires 'preflight'"):
            self.store.append_receipt(
                run,
                Receipt.passed(run.run_id, run.page_id, "imagegen"),
            )

    def test_receipt_journal_recovers_crashes_at_every_append_boundary(self):
        class CrashingStore(RunStore):
            def __init__(self, crash_at):
                self.crash_at = crash_at

            def _checkpoint(self, name):
                if name == self.crash_at:
                    raise OSError(f"crash at {name}")

        for checkpoint in ("pending-written", "receipt-written", "manifest-written"):
            with self.subTest(checkpoint=checkpoint), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                run = RunStore().start(root, self.spec, FIXED_TIME)
                store = CrashingStore(checkpoint)
                with self.assertRaisesRegex(OSError, checkpoint):
                    store.append_receipt(
                        run,
                        Receipt.passed(run.run_id, run.page_id, "preflight"),
                    )

                recovered = RunStore().load(root, run.run_id)

                self.assertTrue(RunStore().verify_chain(recovered).valid)
                self.assertEqual(len(list((run.path / "receipts").glob("*.json"))), 1)
                self.assertFalse((run.path / ".receipt-pending.json").exists())

    def test_receipt_commit_fsyncs_each_renamed_parent_and_journal_unlink(self):
        run = self.store.start(self.root, self.spec, FIXED_TIME)

        with mock.patch("stitch_harness.storage._fsync_directory") as fsync_directory:
            self.store.append_receipt(
                run,
                Receipt.passed(run.run_id, run.page_id, "preflight"),
            )

        self.assertEqual(
            fsync_directory.call_args_list,
            [
                mock.call(run.path),
                mock.call(run.path / "receipts"),
                mock.call(run.path),
                mock.call(run.path),
            ],
        )

    def test_receipt_journal_recovery_accepts_sequence_1000_and_fsyncs_recovery(self):
        class PendingOnlyStore(RunStore):
            def _checkpoint(self, name):
                if name == "pending-written":
                    raise OSError("crash after pending journal")

        run = self.store.start(self.root, self.spec, FIXED_TIME)
        with self.assertRaisesRegex(OSError, "pending journal"):
            PendingOnlyStore().append_receipt(
                run,
                Receipt.passed(run.run_id, run.page_id, "preflight"),
            )
        journal_path = run.path / ".receipt-pending.json"
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal["receipt_name"] = "1000-preflight.json"
        journal_path.write_text(json.dumps(journal), encoding="utf-8")

        with mock.patch("stitch_harness.storage._fsync_directory") as fsync_directory:
            recovered = RunStore().load(self.root, run.run_id)

        self.assertTrue((run.path / "receipts/1000-preflight.json").is_file())
        self.assertTrue(RunStore().verify_chain(recovered).valid)
        self.assertEqual(
            fsync_directory.call_args_list,
            [mock.call(run.path / "receipts"), mock.call(run.path), mock.call(run.path)],
        )
        continued = RunStore().append_receipt(
            recovered,
            Receipt.passed(run.run_id, run.page_id, "preflight"),
        )
        self.assertTrue((run.path / "receipts/1001-preflight.json").is_file())
        self.assertTrue(RunStore().verify_chain(continued).valid)


if __name__ == "__main__":
    unittest.main()
