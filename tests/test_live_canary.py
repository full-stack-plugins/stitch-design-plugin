import importlib.util
import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from unittest import mock
from datetime import UTC, datetime
from pathlib import Path

import yaml

from stitch_harness.assets import local_tool_definitions
from stitch_harness.mcp_proxy import ProxyError, UnknownWriteResult


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
        if stage == "read":
            return {"screen_count": 1}
        if stage == "variant":
            return {"variant_count": 1}
        if stage == "design_system_list":
            return {"design_system_count": 1}
        if stage == "upload":
            return {"upload_count": 1}
        if stage == "download":
            return {"count": 3, "manifest_sha256": "4" * 64}
        return {"ok": True}

    def delete_project(self, context: dict) -> bool:
        self.calls.append("delete_project")
        self.deleted = True
        return True

    def project_absent(self, context: dict) -> bool:
        self.calls.append("project_absent")
        return self.deleted

    def find_project_by_title(self, title: str):
        self.calls.append("find_project_by_title")
        return None


class LiveCanaryTests(unittest.TestCase):
    def test_bilingual_docs_record_060_harness_and_repo_release_gates(self) -> None:
        english = (ROOT / "docs" / "live-canary-acceptance.md").read_text(encoding="utf-8")
        chinese = (ROOT / "docs" / "live-canary-acceptance.zh_CN.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        readme_cn = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        for text in (english, chinese, readme, readme_cn):
            self.assertIn("0.6.0", text)
        self.assertIn("Repository preparation: complete", english)
        self.assertIn("Provider + asset live smoke: passed locally", english)
        self.assertIn("Harness acceptance: passed and archived locally", english)
        self.assertIn("GitHub Release/repo Marketplace: v0.6.0 published", english)
        self.assertIn("仓库准备：已完成", chinese)
        self.assertIn("Provider + asset 真实 smoke：2026-09-14 本机通过", chinese)
        self.assertIn("Harness 验收：本机通过并归档", chinese)
        self.assertIn("GitHub Release/仓库 Marketplace：v0.6.0 已发布", chinese)
        self.assertIn("docs/live-canary-acceptance.md", readme)
        self.assertIn("docs/live-canary-acceptance.zh_CN.md", readme_cn)
        controller = (ROOT / "docs" / "live-harness-controller.md").read_text(encoding="utf-8")
        controller_cn = (ROOT / "docs" / "live-harness-controller.zh_CN.md").read_text(encoding="utf-8")
        self.assertIn("not Harness acceptance", english)
        self.assertIn("不是 Harness 验收", chinese)
        self.assertIn("scripts/setup_harness_runtime.py run", controller)
        self.assertIn("explicit human approval", controller)
        self.assertIn("明确人工批准", controller_cn)

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
        self.assertIn("validate-evidence-schema", commands)
        self.assertIn("validate-acceptance", steps[-1]["run"])
        self.assertFalse(steps[0].get("with", {}).get("persist-credentials", True))
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
        if os.name != "nt":
            self.assertEqual(state_mode, 0o600)
        serialized = json.dumps(public_evidence, sort_keys=True)
        for forbidden in ("123456", "projects/", "screen-instance", "project_title", "project_id", "screen_id"):
            self.assertNotIn(forbidden, serialized)
        self.assertNotIn("archive_created", result["stages"])
        self.assertEqual(result["counts"]["downloaded_files"], 3)
        self.assertEqual(result["counts"]["screens_read"], 1)
        self.assertEqual(result["hashes"]["download_manifest_sha256"], "4" * 64)

    def test_windows_like_atomic_write_disables_posix_mode_without_mutating_os_name(self) -> None:
        module = load_module()
        private_value = "private-value-must-not-be-printed"
        output = io.StringIO()

        def must_not_set_mode(_descriptor: int, _mode: int) -> None:
            raise AssertionError("POSIX mode setter must not run")

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "private.json"
            with (
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(output),
            ):
                module._atomic_private_json(
                    destination,
                    {"value": private_value},
                    enforce_posix_mode=False,
                    mode_setter=must_not_set_mode,
                )
            payload = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(payload, {"value": private_value})
        self.assertNotIn(private_value, output.getvalue())
        if os.name == "nt":
            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "real-windows-private.json"
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    module._atomic_private_json(destination, {"value": private_value})
                self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), {"value": private_value})
            self.assertNotIn(private_value, output.getvalue())

    def test_permission_failure_closes_descriptor_before_removing_temporary_file(self) -> None:
        module = load_module()
        descriptors: list[int] = []
        real_mkstemp = tempfile.mkstemp

        def recording_mkstemp(*args, **kwargs):
            descriptor, name = real_mkstemp(*args, **kwargs)
            descriptors.append(descriptor)
            return descriptor, name

        def denied_mode(_descriptor: int, _mode: int) -> None:
            raise PermissionError("denied")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "private.json"
            with (
                mock.patch.object(module.tempfile, "mkstemp", side_effect=recording_mkstemp),
                self.assertRaises(PermissionError),
            ):
                module._atomic_private_json(
                    destination,
                    {"value": "private"},
                    enforce_posix_mode=True,
                    mode_setter=denied_mode,
                )
            leftovers = list(root.iterdir())
        self.assertEqual(leftovers, [])
        self.assertEqual(len(descriptors), 1)
        with self.assertRaises(OSError):
            os.fstat(descriptors[0])

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
                "design_system_apply", "upload", "download",
            ],
        )

    def test_evidence_contract_rejects_identifier_shaped_nested_fields(self) -> None:
        module = load_module()
        evidence = module._public_template("2026-09-14T08:00:00Z")
        evidence["stages"]["project_id"] = True
        with self.assertRaisesRegex(ValueError, "invalid stage fields"):
            module._validate_public_evidence(evidence)

    def test_schema_validation_is_separate_from_completed_acceptance(self) -> None:
        module = load_module()
        evidence = module._public_template("2026-09-14T08:00:00Z")
        module._validate_evidence_schema(evidence)
        with self.assertRaisesRegex(ValueError, "acceptance"):
            module._validate_acceptance_evidence(evidence)

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
        module._validate_acceptance_evidence(cleanup)
        self.assertEqual(backend.calls.count("delete_project"), 1)
        self.assertTrue(state_payload["delete_attempted"])
        self.assertTrue(cleanup_again["cleanup"]["project_absent"])
        self.assertNotIn("project_name", json.dumps(public_evidence))

    def test_cleanup_reads_absence_even_when_delete_result_is_unknown(self) -> None:
        module = load_module()

        class UnknownDeleteBackend(FakeBackend):
            def delete_project(self, context: dict) -> bool:
                self.calls.append("delete_project")
                self.deleted = True
                raise UnknownWriteResult("unknown")

        backend = UnknownDeleteBackend()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            evidence = root / "evidence.json"
            module.run_canary(backend, state, evidence, root / "workspace")
            cleanup = module.cleanup_canary(backend, state, evidence)
        self.assertEqual(backend.calls[-2:], ["delete_project", "project_absent"])
        self.assertTrue(cleanup["cleanup"]["project_absent"])

    def test_cleanup_reconciles_private_title_before_single_delete_when_identity_was_not_checkpointed(self) -> None:
        module = load_module()

        class EventuallyVisibleBackend(FakeBackend):
            def __init__(self):
                super().__init__()
                self.lookups = 0

            def find_project_by_title(self, title: str):
                self.calls.append("find_project_by_title")
                self.lookups += 1
                if self.lookups == 1:
                    return None
                return {"project_name": "projects/123456", "project_id": "123456"}

        backend = EventuallyVisibleBackend()
        sleeps: list[float] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            evidence = root / "evidence.json"
            module._atomic_private_json(state, {
                "project_title": "codex-stitch-canary-private-title", "delete_attempted": False,
            })
            module._write_public_evidence(evidence, module._public_template("2026-09-14T08:00:00Z"))
            cleanup = module.cleanup_canary(
                backend, state, evidence,
                reconciliation_attempts=3, backoff_seconds=0.25, sleeper=sleeps.append,
            )
            checkpoint = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(backend.calls.count("find_project_by_title"), 2)
        self.assertEqual(backend.calls.count("delete_project"), 1)
        self.assertEqual(backend.calls[-1], "project_absent")
        self.assertEqual(checkpoint["project_name"], "projects/123456")
        self.assertTrue(checkpoint["delete_attempted"])
        self.assertEqual(sleeps, [0.25])
        self.assertTrue(cleanup["cleanup"]["project_absent"])

    def test_cleanup_zero_title_matches_stays_unknown_and_never_deletes(self) -> None:
        module = load_module()
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            evidence = root / "evidence.json"
            module._atomic_private_json(state, {"project_title": "private-title", "delete_attempted": False})
            module._write_public_evidence(evidence, module._public_template("2026-09-14T08:00:00Z"))
            with self.assertRaisesRegex(ProxyError, "identity"):
                module.cleanup_canary(
                    backend, state, evidence,
                    reconciliation_attempts=2, backoff_seconds=0, sleeper=lambda _delay: None,
                )
            public = json.loads(evidence.read_text(encoding="utf-8"))
        self.assertEqual(backend.calls.count("find_project_by_title"), 2)
        self.assertNotIn("delete_project", backend.calls)
        self.assertFalse(public["cleanup"]["project_absent"])


