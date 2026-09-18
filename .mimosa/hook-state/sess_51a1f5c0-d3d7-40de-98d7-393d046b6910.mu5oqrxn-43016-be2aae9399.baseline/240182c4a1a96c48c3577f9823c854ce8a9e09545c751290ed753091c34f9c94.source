import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PythonEntrypointTests(unittest.TestCase):
    def test_proxy_entrypoint_rejects_python_below_311_with_diagnostic(self) -> None:
        script = ROOT / "scripts" / "stitch_mcp_proxy.py"
        spec = importlib.util.spec_from_file_location("stitch_mcp_proxy_entrypoint", script)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(
            hasattr(module, "require_supported_python"),
            "proxy entrypoint must expose its minimum-version check",
        )
        errors = io.StringIO()

        with contextlib.redirect_stderr(errors):
            supported = module.require_supported_python((3, 10)) if hasattr(module, "require_supported_python") else True

        self.assertFalse(supported)
        self.assertIn("Python 3.11 or newer", errors.getvalue())

    def test_configured_proxy_smoke_verifies_current_python(self) -> None:
        expected = f"{sys.version_info.major}.{sys.version_info.minor}"
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "smoke_mcp_config.py"),
                "--expected-python",
                expected,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"configured Python {expected}", result.stdout)
        self.assertIn("proxy smoke passed", result.stdout)


class RepositoryValidatorTests(unittest.TestCase):
    def run_validator(self, script: str, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script), str(root)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_repo_local_skill_validator_accepts_all_skills(self) -> None:
        result = self.run_validator("validate_skills.py", ROOT / "skills")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("validated 43 skills", result.stdout)

    def test_skill_validator_rejects_invalid_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "bad-skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\nname: bad-skill\ndescription: valid description\nunexpected: true\n---\nBody\n",
                encoding="utf-8",
            )
            result = self.run_validator("validate_skills.py", Path(directory))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected frontmatter key", result.stderr)

    def test_skill_validator_rejects_malformed_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "bad-skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\nname: bad-skill\ndescription: [unterminated\n---\nBody\n",
                encoding="utf-8",
            )
            result = self.run_validator("validate_skills.py", Path(directory))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid YAML frontmatter", result.stderr)

    def test_markdown_link_validator_accepts_repository(self) -> None:
        result = self.run_validator("validate_markdown_links.py", ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_markdown_link_validator_rejects_missing_relative_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("[missing](docs/missing.md)\n", encoding="utf-8")
            result = self.run_validator("validate_markdown_links.py", root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("docs/missing.md", result.stderr)

    def test_secret_scanner_detects_fixture_without_echoing_secret(self) -> None:
        secret = "gh" + "p_" + "A" * 36
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "positive.txt").write_text(secret, encoding="utf-8")
            result = self.run_validator("scan_secrets.py", root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("positive.txt", result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_secret_scanner_allows_placeholders_and_pattern_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "negative.txt").write_text(
                "STITCH_API_KEY=test-secret-must-not-appear\nAIza[0-9A-Za-z_-]{20,}\n",
                encoding="utf-8",
            )
            result = self.run_validator("scan_secrets.py", root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
