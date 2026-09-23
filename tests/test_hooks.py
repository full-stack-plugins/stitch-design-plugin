"""Smoke tests for the advisory hook scripts under hooks/.

Both hooks must stay advisory: exit 0 on every input, silent when not
applicable, and never crash on malformed stdin.
"""

import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
INTENT_HOOK = ROOT / "hooks" / "check_stitch_intent.py"
ENV_HOOK = ROOT / "hooks" / "env_check.py"


def run_hook(script, stdin_text=""):
    return subprocess.run(
        [sys.executable, str(script)],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


class StitchIntentHookTests(unittest.TestCase):
    def test_stitch_shaped_prompts_print_command_hint(self):
        for token in (
            "stitch", "设计稿", "生成页面", "生成界面", "做个 UI 设计",
            "设计系统", "组件库", "design-system", "design system", "设计转代码",
            "STITCH", "帮我生成界面",
        ):
            with self.subTest(token=token):
                result = run_hook(INTENT_HOOK, json.dumps({"prompt": f"帮我 {token} 一下"}))
                self.assertEqual(result.returncode, 0)
                self.assertIn("/stitch", result.stdout)
                self.assertIn("/stitch-loop", result.stdout)

    def test_unrelated_prompt_is_silent(self):
        for prompt in ("今天天气怎么样", "fix the login bug", ""):
            with self.subTest(prompt=prompt):
                result = run_hook(INTENT_HOOK, json.dumps({"prompt": prompt}))
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_slash_command_is_silent(self):
        for prompt in ("/stitch", "/stitch-ui-designer 设计系统", "/compact"):
            with self.subTest(prompt=prompt):
                result = run_hook(INTENT_HOOK, json.dumps({"prompt": prompt}))
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_malformed_or_empty_stdin_is_silent_and_exits_zero(self):
        for stdin_text in ("{not json", "", "\x00\xff", json.dumps(["not", "a", "dict"])):
            with self.subTest(stdin=repr(stdin_text)[:20]):
                result = run_hook(INTENT_HOOK, stdin_text)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_missing_prompt_key_is_silent(self):
        result = run_hook(INTENT_HOOK, json.dumps({"other": "stitch 设计系统"}))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


class EnvCheckHookTests(unittest.TestCase):
    def test_reports_python_version_and_ready_proxy(self):
        result = run_hook(ENV_HOOK, json.dumps({}))
        self.assertEqual(result.returncode, 0)
        self.assertIn("Stitch 插件环境", result.stdout)
        self.assertIn(f"python3: {sys.version.split()[0]}", result.stdout)
        self.assertIn("Stitch MCP proxy: 就绪", result.stdout)

    def test_malformed_stdin_still_exits_zero(self):
        for stdin_text in ("{broken", "", "null"):
            with self.subTest(stdin=repr(stdin_text)):
                result = run_hook(ENV_HOOK, stdin_text)
                self.assertEqual(result.returncode, 0)
                self.assertIn("Stitch 插件环境", result.stdout)

    def test_reports_missing_proxy_script(self):
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "hooks" / "env_check.py"
            copied.parent.mkdir(parents=True)
            shutil.copy2(ENV_HOOK, copied)
            result = run_hook(copied, json.dumps({}))
        self.assertEqual(result.returncode, 0)
        self.assertIn("Stitch MCP proxy: 脚本缺失", result.stdout)

    def test_warns_when_python_below_311(self):
        spec = importlib.util.spec_from_file_location("env_check", ENV_HOOK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = io.StringIO()
        with mock.patch("sys.version_info", (3, 10, 14)), \
             mock.patch("sys.stdin", io.StringIO("")), \
             contextlib.redirect_stdout(output):
            code = module.main()
        self.assertEqual(code, 0)
        self.assertIn("需要 Python 3.11+", output.getvalue())


if __name__ == "__main__":
    unittest.main()
