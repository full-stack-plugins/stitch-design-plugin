import os
import tempfile
import unittest
from pathlib import Path

from stitch_harness.archive import ArchiveManager
from stitch_harness.contracts import PageSpec
from stitch_harness.state import InvalidTransition, RunState
from stitch_harness.storage import Run, sha256_file


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


if __name__ == "__main__":
    unittest.main()
