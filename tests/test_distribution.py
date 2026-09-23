import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CODEX_VERSION = json.loads(
    (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
)["version"]
RELEASE_VERSION = CODEX_VERSION.split("+", 1)[0]
LOCKED_SKILL_COUNT = sum(
    len(source.get("skills", []))
    for source in json.loads((ROOT / "skills.lock.json").read_text(encoding="utf-8")).get(
        "sources", []
    )
)
LOCAL_SKILL_COUNT = len(
    json.loads((ROOT / "plugin-local-skills.json").read_text(encoding="utf-8")).get(
        "skills", []
    )
)
EXPECTED_SKILL_COUNT = LOCKED_SKILL_COUNT + LOCAL_SKILL_COUNT


def fake_codex_command(platform_name: str) -> tuple[str, str]:
    if platform_name == "nt":
        return (
            "codex.cmd",
            "@echo off\r\n"
            "if defined STITCH_API_KEY echo key:set args:%*\r\n",
        )
    return (
        "codex",
        "#!/bin/sh\n"
        "test -n \"$STITCH_API_KEY\" && printf 'key:set args:%s\\n' \"$*\"\n",
    )


def fake_python_command(platform_name: str, executable: str) -> tuple[str, str]:
    if platform_name == "nt":
        return (
            "python.cmd",
            "@echo off\r\n"
            f'"{executable}" %*\r\n',
        )
    return (
        "python",
        "#!/bin/sh\n"
        f'exec "{executable}" "$@"\n',
    )


class DistributionContractTests(unittest.TestCase):
    def test_release_version_is_consistent_across_active_surfaces(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], CODEX_VERSION)

        validator = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_distribution.py"), str(ROOT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(validator.returncode, 0, validator.stdout + validator.stderr)
        self.assertIn(f"compatibility distribution {RELEASE_VERSION}", validator.stdout)

        active_version_surfaces = (
            ROOT / "README.md",
            ROOT / "README.zh-CN.md",
            ROOT / "docs" / "Stitch-Design-Architecture.md",
            ROOT / "docs" / "Stitch-Design-Architecture.zh_CN.md",
            ROOT / "docs" / "Stitch-Design-Technical-Solution.md",
            ROOT / "docs" / "Stitch-Design-Technical-Solution.zh_CN.md",
            ROOT / "stitch_harness" / "preflight.py",
        )
        for path in active_version_surfaces:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIn(RELEASE_VERSION, text)

        self.assertIn(
            f"Current release | [v{RELEASE_VERSION}]",
            (ROOT / "README.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "Previous release | [v0.8.3]",
            (ROOT / "README.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            f"当前版本 | [v{RELEASE_VERSION}]",
            (ROOT / "README.zh-CN.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "上一版本 | [v0.8.3]",
            (ROOT / "README.zh-CN.md").read_text(encoding="utf-8"),
        )

    def test_validate_workflow_covers_cross_platform_offline_gates(self) -> None:
        workflow_path = ROOT / ".github" / "workflows" / "validate.yml"
        self.assertTrue(workflow_path.is_file(), "validate workflow must exist")
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        jobs = workflow["jobs"]

        unix = jobs["unix-offline"]
        self.assertEqual(unix["strategy"]["matrix"]["os"], ["ubuntu-latest", "macos-latest"])
        self.assertEqual(unix["strategy"]["matrix"]["python-version"], ["3.11", "3.13"])
        unix_steps = {step.get("name"): step.get("run") for step in unix["steps"] if "name" in step}
        for name in (
            "Run unit tests",
            "Validate distribution",
            "Validate all Skills",
            "Validate Markdown links",
            "Scan for secrets",
            "Run ShellCheck",
            "Compile Python sources",
            "Verify configured MCP command",
        ):
            self.assertIn(name, unix_steps)
        self.assertEqual(unix_steps["Run unit tests"], "python -m unittest discover -s tests -v")
        self.assertEqual(unix_steps["Validate distribution"], "python scripts/validate_distribution.py .")
        self.assertEqual(unix_steps["Validate all Skills"], "python scripts/validate_skills.py skills")
        self.assertEqual(unix_steps["Validate Markdown links"], "python scripts/validate_markdown_links.py .")
        self.assertEqual(unix_steps["Scan for secrets"], "python scripts/scan_secrets.py .")
        self.assertIn("shellcheck", unix_steps["Run ShellCheck"])
        self.assertIn("python -m compileall", unix_steps["Compile Python sources"])
        self.assertEqual(
            unix_steps["Verify configured MCP command"],
            'python scripts/smoke_mcp_config.py --expected-python "${{ matrix.python-version }}"',
        )

        windows = jobs["windows-offline"]
        self.assertEqual(windows["runs-on"], "windows-latest")
        self.assertEqual(windows["strategy"]["matrix"]["python-version"], ["3.11", "3.13"])
        windows_steps = {step.get("name"): step for step in windows["steps"] if "name" in step}
        for name in (
            "Run unit tests",
            "Validate distribution",
            "Validate all Skills",
            "Validate Markdown links",
            "Scan for secrets",
            "Compile Python sources",
            "Verify configured MCP command",
        ):
            self.assertIn(name, windows_steps)
        self.assertEqual(
            windows_steps["Verify configured MCP command"]["run"],
            'python scripts/smoke_mcp_config.py --expected-python "${{ matrix.python-version }}"',
        )

    def test_workflow_actions_are_pinned_to_immutable_commits(self) -> None:
        workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertTrue(workflows, "expected at least one workflow")
        pinned: list[str] = []
        for workflow_path in workflows:
            workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
            for job_name, job in workflow["jobs"].items():
                for step in job.get("steps", []):
                    reference = step.get("uses")
                    if reference is None:
                        continue
                    revision = reference.split("@", 1)[1].split()[0]
                    self.assertEqual(
                        len(revision),
                        40,
                        f"{workflow_path.name}:{job_name} must pin a full commit SHA: {reference}",
                    )
                    self.assertTrue(
                        all(character in "0123456789abcdef" for character in revision),
                        f"{workflow_path.name}:{job_name} must pin a lowercase hex SHA: {reference}",
                    )
                    pinned.append(reference)
        self.assertEqual(
            sorted({reference.split("@", 1)[0] for reference in pinned}),
            ["actions/checkout", "actions/setup-python"],
            "release provenance requires every workflow action to be pinned and inventoried",
        )

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
        self.assertIn(f"validated {EXPECTED_SKILL_COUNT} skills", result.stdout)

    def test_repository_marketplace_targets_public_root_plugin(self) -> None:
        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
        )
        entry = next(plugin for plugin in marketplace["plugins"] if plugin["name"] == "stitch-design")

        self.assertEqual(entry["source"]["source"], "url")
        self.assertEqual(
            entry["source"]["url"],
            "https://github.com/full-stack-plugins/stitch-design-plugin.git",
        )
        self.assertEqual(entry["source"]["ref"], f"v{RELEASE_VERSION}")
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
        self.assertEqual(entry["policy"]["authentication"], "ON_USE")

    def test_plugin_uses_python3_secret_safe_stdio_proxy(self) -> None:
        config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        server = config["mcpServers"]["stitch"]

        self.assertEqual(
            server,
            {
                "type": "stdio",
                "command": "python3",
                "args": ["scripts/stitch_mcp_proxy.py"],
                "cwd": ".",
            },
        )

    def test_active_distribution_has_no_node_launcher_dependency(self) -> None:
        self.assertFalse((ROOT / "scripts" / "stitch_mcp_launcher.js").exists())
        active_paths = (
            ROOT / ".mcp.json",
            ROOT / ".github" / "workflows" / "validate.yml",
            ROOT / "README.md",
            ROOT / "README.zh-CN.md",
            ROOT / "docs" / "Stitch-Design-Architecture.md",
            ROOT / "docs" / "Stitch-Design-Architecture.zh_CN.md",
            ROOT / "docs" / "Stitch-Design-Technical-Solution.md",
            ROOT / "docs" / "Stitch-Design-Technical-Solution.zh_CN.md",
            ROOT / "docs" / "getting-started.zh-CN.md",
            ROOT / "scripts" / "validate_distribution.py",
        )
        for path in active_paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotIn("stitch_mcp_launcher.js", text)
                self.assertNotIn('"command": "node"', text)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        guide = (ROOT / "docs" / "getting-started.zh-CN.md").read_text(encoding="utf-8")
        self.assertIn("The `python` command on PATH must resolve to Python 3.11 or newer", readme)
        self.assertIn("PATH 中的 `python` 命令必须解析为 Python 3.11 或更高版本", readme_zh)
        self.assertIn("Windows 同样使用 `python` 命令", guide)
        self.assertNotIn("Windows 将 `python3` 替换为 `py`", guide)
        setup_skill = (ROOT / "skills" / "stitch-local-setup" / "SKILL.md").read_text(encoding="utf-8")
        setup_wrapper = (ROOT / "scripts" / "stitch_setup.sh").read_text(encoding="utf-8")
        self.assertIn("PATH 中的 `python` 必须解析为 Python 3.11 或更高版本", setup_skill)
        self.assertNotIn("python3 ", setup_skill)
        self.assertNotIn("py C:", setup_skill)
        self.assertIn('exec python "$SCRIPT_DIR/stitch_setup.py" "$@"', setup_wrapper)
        self.assertNotIn("exec python3", setup_wrapper)
        for path in (
            ROOT / "docs" / "Stitch-Design-Architecture.md",
            ROOT / "docs" / "Stitch-Design-Technical-Solution.md",
        ):
            self.assertIn("PATH `python` must resolve to Python 3.11 or newer", path.read_text(encoding="utf-8"))
        for path in (
            ROOT / "docs" / "Stitch-Design-Architecture.zh_CN.md",
            ROOT / "docs" / "Stitch-Design-Technical-Solution.zh_CN.md",
        ):
            self.assertIn("PATH 的 `python` 必须解析为 Python 3.11 或更高版本", path.read_text(encoding="utf-8"))

    def test_breaking_identity_uses_stitch_design_everywhere(self) -> None:
        manifest = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["name"], "stitch-design")
        self.assertEqual(manifest["version"], CODEX_VERSION)
        self.assertEqual(manifest["interface"]["displayName"], "Google Stitch Design")

    def test_portable_files_are_not_activated_without_portable_auth(self) -> None:
        self.assertFalse((ROOT / "plugin.json").exists())
        self.assertFalse((ROOT / "mcp.json").exists())
        migration = (ROOT / "docs" / "portable-migration.md").read_text(encoding="utf-8")

        self.assertIn("plugin_asdk_app", migration)
        self.assertIn("MUST NOT perform placeholder", migration)

    def test_local_setup_guide_separates_plugin_mcp_and_credentials(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        guide = (ROOT / "docs" / "getting-started.zh-CN.md").read_text(encoding="utf-8")

        self.assertIn("[简体中文](README.zh-CN.md)", readme)
        self.assertIn("第一次使用", readme_zh)
        self.assertIn("安装插件时会自动加载 `.mcp.json`", guide)
        self.assertIn("SDK 仍然需要 `STITCH_API_KEY`", guide)
        self.assertIn("不需要克隆插件仓库", guide)
        self.assertIn("Windows", guide)
        self.assertIn("所有平台默认写入当前用户的受限配置文件", guide)
        self.assertIn("ChatGPT 网页版", guide)
        self.assertIn("尚未通过端到端验证", guide)
        for text in (readme, readme_zh, guide):
            self.assertNotIn("stitch_setup.py migrate", text)
            self.assertNotIn("Native system-store migration", text)

    def test_readmes_use_real_marketplace_install_commands_and_visual_metrics(self) -> None:
        readmes = (
            (ROOT / "README.md").read_text(encoding="utf-8"),
            (ROOT / "README.zh-CN.md").read_text(encoding="utf-8"),
        )
        required = (
            f"codex plugin marketplace add full-stack-plugins/stitch-design-plugin --ref v{RELEASE_VERSION}",
            f"codex plugin marketplace add https://github.com/full-stack-plugins/stitch-design-plugin.git --ref v{RELEASE_VERSION}",
            "--sparse .agents/plugins",
            "codex plugin marketplace add ./partme-stitch-plugin",
            "codex plugin add stitch-design@partme-ai-stitch",
            "tests-379%20passing",
            "MCP%20tools-17",
            "assets/stitch-hero.png",
        )
        for readme in readmes:
            for value in required:
                self.assertIn(value, readme)

    def test_bilingual_overview_counts_current_skill_inventory(self) -> None:
        self.assertIn("43 workflow-oriented Agent Skills", (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn("43 个面向工作流的 Agent Skills", (ROOT / "README.zh-CN.md").read_text(encoding="utf-8"))

    def test_public_docs_remove_native_store_and_describe_403_without_replay(self) -> None:
        paths = (
            ROOT / "README.md", ROOT / "README.zh-CN.md", ROOT / "PRIVACY.md",
            ROOT / "docs/Stitch-Design-Architecture.md",
            ROOT / "docs/Stitch-Design-Architecture.zh_CN.md",
            ROOT / "docs/Stitch-Design-Technical-Solution.md",
            ROOT / "docs/Stitch-Design-Technical-Solution.zh_CN.md",
            ROOT / "docs/getting-started.zh-CN.md",
        )
        stale = (
            "system secret store", "system-secret-store", "native system store",
            "native secret store", "keychain", "credential manager", "secret service",
            "系统秘密存储", "系统钥匙串",
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            normalized = text.casefold()
            with self.subTest(path=path.name):
                for phrase in stale:
                    self.assertNotIn(phrase.casefold(), normalized)
        privacy = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
        self.assertIn("Only HTTP 401", privacy)
        self.assertIn("HTTP 403 is permission denied and is not refreshed or replayed", privacy)

    def test_manifest_and_readmes_remain_truthful_at_current_version(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], CODEX_VERSION)
        for path in (ROOT / "README.md", ROOT / "README.zh-CN.md"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn(RELEASE_VERSION, text)

    def test_stitch_setup_check_never_prints_the_key(self) -> None:
        script = ROOT / "scripts" / "stitch_setup.sh"
        shell = shutil.which("sh")
        if shell is None:
            self.skipTest("POSIX-compatible shell is not available")
        secret = "test-secret-must-not-appear"
        with tempfile.TemporaryDirectory() as directory:
            shim_name, shim_body = fake_python_command(os.name, sys.executable)
            shim = Path(directory) / shim_name
            shim.write_text(shim_body, encoding="utf-8")
            if os.name != "nt":
                shim.chmod(0o755)
            result = subprocess.run(
                [shell, str(script), "check"],
                env={
                    "PATH": os.pathsep.join((directory, os.environ.get("PATH", ""))),
                    "STITCH_API_KEY": secret,
                    "STITCH_DISABLE_ADC": "1",
                },
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("STITCH_API_KEY is available", result.stdout)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_stitch_setup_cli_forwards_the_key_without_printing_it(self) -> None:
        script = ROOT / "scripts" / "stitch_setup.sh"
        shell = shutil.which("sh")
        self.assertIsNotNone(shell, "POSIX-compatible shell is required for the wrapper test")
        assert shell is not None
        secret = "test-secret-must-not-appear"
        with tempfile.TemporaryDirectory() as directory:
            command_name, command_body = fake_codex_command(os.name)
            fake_codex = Path(directory) / command_name
            fake_codex.write_text(command_body, encoding="utf-8")
            if os.name != "nt":
                fake_codex.chmod(0o755)
            shim_name, shim_body = fake_python_command(os.name, sys.executable)
            shim = Path(directory) / shim_name
            shim.write_text(shim_body, encoding="utf-8")
            if os.name != "nt":
                shim.chmod(0o755)
            environment = {
                "PATH": os.pathsep.join((directory, os.environ.get("PATH", ""))),
                "STITCH_API_KEY": secret,
            }
            if os.name == "nt":
                environment["PATHEXT"] = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD")
                for variable in ("SystemRoot", "WINDIR", "COMSPEC", "TEMP", "TMP"):
                    if variable in os.environ:
                        environment[variable] = os.environ[variable]
            result = subprocess.run(
                [shell, str(script), "cli", "--", "resume"],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("key:set args:resume", result.stdout)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_fake_codex_command_covers_posix_and_windows_lookup_contracts(self) -> None:
        posix_name, posix_body = fake_codex_command("posix")
        windows_name, windows_body = fake_codex_command("nt")

        self.assertEqual(posix_name, "codex")
        self.assertTrue(posix_body.startswith("#!/bin/sh\n"))
        self.assertEqual(windows_name, "codex.cmd")
        self.assertTrue(windows_body.startswith("@echo off\r\n"))
        for body in (posix_body, windows_body):
            self.assertIn("STITCH_API_KEY", body)
            self.assertNotIn("test-secret-must-not-appear", body)

    def test_first_use_skill_routes_missing_credentials_to_local_setup(self) -> None:
        skill = (ROOT / "skills" / "stitch-local-setup" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("首次", skill)
        self.assertIn("Stitch Settings", skill)
        self.assertIn("scripts/stitch_setup.py ui", skill)
        self.assertIn("不要让用户把 key 粘贴到聊天", skill)
        self.assertIn("Windows", skill)
        self.assertIn("凭据仅来自当前进程或受限的用户配置文件", skill)

    def test_delivery_harness_skill_exposes_verified_handoff_contract(self) -> None:
        skill = (ROOT / "skills" / "stitch-delivery-harness" / "SKILL.md").read_text(encoding="utf-8")
        workflow = (ROOT / "skills" / "stitch-delivery-harness" / "references" / "workflow.md").read_text(encoding="utf-8")

        self.assertIn("scripts/stitch_harness.py", skill)
        self.assertIn("AWAITING_USER_APPROVAL", skill)
        self.assertIn("不能以工具成功文本标记完成", skill)
        ordered = ["页面规格", "Stitch 生成", "HTML/尺寸/文案", "ImageGen", "OCR/业务", "回灌", "可编辑性", "双图对比", "用户批准", "正式归档"]
        positions = [workflow.index(value) for value in ordered]
        self.assertEqual(positions, sorted(positions))

        loop = (ROOT / "skills" / "stitch-loop" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("stitch-delivery-harness", loop)
        self.assertIn("不能以工具成功文本标记完成", loop)

    def test_delivery_harness_documents_receipt_bound_compare_and_reconciliation(self) -> None:
        skill_root = ROOT / "skills" / "stitch-delivery-harness"
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        workflow = (skill_root / "references" / "workflow.md").read_text(encoding="utf-8")
        combined = skill + workflow

        self.assertIn("reconcile --project", combined)
        self.assertIn("--evidence", combined)
        self.assertIn("从 receipts", combined)
        self.assertNotIn("--stitch /absolute", combined)
        self.assertNotIn("--art /absolute", combined)

    def test_architecture_documents_describe_secure_harness_boundaries(self) -> None:
        paths = [
            ROOT / "docs" / "Stitch-Design-Architecture.md",
            ROOT / "docs" / "Stitch-Design-Architecture.zh_CN.md",
            ROOT / "docs" / "Stitch-Design-Technical-Solution.md",
            ROOT / "docs" / "Stitch-Design-Technical-Solution.zh_CN.md",
        ]

        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn(RELEASE_VERSION, text)
                self.assertIn("stdio", text)
                self.assertIn("Harness", text)
                self.assertNotIn("env_http_headers", text)

        architecture = paths[0].read_text(encoding="utf-8")
        self.assertNotIn("environment or system store found", architecture)
        self.assertIn("environment or restricted user config found", architecture)
        self.assertIn(f"stitch-design {RELEASE_VERSION}", architecture)

    def test_stitch_setup_stores_key_in_supplied_secret_provider(self) -> None:
        script = ROOT / "scripts" / "stitch_setup.py"
        secret = "config-secret-must-not-appear"

        class FakeSecretProvider:
            value = None

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "credentials.json"
            spec = importlib.util.spec_from_file_location("stitch_setup", script)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            provider = FakeSecretProvider()
            module.save_key(secret, provider)

        self.assertEqual(provider.get(), secret)
        self.assertFalse(config.exists())

    def test_stitch_setup_respects_an_explicit_secret_provider(self) -> None:
        script = ROOT / "scripts" / "stitch_setup.py"
        secret = "config-secret-must-not-appear"

        class EmptySecretProvider:
            def get(self):
                return None

            def set(self, value):
                raise AssertionError("read test must not write")

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "credentials.json"
            config.write_text(json.dumps({"STITCH_API_KEY": secret}), encoding="utf-8")
            spec = importlib.util.spec_from_file_location("stitch_setup", script)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            value = module.load_key(EmptySecretProvider())
            preserved = config.read_text(encoding="utf-8")

        self.assertIsNone(value)
        self.assertIn(secret, preserved)


if __name__ == "__main__":
    unittest.main()
