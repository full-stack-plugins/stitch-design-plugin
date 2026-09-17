import tempfile
import unittest
from pathlib import Path

from stitch_harness.setup_trigger import launch_setup_ui_once


class SetupTriggerTests(unittest.TestCase):
    def test_first_missing_credential_launches_ui_and_second_is_deduplicated(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin_root = root / "plugin"
            script = plugin_root / "scripts" / "stitch_setup.py"
            script.parent.mkdir(parents=True)
            script.write_text("# setup\n", encoding="utf-8")
            marker = root / "setup-trigger.json"

            first = launch_setup_ui_once(
                plugin_root=plugin_root,
                marker_path=marker,
                now=lambda: 1000.0,
                launcher=lambda command: calls.append(command),
            )
            second = launch_setup_ui_once(
                plugin_root=plugin_root,
                marker_path=marker,
                now=lambda: 1001.0,
                launcher=lambda command: calls.append(command),
            )

            marker_payload = marker.read_text(encoding="utf-8")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][-2:], [str(script.resolve()), "ui"])
        self.assertEqual(marker_payload, '{"launched_at":1000.0}\n')

    def test_stale_trigger_allows_a_new_setup_window(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin_root = root / "plugin"
            script = plugin_root / "scripts" / "stitch_setup.py"
            script.parent.mkdir(parents=True)
            script.write_text("# setup\n", encoding="utf-8")
            marker = root / "setup-trigger.json"
            marker.write_text('{"launched_at":1000.0}\n', encoding="utf-8")

            launched = launch_setup_ui_once(
                plugin_root=plugin_root,
                marker_path=marker,
                now=lambda: 1601.0,
                launcher=lambda command: calls.append(command),
            )

        self.assertTrue(launched)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
