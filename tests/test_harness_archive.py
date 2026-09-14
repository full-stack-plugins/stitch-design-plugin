import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from stitch_harness.archive import ArchiveManager
from stitch_harness.cli import _archive_or_recover
from stitch_harness.orchestrator import Harness
from stitch_harness.contracts import PageSpec
from stitch_harness.state import InvalidTransition, RunState
from stitch_harness.storage import ArtifactRecord, ChainVerification, Receipt, Run, RunStore, sha256_file


FIXTURE = Path(__file__).parent / "fixtures" / "page-spec.json"


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        self.run_path = self.project / ".stitch" / "runs" / "run"
        self.run_path.mkdir(parents=True)
        self.spec = PageSpec.load(FIXTURE)
        self.manager = ArchiveManager(self.project)

    def tearDown(self):
        self.temp.cleanup()

    def test_archive_requires_approved_state(self):
        run = Run("run", "login", self.run_path, RunState.COMPARISON_ACCEPTED)

        with self.assertRaises(InvalidTransition):
            self.manager.archive(run, self.spec)

    @unittest.skipIf(os.name == "nt", "Windows runners do not guarantee symlink privileges")
    def test_move_preserves_old_conversation_path_as_relative_symlink(self):
        old_image = self.project / "generated" / "login.png"
        old_image.parent.mkdir()
        old_image.write_bytes(b"approved-image")
        archive_dir = self.project / "docs" / "design-v1" / "desktop" / "login" / "v1"
        archive_dir.mkdir(parents=True)
        destination = archive_dir / "login-light.png"

        result = self.manager.move_with_compat_link(old_image, destination)

        self.assertTrue(old_image.is_symlink())
        self.assertFalse(os.path.isabs(os.readlink(old_image)))
        self.assertEqual(sha256_file(old_image.resolve()), result.sha256)
        self.assertEqual(destination.read_bytes(), b"approved-image")

    def approved_run(self):
        store = RunStore()
        run = store.start(self.project, self.spec, datetime(2026, 9, 14, tzinfo=UTC))
        files = {
            "artifacts/art.png": b"art",
            "artifacts/roundtrip.html": b"html",
            "artifacts/stitch-final.png": b"stitch",
            "comparison/side-by-side.png": b"side",
            "comparison/overlay.png": b"overlay",
            "comparison/diff-heatmap.png": b"diff",
        }
        for relative, content in files.items():
            path = run.path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        run = store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "preflight"))
        run = store.update_state(run, RunState.PREFLIGHT_PASSED)
        run = store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "stitch.generate"))
        run = store.update_state(run, RunState.STITCH_GENERATED)
        run = store.update_state(run, RunState.SOURCE_ACCEPTED)
        run = store.update_state(run, RunState.AWAITING_ART_DECISION)
        run = store.append_receipt(
            run,
            Receipt.passed(
                run.run_id,
                run.page_id,
                "art-decision",
                checks=({"decision": "enhance", "source": "explicit-user-response"},),
            ),
        )
        run = store.update_states(
            run,
            (RunState.ART_ENHANCEMENT_APPROVED,),
            manifest_updates={"art_mode": "enhance"},
        )
        art = ArtifactRecord.from_path(run.path, run.path / "artifacts/art.png", "image/png")
        run = store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "imagegen", outputs=[art]))
        run = store.update_state(run, RunState.ART_GENERATED)
        run = store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "ocr"))
        run = store.update_state(run, RunState.ART_ACCEPTED)
        roundtrip = [
            ArtifactRecord.from_path(run.path, run.path / "artifacts/roundtrip.html", "text/html"),
            ArtifactRecord.from_path(run.path, run.path / "artifacts/stitch-final.png", "image/png"),
        ]
        run = store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "stitch.roundtrip", outputs=roundtrip))
        run = store.update_state(run, RunState.ROUNDTRIPPED)
        run = store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "editability"))
        run = store.update_state(run, RunState.EDITABILITY_VERIFIED)
        comparisons = [
            ArtifactRecord.from_path(run.path, run.path / relative, "image/png")
            for relative in (
                "comparison/side-by-side.png",
                "comparison/overlay.png",
                "comparison/diff-heatmap.png",
            )
        ]
        run = store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "visual-judge", outputs=comparisons))
        run = store.update_state(run, RunState.COMPARISON_ACCEPTED)
        run = store.update_state(run, RunState.AWAITING_USER_APPROVAL)
        required = store.required_approval_artifacts(run)
        approval_inputs = [
            ArtifactRecord.from_path(run.path, run.path / relative, "application/octet-stream")
            for relative in required
        ]
        run = store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "user-approval", inputs=approval_inputs))
        return store.update_state(run, RunState.APPROVED)

    def test_archive_rejects_invalid_receipt_chain(self):
        run = self.approved_run()
        first_receipt = sorted((run.path / "receipts").glob("*.json"))[0]
        first_receipt.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "receipt chain"):
            self.manager.archive(run, self.spec)

    def test_archive_includes_manifest_and_preserves_approved_hashes(self):
        run = self.approved_run()

        result = self.manager.archive(run, self.spec)

        self.assertTrue((result.destination / "manifest.json").is_file())
        archived = RunStore().load_from_path(result.destination, run.run_id)
        self.assertEqual(archived.state, RunState.APPROVED)
        self.assertEqual(archived.latest_receipt_sha256, run.latest_receipt_sha256)
        for relative, digest in RunStore().required_approval_artifacts(run).items():
            self.assertEqual(sha256_file(result.destination / relative), digest)

    def test_archive_rejects_stale_copied_manifest(self):
        run = self.approved_run()
        manifest_path = run.path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["latest_receipt_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "manifest|receipt chain"):
            self.manager.archive(run, self.spec)

    def test_archive_rejects_windows_style_archive_paths(self):
        run = self.approved_run()
        for archive in (r"nested\archive", r"C:archive", r"C:\outside\archive", r"\\server\share"):
            with self.subTest(archive=archive):
                unsafe_spec = replace(self.spec, archive=archive)
                with self.assertRaisesRegex(ValueError, "contained"):
                    self.manager.archive(run, unsafe_spec)

    @unittest.skipIf(os.name == "nt", "Windows runners do not guarantee symlink privileges")
    def test_archive_rejects_symlink_escape(self):
        run = self.approved_run()
        with tempfile.TemporaryDirectory() as outside_directory:
            (self.project / "escaped").symlink_to(Path(outside_directory), target_is_directory=True)
            unsafe_spec = replace(self.spec, archive="escaped/archive")

            with self.assertRaisesRegex(ValueError, "contained"):
                self.manager.archive(run, unsafe_spec)

    def test_reported_archive_failure_leaves_no_final_destination(self):
        run = self.approved_run()

        class FailOnlyAfterPublicationStore(RunStore):
            def verify_chain(self, candidate):
                if candidate.path != run.path and candidate.path.name == run.run_id:
                    return ChainVerification(False, ("forced published verification failure",))
                return super().verify_chain(candidate)

        manager = ArchiveManager(self.project, store=FailOnlyAfterPublicationStore())
        destination = self.project / self.spec.archive / run.run_id

        with self.assertRaisesRegex(ValueError, "published archive"):
            manager.archive(run, self.spec)

        self.assertFalse(destination.exists())

    def test_archive_command_recovers_after_publication_before_state_persistence(self):
        run = self.approved_run()
        harness = Harness()
        original = harness.store.update_state
        calls = 0

        def interrupted(candidate, target):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("simulated state persistence interruption")
            return original(candidate, target)

        harness.store.update_state = interrupted
        with self.assertRaisesRegex(OSError, "interruption"):
            _archive_or_recover(harness, self.project, run.run_id)
        destination = self.project / self.spec.archive / run.run_id
        self.assertTrue(destination.is_dir())

        state, recovered_destination = _archive_or_recover(harness, self.project, run.run_id)
        self.assertEqual(state, RunState.ARCHIVED)
        self.assertEqual(recovered_destination.resolve(), destination.resolve())

    def test_archive_recovery_rejects_published_spec_that_differs_from_source(self):
        run = self.approved_run()
        result = self.manager.archive(run, self.spec)
        published_spec = result.destination / "spec.json"
        payload = json.loads(published_spec.read_text(encoding="utf-8"))
        payload["title"] = "tampered archive title"
        published_spec.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "spec|archive"):
            _archive_or_recover(Harness(), self.project, run.run_id)


if __name__ == "__main__":
    unittest.main()
