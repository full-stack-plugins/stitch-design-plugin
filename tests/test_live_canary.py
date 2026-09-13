import importlib.util
import json
import os
import stat
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "live_canary.py"


def load_module():
    spec = importlib.util.spec_from_file_location("live_canary", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("live canary script must be importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeBackend:
    def __init__(self, *, fail_at: str | None = None):
        self.fail_at = fail_at
        self.calls: list[str] = []
        self.deleted = False

    def execute(self, stage: str, context: dict, workspace: Path) -> dict:
        self.calls.append(stage)
        if stage == self.fail_at:
            raise RuntimeError(f"failed at {stage}")
        if stage == "create_project":
            return {"project_name": "projects/123456", "project_id": "123456"}
        if stage == "generate":
            return {"screen_name": "projects/123456/screens/" + "a" * 32, "screen_id": "screen-instance"}
        if stage == "download":
            return {"count": 3, "hashes": ["1" * 64, "2" * 64, "3" * 64]}
        if stage == "harness_compare_archive":
            return {"comparison_count": 3, "archive_sha256": "4" * 64}
        return {"ok": True}

    def delete_project(self, context: dict) -> bool:
        self.calls.append("delete_project")
        self.deleted = True
        return True

    def project_absent(self, context: dict) -> bool:
        self.calls.append("project_absent")
        return self.deleted


class LiveCanaryTests(unittest.TestCase):
    def test_bilingual_docs_keep_060_as_candidate_until_live_controller_evidence_exists(self) -> None:
        english = (ROOT / "docs" / "live-canary-acceptance.md").read_text(encoding="utf-8")
        chinese = (ROOT / "docs" / "live-canary-acceptance.zh_CN.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        readme_cn = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        for text in (english, chinese, readme, readme_cn):
            self.assertIn("0.6.0", text)
        self.assertIn("Repository preparation: complete", english)
        self.assertIn("Live Canary: not executed", english)
        self.assertIn("Release/Marketplace: not published", english)
        self.assertIn("仓库准备：已完成", chinese)
        self.assertIn("真实 Canary：未执行", chinese)
        self.assertIn("Release/Marketplace：未发布", chinese)
        self.assertIn("docs/live-canary-acceptance.md", readme)
        self.assertIn("docs/live-canary-acceptance.zh_CN.md", readme_cn)

    def test_workflow_is_manual_secret_only_and_cleanup_is_final_always_step(self) -> None:
        workflow_path = ROOT / ".github" / "workflows" / "live-canary.yml"
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        trigger = workflow.get("on", workflow.get(True))
        self.assertEqual(set(trigger), {"workflow_dispatch"})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        job = workflow["jobs"]["live-canary"]
        self.assertNotIn("env", job, "repository secret must not be inherited by unrelated actions")
        steps = job["steps"]
        commands = "\n".join(str(step.get("run", "")) for step in steps)
        self.assertIn("secrets.STITCH_API_KEY", json.dumps(workflow))
        self.assertNotIn("STITCH_API_KEY=", commands)
        self.assertIn("live_canary.py run", commands)
        secret_steps = [step["name"] for step in steps if "secrets.STITCH_API_KEY" in json.dumps(step)]
        self.assertEqual(
            secret_steps,
            ["Require repository credential", "Run bounded canary chain", "Cleanup remote project and prove absence"],
        )
        self.assertEqual(steps[-1]["name"], "Cleanup remote project and prove absence")
        self.assertEqual(steps[-1]["if"], "${{ always() }}")
        self.assertIn("live_canary.py cleanup", steps[-1]["run"])

    def test_run_uses_unique_title_and_writes_only_sanitized_evidence(self) -> None:
        module = load_module()
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "private" / "state.json"
            evidence = root / "evidence.json"
            result = module.run_canary(
                backend,
                state,
                evidence,
                root / "workspace",
                now=lambda: datetime(2026, 9, 14, 8, 0, tzinfo=UTC),
                nonce="abcdef123456",
            )
            private_state = json.loads(state.read_text(encoding="utf-8"))
            public_evidence = json.loads(evidence.read_text(encoding="utf-8"))
            state_mode = stat.S_IMODE(state.stat().st_mode)

        self.assertEqual(private_state["project_title"], "codex-stitch-canary-20260914t080000z-abcdef123456")
        self.assertEqual(state_mode, 0o600)
        serialized = json.dumps(public_evidence, sort_keys=True)
        for forbidden in ("123456", "projects/", "screen-instance", "project_title", "project_id", "screen_id"):
            self.assertNotIn(forbidden, serialized)
        self.assertTrue(result["stages"]["archive_created"])
        self.assertEqual(result["counts"]["downloaded_files"], 3)
        self.assertEqual(result["counts"]["comparison_files"], 3)
        self.assertEqual(result["hashes"]["archive_sha256"], "4" * 64)

    def test_run_orders_the_complete_canary_chain(self) -> None:
        module = load_module()
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module.run_canary(backend, root / "state.json", root / "evidence.json", root / "workspace")
        self.assertEqual(
            backend.calls,
            [
                "create_project", "generate", "read", "edit", "variant",
                "design_system_create", "design_system_update", "design_system_list",
                "design_system_apply", "upload", "download", "harness_compare_archive",
            ],
        )

    def test_evidence_contract_rejects_identifier_shaped_nested_fields(self) -> None:
        module = load_module()
        evidence = module._public_template("2026-09-14T08:00:00Z")
        evidence["stages"]["project_id"] = True
        with self.assertRaisesRegex(ValueError, "invalid stage fields"):
            module._validate_public_evidence(evidence)

    def test_cleanup_attempts_delete_once_and_records_only_absence_boolean(self) -> None:
        module = load_module()
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            evidence = root / "evidence.json"
            module.run_canary(backend, state, evidence, root / "workspace")
            cleanup = module.cleanup_canary(backend, state, evidence)
            state_payload = json.loads(state.read_text(encoding="utf-8"))
            public_evidence = json.loads(evidence.read_text(encoding="utf-8"))
            cleanup_again = module.cleanup_canary(backend, state, evidence)

        self.assertTrue(cleanup["cleanup"]["delete_requested"])
        self.assertTrue(cleanup["cleanup"]["project_absent"])
        self.assertEqual(backend.calls.count("delete_project"), 1)
        self.assertTrue(state_payload["delete_attempted"])
        self.assertTrue(cleanup_again["cleanup"]["project_absent"])
        self.assertNotIn("project_name", json.dumps(public_evidence))


if __name__ == "__main__":
    unittest.main()
