import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is required by the plugin launcher")
    def test_launcher_selects_platform_specific_python_commands(self) -> None:
        script = ROOT / "scripts" / "stitch_mcp_launcher.js"
        program = (
            f"const launcher=require({json.dumps(str(script))});"
            "console.log(JSON.stringify({"
            "win:launcher.pythonCandidates('win32'),"
            "unix:launcher.pythonCandidates('darwin'),"
            "normal:launcher.forwardedExitCode(7,null),"
            "interrupt:launcher.forwardedExitCode(null,'SIGINT'),"
            "terminate:launcher.forwardedExitCode(null,'SIGTERM')"
            "}));"
        )
        result = subprocess.run(
            [shutil.which("node"), "-e", program], capture_output=True, text=True, check=False
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        selected = json.loads(result.stdout)
        self.assertEqual(selected["win"], [["py", ["-3.11"]], ["python", []]])
        self.assertEqual(selected["unix"], [["python3", []], ["python", []]])
        self.assertEqual(selected["normal"], 7)
        self.assertEqual(selected["interrupt"], 130)
        self.assertEqual(selected["terminate"], 143)

    @unittest.skipUnless(os.name != "nt" and shutil.which("node"), "Unix launcher smoke")
    def test_launcher_forwards_stdio_without_putting_secret_in_argv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            arguments = fixture / "arguments.json"
            fake_python = fixture / "python3"
            fake_python.write_text(
                "#!/bin/sh\n"
                "\"$REAL_PYTHON\" -c 'import json,os,sys; open(os.environ[\"ARGS_FILE\"], \"w\").write(json.dumps(sys.argv[1:]))' \"$@\"\n"
                "exec \"$REAL_PYTHON\" \"$@\"\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            environment = os.environ.copy()
            environment.update(
                {
                    "ARGS_FILE": str(arguments),
                    "PATH": os.pathsep.join((directory, os.environ.get("PATH", ""))),
                    "REAL_PYTHON": sys.executable,
                    "STITCH_API_KEY": "fixture-secret-must-not-enter-argv",
                }
            )
            result = subprocess.run(
                [shutil.which("node"), str(ROOT / "scripts" / "stitch_mcp_launcher.js")],
                input="{invalid-json\n",
                capture_output=True,
                text=True,
                env=environment,
                check=False,
            )
            self.assertTrue(arguments.is_file(), result.stdout + result.stderr)
            forwarded = json.loads(arguments.read_text(encoding="utf-8")) if arguments.is_file() else []

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"code":-32700', result.stdout)
        self.assertEqual(forwarded, [str(ROOT / "scripts" / "stitch_mcp_proxy.py")])
        self.assertNotIn("fixture-secret-must-not-enter-argv", json.dumps(forwarded))


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
