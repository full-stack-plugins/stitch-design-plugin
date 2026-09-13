import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from stitch_harness.contracts import PageSpec
from stitch_harness.state import InvalidTransition, RunState, transition
from stitch_harness.storage import ArtifactRecord, Receipt, RunStore, sha256_file


FIXTURE = Path(__file__).parent / "fixtures" / "page-spec.json"
FIXED_TIME = datetime(2026, 9, 13, 15, 30, tzinfo=UTC)


class RunStateTests(unittest.TestCase):
    def test_cannot_skip_source_acceptance(self):
        with self.assertRaises(InvalidTransition):
            transition(RunState.STITCH_GENERATED, RunState.ART_GENERATED)

    def test_approved_artifacts_may_advance_to_archive(self):
        self.assertEqual(transition(RunState.APPROVED, RunState.ARCHIVED), RunState.ARCHIVED)


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


if __name__ == "__main__":
    unittest.main()