class RecordingSession:
    def __init__(self, tools: list[dict], *, create_unknown: bool = False, delete_unknown: bool = False, variant_same_source: bool = False, response_mutator=None):
        split = len(tools) // 2
        self.pages = (tools[:split], tools[split:])
        self.create_unknown = create_unknown
        self.delete_unknown = delete_unknown
        self.variant_same_source = variant_same_source
        self.deleted = False
        self.response_mutator = response_mutator
        self.requests: list[dict] = []

    @staticmethod
    def _screen(project_id: str) -> dict:
        return {"id": "instance-1", "sourceScreen": f"projects/{project_id}/screens/" + "a" * 32}

    def send(self, request: dict) -> list[dict]:
        self.requests.append(json.loads(json.dumps(request)))
        method = request["method"]
        if method == "notifications/initialized":
            return []
        identifier = request["id"]
        if method == "initialize":
            structured = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}}
        elif method == "tools/list":
            cursor = request.get("params", {}).get("cursor")
            structured = {"tools": self.pages[0], "nextCursor": "page-2"} if cursor is None else {"tools": self.pages[1]}
        else:
            name = request["params"]["name"]
            arguments = request["params"]["arguments"]
            if name == "create_project" and self.create_unknown:
                self.create_unknown = False
                raise UnknownWriteResult("unknown create")
            project_id = arguments.get("projectId", "123456")
            outputs = {
                "create_project": {"name": "projects/123456"},
                "list_projects": {"projects": [] if self.deleted else [{"name": "projects/123456", "title": "canary-title"}]},
                "generate_screen_from_text": {
                    "projectId": project_id,
                    "sessionId": "session-1",
                    "outputComponents": [
                        {"designSystem": {"name": "projects/123456/assets/system-1", "version": "1"}},
                        {"design": {"screens": [{
                            "id": "instance-1",
                            "name": f"projects/{project_id}/screens/" + "a" * 32,
                            "deviceType": "MOBILE",
                            "width": "390",
                            "height": "884",
                            "htmlCode": {
                                "name": f"projects/{project_id}/files/html-1",
                                "downloadUrl": "https://example.invalid/screen.html",
                                "mimeType": "text/html",
                            },
                            "screenshot": {
                                "name": f"projects/{project_id}/files/image-1",
                                "downloadUrl": "https://example.invalid/screen.png",
                            },
                        }]}, "theme": {}},
                        {"text": "Generated one screen"},
                    ],
                },
                "get_project": {"name": "projects/123456", "title": "canary-title"},
                "list_screens": {},
                "get_screen": {"htmlCode": {"mimeType": "text/html"}, "screenshot": {"mimeType": "image/png"}},
                "edit_screens": {"screens": [self._screen("123456")]},
                "generate_variants": {"screens": [
                    self._screen("123456") if self.variant_same_source else {
                        "id": "instance-variant",
                        "sourceScreen": "projects/123456/screens/" + "c" * 32,
                    }
                ]},
                "create_design_system": {"name": "assets/asset-1", "designSystem": arguments.get("designSystem")},
                "update_design_system": {
                    "name": "projects/123456/sessions/session-1",
                    "designSystem": {
                        **arguments.get("designSystem", {}),
                        "theme": {
                            **arguments.get("designSystem", {}).get("theme", {}),
                            "bodyFontFamily": "Inter",
                        },
                    },
                },
                "list_design_systems": {"designSystems": [{"name": "assets/asset-1"}]},
                "apply_design_system": {"outputComponents": [{"design": {"screens": [{
                    "id": "instance-applied",
                    "name": "projects/123456/screens/" + "d" * 32,
                }]}}]},
                "stitch_local_upload_asset": {"screens": [{"name": "projects/123456/screens/" + "1" * 19}]},
                "stitch_local_download_assets": {
                    "outputDir": arguments.get("outputDir"), "count": 1,
                    "files": [{"path": "assets/screen.png", "sha256": "5" * 64, "mime": "image/png", "size": 10}],
                },
                "delete_project": {},
            }
            if name == "delete_project" and self.delete_unknown:
                self.delete_unknown = False
                self.deleted = True
                raise UnknownWriteResult("unknown delete")
            structured = outputs[name]
        result = structured if method in {"initialize", "tools/list"} else {"structuredContent": structured}
        response = {"jsonrpc": "2.0", "id": identifier, "result": result}
        if self.response_mutator is not None:
            response = self.response_mutator(request, response)
        return [response]


class StitchBackendProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        fixture = json.loads((ROOT / "tests" / "fixtures" / "stitch-tool-contract.json").read_text(encoding="utf-8"))
        self.tools = fixture["tools"] + local_tool_definitions()

    def test_handshake_sends_initialized_notification_and_validates_cursor_catalog(self) -> None:
        session = RecordingSession(self.tools)
        backend = self.module.StitchBackend(session=session)
        result = backend.execute("create_project", {"project_title": "canary-title"}, Path("."))
        methods = [request["method"] for request in session.requests]
        self.assertEqual(methods[:4], ["initialize", "notifications/initialized", "tools/list", "tools/list"])
        self.assertEqual(session.requests[2]["params"], {})
        self.assertEqual(session.requests[3]["params"], {"cursor": "page-2"})
        self.assertEqual(result["project_name"], "projects/123456")

    def test_tool_parser_rejects_mismatched_id_and_is_error(self) -> None:
        def mismatch(_request, response):
            response["id"] = "wrong"
            return response

        with self.assertRaisesRegex(ProxyError, "response"):
            self.module.StitchBackend(session=RecordingSession(self.tools, response_mutator=mismatch)).execute(
                "create_project", {"project_title": "canary-title"}, Path(".")
            )

        def tool_error(request, response):
            if request["method"] == "tools/call":
                response["result"]["isError"] = True
            return response

        with self.assertRaisesRegex(ProxyError, "tool result"):
            self.module.StitchBackend(session=RecordingSession(self.tools, response_mutator=tool_error)).execute(
                "create_project", {"project_title": "canary-title"}, Path(".")
            )

        def jsonrpc_error(request, response):
            if request["method"] == "tools/call":
                response.pop("result")
                response["error"] = {"code": -32000, "message": "redacted"}
            return response

        with self.assertRaisesRegex(ProxyError, "response"):
            self.module.StitchBackend(session=RecordingSession(self.tools, response_mutator=jsonrpc_error)).execute(
                "create_project", {"project_title": "canary-title"}, Path(".")
            )

    def test_unknown_create_reconciles_exactly_one_project_by_unique_title(self) -> None:
        session = RecordingSession(self.tools, create_unknown=True)
        backend = self.module.StitchBackend(session=session)
        result = backend.execute("create_project", {"project_title": "canary-title"}, Path("."))
        self.assertEqual(result, {"project_name": "projects/123456", "project_id": "123456"})
        calls = [request for request in session.requests if request["method"] == "tools/call"]
        self.assertEqual([call["params"]["name"] for call in calls[-2:]], ["create_project", "list_projects"])

    def test_unknown_create_rejects_multiple_exact_title_matches(self) -> None:
        def duplicate_projects(request, response):
            if request.get("params", {}).get("name") == "list_projects":
                response["result"]["structuredContent"]["projects"].append(
                    {"name": "projects/654321", "title": "canary-title"}
                )
            return response

        backend = self.module.StitchBackend(
            session=RecordingSession(self.tools, create_unknown=True, response_mutator=duplicate_projects)
        )
        with self.assertRaisesRegex(UnknownWriteResult, "remains unknown"):
            backend.execute("create_project", {"project_title": "canary-title"}, Path("."))

    def test_edit_rejects_a_screen_from_another_project_and_upload_requires_nonempty_screens(self) -> None:
        def wrong_edit(request, response):
            if request.get("params", {}).get("name") == "edit_screens":
                response["result"]["structuredContent"]["screens"][0]["sourceScreen"] = "projects/999/screens/" + "a" * 32
            return response

        context = {
            "project_id": "123456", "project_name": "projects/123456",
            "screen_id": "instance-1", "screen_name": "projects/123456/screens/" + "a" * 32,
        }
        with self.assertRaisesRegex(ProxyError, "project"):
            self.module.StitchBackend(session=RecordingSession(self.tools, response_mutator=wrong_edit)).execute(
                "edit", context, Path(".")
            )

        def empty_upload(request, response):
            if request.get("params", {}).get("name") == "stitch_local_upload_asset":
                response["result"]["structuredContent"]["screens"] = []
            return response

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ProxyError, "upload"):
                self.module.StitchBackend(session=RecordingSession(self.tools, response_mutator=empty_upload)).execute(
                    "upload", context, Path(directory)
                )

    def test_mutating_calls_use_exact_bound_parameters(self) -> None:
        session = RecordingSession(self.tools)
        backend = self.module.StitchBackend(session=session)
        context = {
            "project_id": "123456", "project_name": "projects/123456",
            "screen_id": "instance-1", "screen_name": "projects/123456/screens/" + "a" * 32,
            "design_system_asset_id": "asset-1", "design_system_name": "assets/asset-1",
            "design_system": self.module._canary_design_system(),
        }
        backend.execute("edit", context, Path("."))
        backend.execute("variant", context, Path("."))
        backend.execute("design_system_update", context, Path("."))
        backend.execute("design_system_apply", context, Path("."))
        calls = [request["params"] for request in session.requests if request["method"] == "tools/call"]
        selected = {"id": "instance-1", "sourceScreen": context["screen_name"]}
        self.assertEqual(calls[-4:], [
            {"name": "edit_screens", "arguments": {
                "projectId": "123456", "selectedScreenIds": ["instance-1"],
                "prompt": "Keep the layout and change the primary button label to Continue.",
            }},
            {"name": "generate_variants", "arguments": {
                "projectId": "123456", "selectedScreenIds": ["instance-1"],
                "prompt": "Create one layout variant while preserving the content hierarchy.",
                "variantOptions": {"variantCount": 1, "creativeRange": "REFINE", "aspects": ["LAYOUT"]},
            }},
            {"name": "update_design_system", "arguments": {
                "name": "assets/asset-1", "projectId": "123456",
                "designSystem": self.module._canary_design_system(),
            }},
            {"name": "apply_design_system", "arguments": {
                "projectId": "123456", "selectedScreenInstances": [selected], "assetId": "asset-1",
            }},
        ])

    def test_real_backend_unknown_delete_still_performs_list_projects_probe(self) -> None:
        session = RecordingSession(self.tools, delete_unknown=True)
        backend = self.module.StitchBackend(session=session)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            evidence = root / "evidence.json"
            private = {
                "project_name": "projects/123456", "project_id": "123456",
                "project_title": "canary-title", "delete_attempted": False,
            }
            public = self.module._public_template("2026-09-14T08:00:00Z")
            self.module._atomic_private_json(state, private)
            self.module._write_public_evidence(evidence, public)
            cleaned = self.module.cleanup_canary(backend, state, evidence)
        calls = [request for request in session.requests if request["method"] == "tools/call"]
        self.assertEqual([call["params"]["name"] for call in calls[-2:]], ["delete_project", "list_projects"])
        self.assertTrue(cleaned["cleanup"]["project_absent"])

    def test_successful_delete_accepts_provider_empty_structured_content(self) -> None:
        session = RecordingSession(self.tools)
        backend = self.module.StitchBackend(session=session)
        deleted = backend.delete_project({
            "project_name": "projects/123456",
            "project_id": "123456",
        })
        self.assertTrue(deleted)
        calls = [request for request in session.requests if request["method"] == "tools/call"]
        self.assertEqual(calls[-1]["params"], {
            "name": "delete_project",
            "arguments": {"name": "projects/123456"},
        })

    def test_cleanup_failure_still_reads_and_keeps_absence_unproved(self) -> None:
        class FailedDeleteBackend(FakeBackend):
            def delete_project(self, context: dict) -> bool:
                self.calls.append("delete_project")
                raise ProxyError("definitive failure")

            def project_absent(self, context: dict) -> bool:
                self.calls.append("project_absent")
                return False

        backend = FailedDeleteBackend()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            evidence = root / "evidence.json"
            module = self.module
            module._atomic_private_json(state, {
                "project_name": "projects/123456", "project_id": "123456",
                "project_title": "canary-title", "delete_attempted": False,
            })
            module._write_public_evidence(evidence, module._public_template("2026-09-14T08:00:00Z"))
            with self.assertRaisesRegex(ProxyError, "definitive failure"):
                module.cleanup_canary(backend, state, evidence, backoff_seconds=0)
            public = json.loads(evidence.read_text(encoding="utf-8"))
        self.assertEqual(backend.calls, ["delete_project", "project_absent", "project_absent", "project_absent"])
        self.assertFalse(public["cleanup"]["project_absent"])

    def test_recording_session_exercises_full_real_backend_smoke_contract(self) -> None:
        session = RecordingSession(self.tools)
        backend = self.module.StitchBackend(session=session)
        context = {"project_title": "canary-title"}
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            for stage in self.module.STAGES:
                context.update(backend.execute(stage, context, workspace))
        self.assertEqual(context["project_name"], "projects/123456")
        self.assertEqual(context["screen_name"], "projects/123456/screens/" + "d" * 32)
        self.assertEqual(context["design_system_asset_id"], "asset-1")
        self.assertEqual(context["upload_count"], 1)
        self.assertEqual(context["count"], 1)
        self.assertRegex(context["manifest_sha256"], r"^[0-9a-f]{64}$")
        calls = [request["params"] for request in session.requests if request["method"] == "tools/call"]
        download_call = next(call for call in calls if call["name"] == "stitch_local_download_assets")
        self.assertEqual(download_call["arguments"]["screenNames"], [
            "projects/123456/screens/" + "1" * 19,
        ])

    def test_variant_rejects_the_source_screen_identity(self) -> None:
        backend = self.module.StitchBackend(session=RecordingSession(self.tools, variant_same_source=True))
        context = {
            "project_id": "123456", "project_name": "projects/123456",
            "screen_id": "instance-1", "screen_name": "projects/123456/screens/" + "a" * 32,
        }
        with self.assertRaisesRegex(ProxyError, "different"):
            backend.execute("variant", context, Path("."))


if __name__ == "__main__":
    unittest.main()
