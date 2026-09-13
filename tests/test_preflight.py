import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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
        global_result = SimpleNamespace(returncode=0, stdout="stitch\n enabled: true\n", stderr="")

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
        )


if __name__ == "__main__":
    unittest.main()
