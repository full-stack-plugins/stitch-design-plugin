import json
import struct
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DistributionContractTests(unittest.TestCase):
    def test_manifest_declares_official_stitch_brand_assets(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        interface = manifest["interface"]
        self.assertEqual(interface.get("logo"), "./assets/logo.png")
        self.assertEqual(interface.get("logoDark"), "./assets/logo-dark.png")
        self.assertEqual(interface.get("composerIcon"), "./assets/composer-icon.png")
        for relative, expected_size in (("assets/logo.png", 512), ("assets/logo-dark.png", 512), ("assets/composer-icon.png", 256)):
            data = (ROOT / relative).read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            width, height = struct.unpack(">II", data[16:24])
            self.assertEqual((width, height), (expected_size, expected_size))
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("https://www.gstatic.com/labs-code/stitch/favicon-512x512.png", notices)

    def test_distribution_validator_accepts_repository(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_distribution.py"), str(ROOT)],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("validated 39 skills", result.stdout)

    def test_repository_marketplace_targets_public_root_plugin(self) -> None:
        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
        )
        entry = next(plugin for plugin in marketplace["plugins"] if plugin["name"] == "stitch-design")

        self.assertEqual(entry["source"]["source"], "url")
        self.assertEqual(
            entry["source"]["url"],
            "https://github.com/partme-ai/codex-stitch-plugin.git",
        )
        self.assertEqual(entry["source"]["ref"], "main")
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
        self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")

    def test_breaking_identity_uses_stitch_design_everywhere(self) -> None:
        manifest = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["name"], "stitch-design")
        self.assertEqual(manifest["version"], "0.3.0")
        self.assertEqual(manifest["interface"]["displayName"], "Stitch Design")

    def test_portable_files_are_not_activated_without_portable_auth(self) -> None:
        self.assertFalse((ROOT / "plugin.json").exists())
        self.assertFalse((ROOT / "mcp.json").exists())
        migration = (ROOT / "docs" / "portable-migration.md").read_text(encoding="utf-8")

        self.assertIn("plugin_asdk_app", migration)
        self.assertIn("MUST NOT perform placeholder", migration)


if __name__ == "__main__":
    unittest.main()
