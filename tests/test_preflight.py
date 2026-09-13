import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from stitch_harness import preflight
from stitch_harness.preflight import default_preflight, stitch_read_probe


FIXTURE = Path(__file__).parent / "fixtures" / "stitch-tool-contract.json"


def load_tool_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["tools"]


class FakeSession:
    def __init__(self, responses):
        self.responses = {method: list(values) for method, values in responses.items()}
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        method = message.get("method")
        if method == "notifications/initialized":
            return []
        return self.responses[method].pop(0)


def valid_session(*, initialize=None, pages=None, projects=None):
    tools = load_tool_fixture()
    return FakeSession(
        {
            "initialize": [
                initialize
                or [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {"tools": {"listChanged": False}},
                        },
                    }
                ]
            ],
            "tools/list": pages
            or [[{"jsonrpc": "2.0", "id": 2, "result": {"tools": tools}}]],
            "tools/call": [
                projects
                or [
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "result": {"structuredContent": {"projects": []}, "isError": False},
                    }
                ]
            ],
        }
    )


class StitchReadProbeTests(unittest.TestCase):
    def test_account_level_auth_error_fails_preflight(self):
        session = valid_session(
            projects=[
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "result": {
                        "isError": True,
                        "structuredContent": {"projects": []},
                        "content": [{"type": "text", "text": "Unauthorized"}],
                    },
                }
            ]
        )

        errors = stitch_read_probe(session)

        self.assertEqual(errors, ("Stitch read-only account probe failed",))
        self.assertEqual(session.messages[-1]["params"]["name"], "list_projects")

    def test_valid_account_level_result_passes_preflight(self):
        session = valid_session()

        self.assertEqual(stitch_read_probe(session), ())

    def test_initialize_response_requires_matching_id(self):
        session = valid_session(
            initialize=[
                {
                    "jsonrpc": "2.0",
                    "id": 99,
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                    },
                }
            ]
        )

        self.assertEqual(stitch_read_probe(session), ("Stitch MCP initialize response is invalid",))

    def test_initialize_response_rejects_boolean_id_equal_to_one(self):
        session = valid_session(
            initialize=[
                {
                    "jsonrpc": "2.0",
                    "id": True,
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                    },
                }
            ]
        )

        self.assertEqual(stitch_read_probe(session), ("Stitch MCP initialize response is invalid",))

    def test_initialize_error_fails_before_initialized_notification(self):
        session = valid_session(
            initialize=[{"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "no"}}]
        )

        self.assertEqual(stitch_read_probe(session), ("Stitch MCP initialize response is invalid",))
        self.assertEqual(len(session.messages), 1)

    def test_initialize_requires_tools_capability(self):
        session = valid_session(
            initialize=[
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {"protocolVersion": "2025-06-18", "capabilities": {}},
                }
            ]
        )

        self.assertEqual(stitch_read_probe(session), ("Stitch MCP initialize response is invalid",))

    def test_tool_catalog_follows_cursors_before_read_probe(self):
        tools = load_tool_fixture()
        session = valid_session(
            pages=[
                [{"jsonrpc": "2.0", "id": 2, "result": {"tools": tools[:8], "nextCursor": "next"}}],
                [{"jsonrpc": "2.0", "id": 3, "result": {"tools": tools[8:]}}],
            ],
            projects=[
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "result": {"structuredContent": {"projects": []}, "isError": False},
                }
            ],
        )

        self.assertEqual(stitch_read_probe(session), ())
        list_messages = [message for message in session.messages if message["method"] == "tools/list"]
        self.assertEqual(list_messages[1]["params"], {"cursor": "next"})

    def test_final_read_response_requires_matching_id(self):
        session = valid_session(
            projects=[
                {
                    "jsonrpc": "2.0",
                    "id": 99,
                    "result": {"structuredContent": {"projects": []}, "isError": False},
                }
            ]
        )

        self.assertEqual(stitch_read_probe(session), ("Stitch read-only account probe failed",))

    def test_final_read_response_requires_structured_projects_list(self):
        session = valid_session(
            projects=[
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "result": {"structuredContent": {"projects": {}}, "isError": False},
                }
            ]
        )

        self.assertEqual(stitch_read_probe(session), ("Stitch read-only account probe failed",))


