"""Prevent the obsolete Codex-prefixed public Stitch plugin identity."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
OBSOLETE = "codex" + "-stitch-design-plugin"


class CrossHostNamingTest(unittest.TestCase):
    def test_current_design_uses_cross_host_plugin_name(self) -> None:
        violations: list[str] = []
        for directory in (ROOT / "docs/superpowers/specs", ROOT / "docs/superpowers/plans"):
            for path in directory.glob("*.md"):
                if OBSOLETE in path.read_text(encoding="utf-8"):
                    violations.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
