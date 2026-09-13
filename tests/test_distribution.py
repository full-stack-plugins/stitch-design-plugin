import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
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
        self.assertIn("validated 41 skills", result.stdout)

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
        self.assertEqual(entry["policy"]["authentication"], "ON_USE")

    def test_plugin_uses_bundled_secret_safe_stdio_proxy(self) -> None:
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

    def test_breaking_identity_uses_stitch_design_everywhere(self) -> None:
        manifest = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["name"], "stitch-design")
        self.assertEqual(manifest["version"], "0.5.1")
        self.assertEqual(manifest["interface"]["displayName"], "Stitch Design")

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
        self.assertIn("默认流程不访问系统钥匙串", guide)
        self.assertIn("ChatGPT 网页版", guide)
        self.assertIn("尚未通过端到端验证", guide)

    def test_stitch_setup_check_never_prints_the_key(self) -> None:
        script = ROOT / "scripts" / "stitch_setup.sh"
        secret = "test-secret-must-not-appear"
        result = subprocess.run(
            [str(script), "check"],
            env={"PATH": "/usr/bin:/bin", "STITCH_API_KEY": secret},
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("STITCH_API_KEY is available", result.stdout)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_stitch_setup_cli_forwards_the_key_without_printing_it(self) -> None:
        script = ROOT / "scripts" / "stitch_setup.sh"
        secret = "test-secret-must-not-appear"
        with tempfile.TemporaryDirectory() as directory:
            fake_codex = Path(directory) / "codex"
            fake_codex.write_text(
                "#!/bin/sh\n"
                "test -n \"$STITCH_API_KEY\" && printf 'key:set args:%s\\n' \"$*\"\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            result = subprocess.run(
                [str(script), "cli", "--", "resume"],
                env={"PATH": f"{directory}:/usr/bin:/bin", "STITCH_API_KEY": secret},
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("key:set args:resume", result.stdout)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_first_use_skill_routes_missing_credentials_to_local_setup(self) -> None:
        skill = (ROOT / "skills" / "stitch-local-setup" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("首次", skill)
        self.assertIn("Stitch Settings", skill)
        self.assertIn("scripts/stitch_setup.py ui", skill)
        self.assertIn("不要让用户把 key 粘贴到聊天", skill)
        self.assertIn("Windows", skill)
        self.assertIn("默认配置不会访问系统钥匙串", skill)

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
                self.assertIn("0.5.1", text)
                self.assertIn("stdio", text)
                self.assertIn("Harness", text)
                self.assertNotIn("env_http_headers", text)

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