class DefaultPreflightTests(unittest.TestCase):
    def test_separate_global_stitch_mcp_is_a_precise_preflight_failure(self):
        provider = mock.Mock()
        provider.get.return_value = "test-secret"
        global_result = SimpleNamespace(
            returncode=0,
            stdout=(
                "stitch\n"
                "  enabled: true\n"
                "  transport: streamable_http\n"
                "  url: https://stitch.googleapis.com/mcp\n"
                "  bearer_token_env_var: -\n"
                "  http_headers: -\n"
                "  env_http_headers: -\n"
                "  http_headers_helper: <redacted>\n"
                "  remove: codex mcp remove stitch\n"
            ),
            stderr="",
        )

        with mock.patch(
            "stitch_harness.preflight.platform_secret_provider", return_value=provider
        ), mock.patch(
            "stitch_harness.preflight.shutil.which", return_value="/usr/bin/codex"
        ), mock.patch(
            "stitch_harness.preflight.subprocess.run", return_value=global_result
        ) as run:
            errors = default_preflight(Path("."))

        self.assertEqual(
            errors,
            ("separate global Stitch MCP detected; run `codex mcp remove stitch` and retry",),
        )
        run.assert_called_once_with(
            ["/usr/bin/codex", "mcp", "get", "stitch"],
            capture_output=True,
            text=True,
            check=False,
            env=mock.ANY,
        )

    def test_plugin_owned_stdio_mcp_continues_with_plugin_and_read_checks(self):
        provider = mock.Mock()
        provider.get.return_value = "test-secret"
        plugin_root = Path(preflight.__file__).resolve().parents[1]
        owned = SimpleNamespace(
            returncode=0,
            stdout=(
                "stitch\n"
                "  enabled: true\n"
                "  transport: stdio\n"
                "  command: python3\n"
                "  args: scripts/stitch_mcp_proxy.py\n"
                f"  cwd: {plugin_root}/.\n"
                "  env: -\n"
                "  remove: codex mcp remove stitch\n"
            ),
            stderr="",
        )
        plugins = SimpleNamespace(
            returncode=0,
            stdout="stitch-design@0.5.4 enabled\n",
            stderr="",
        )

        with mock.patch(
            "stitch_harness.preflight.platform_secret_provider", return_value=provider
        ), mock.patch(
            "stitch_harness.preflight.shutil.which", return_value="/usr/bin/codex"
        ), mock.patch(
            "stitch_harness.preflight.subprocess.run", side_effect=[owned, plugins]
        ), mock.patch(
            "stitch_harness.preflight.stitch_read_probe", return_value=()
        ):
            errors = default_preflight(Path("."))

        self.assertEqual(errors, ())

    def test_mismatched_stdio_command_or_cwd_is_a_conflict(self):
        plugin_root = Path(preflight.__file__).resolve().parents[1]
        mismatches = (
            ("python-malicious", f"{plugin_root}/."),
            ("python3", f"{plugin_root.parent}/other-plugin"),
        )
        for command, cwd in mismatches:
            with self.subTest(command=command, cwd=cwd):
                provider = mock.Mock()
                provider.get.return_value = "test-secret"
                result = SimpleNamespace(
                    returncode=0,
                    stdout=(
                        "stitch\n"
                        "  enabled: true\n"
                        "  transport: stdio\n"
                        f"  command: {command}\n"
                        "  args: scripts/stitch_mcp_proxy.py\n"
                        f"  cwd: {cwd}\n"
                        "  env: -\n"
                        "  remove: codex mcp remove stitch\n"
                    ),
                    stderr="",
                )

                with mock.patch(
                    "stitch_harness.preflight.platform_secret_provider", return_value=provider
                ), mock.patch(
                    "stitch_harness.preflight.shutil.which", return_value="/usr/bin/codex"
                ), mock.patch(
                    "stitch_harness.preflight.subprocess.run", return_value=result
                ):
                    errors = default_preflight(Path("."))

                self.assertEqual(
                    errors,
                    (
                        "separate global Stitch MCP detected; "
                        "run `codex mcp remove stitch` and retry",
                    ),
                )

    def test_malformed_successful_mcp_output_fails_closed_without_echoing_it(self):
        provider = mock.Mock()
        provider.get.return_value = "test-secret"
        malformed = SimpleNamespace(
            returncode=0,
            stdout=(
                "stitch\n"
                "  enabled: true\n"
                "  transport: stdio\n"
                "  command: python3\n"
                "  credential-like-private-detail\n"
            ),
            stderr="",
        )

        with mock.patch(
            "stitch_harness.preflight.platform_secret_provider", return_value=provider
        ), mock.patch(
            "stitch_harness.preflight.shutil.which", return_value="/usr/bin/codex"
        ), mock.patch(
            "stitch_harness.preflight.subprocess.run", return_value=malformed
        ):
            errors = default_preflight(Path("."))

        self.assertEqual(errors, ("Codex global MCP configuration could not be read",))
        self.assertNotIn("private-detail", " ".join(errors))

    def test_absent_global_mcp_continues_with_plugin_and_read_checks(self):
        provider = mock.Mock()
        provider.get.return_value = "test-secret"
        absent = SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="Error: No MCP server named 'stitch' found.\n",
        )
        plugins = SimpleNamespace(
            returncode=0,
            stdout="stitch-design@0.5.4 enabled\n",
            stderr="",
        )

        with mock.patch(
            "stitch_harness.preflight.platform_secret_provider", return_value=provider
        ), mock.patch(
            "stitch_harness.preflight.shutil.which", return_value="/usr/bin/codex"
        ), mock.patch(
            "stitch_harness.preflight.subprocess.run", side_effect=[absent, plugins]
        ), mock.patch(
            "stitch_harness.preflight.stitch_read_probe", return_value=()
        ):
            errors = default_preflight(Path("."))

        self.assertEqual(errors, ())

    def test_global_mcp_cli_failure_blocks_preflight(self):
        provider = mock.Mock()
        provider.get.return_value = "test-secret"
        failed = SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="Error: failed to load MCP configuration\n",
        )

        with mock.patch(
            "stitch_harness.preflight.platform_secret_provider", return_value=provider
        ), mock.patch(
            "stitch_harness.preflight.shutil.which", return_value="/usr/bin/codex"
        ), mock.patch(
            "stitch_harness.preflight.subprocess.run", return_value=failed
        ):
            errors = default_preflight(Path("."))

        self.assertEqual(errors, ("Codex global MCP configuration could not be read",))

    def test_global_mcp_process_failure_blocks_preflight_without_crashing(self):
        provider = mock.Mock()
        provider.get.return_value = "test-secret"

        with mock.patch(
            "stitch_harness.preflight.platform_secret_provider", return_value=provider
        ), mock.patch(
            "stitch_harness.preflight.shutil.which", return_value="/usr/bin/codex"
        ), mock.patch(
            "stitch_harness.preflight.subprocess.run", side_effect=OSError("exec failed")
        ):
            try:
                errors = default_preflight(Path("."))
            except Exception as error:  # noqa: BLE001 - regression proves fail-closed behavior
                self.fail(f"global MCP check crashed: {type(error).__name__}")

        self.assertEqual(errors, ("Codex global MCP configuration could not be read",))

    def test_plugin_list_process_failure_blocks_preflight_without_crashing(self):
        provider = mock.Mock()
        provider.get.return_value = "test-secret"
        absent = SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="Error: No MCP server named 'stitch' found.\n",
        )

        with mock.patch(
            "stitch_harness.preflight.platform_secret_provider", return_value=provider
        ), mock.patch(
            "stitch_harness.preflight.shutil.which", return_value="/usr/bin/codex"
        ), mock.patch(
            "stitch_harness.preflight.subprocess.run", side_effect=[absent, OSError("exec failed")]
        ):
            try:
                errors = default_preflight(Path("."))
            except Exception as error:  # noqa: BLE001 - regression proves fail-closed behavior
                self.fail(f"plugin list check crashed: {type(error).__name__}")

        self.assertEqual(errors, ("Codex plugin list could not be read",))

    def test_codex_cli_checks_receive_no_credential_environment(self):
        provider = mock.Mock()
        provider.get.return_value = "provider-secret"
        absent = SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="Error: No MCP server named 'stitch' found.\n",
        )
        plugins = SimpleNamespace(
            returncode=0,
            stdout="stitch-design@0.5.4 enabled\n",
            stderr="",
        )
        secret_environment = {
            "STITCH_API_KEY": "stitch-secret",
            "STITCH_DESIGN_CONFIG": "/private/credential.json",
            "GOOGLE_API_KEY": "google-secret",
            "AWS_ACCESS_KEY_ID": "aws-key",
            "PRIVATE_KEY": "private-key",
            "ACCESS_TOKEN": "token-secret",
            "SERVICE_PASSWORD": "password-secret",
            "SAFE_SETTING": "preserved",
        }

        with mock.patch.dict(os.environ, secret_environment, clear=False), mock.patch(
            "stitch_harness.preflight.platform_secret_provider", return_value=provider
        ), mock.patch(
            "stitch_harness.preflight.shutil.which", return_value="/usr/bin/codex"
        ), mock.patch(
            "stitch_harness.preflight.subprocess.run", side_effect=[absent, plugins]
        ) as run, mock.patch(
            "stitch_harness.preflight.stitch_read_probe", return_value=()
        ):
            errors = default_preflight(Path("."))

        self.assertEqual(errors, ())
        for call in run.call_args_list:
            child_environment = call.kwargs.get("env")
            self.assertIsNotNone(child_environment)
            self.assertEqual(child_environment["SAFE_SETTING"], "preserved")
            for secret_name in secret_environment.keys() - {"SAFE_SETTING"}:
                self.assertNotIn(secret_name, child_environment)


if __name__ == "__main__":
    unittest.main()
