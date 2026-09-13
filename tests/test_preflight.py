import unittest

from stitch_harness.preflight import stitch_read_probe


class FakeSession:
    def __init__(self, tool_result):
        self.tool_result = tool_result
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        if message.get("method") == "tools/call":
            return [self.tool_result]
        return [{"jsonrpc": "2.0", "id": message.get("id"), "result": {}}] if "id" in message else []


class StitchReadProbeTests(unittest.TestCase):
    def test_account_level_auth_error_fails_preflight(self):
        session = FakeSession(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"isError": True, "content": [{"type": "text", "text": "Unauthorized"}]},
            }
        )

        errors = stitch_read_probe(session)

        self.assertEqual(errors, ("Stitch read-only account probe failed",))
        self.assertEqual(session.messages[-1]["params"]["name"], "list_projects")

    def test_valid_account_level_result_passes_preflight(self):
        session = FakeSession(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"isError": False, "content": [{"type": "text", "text": "[]"}]},
            }
        )

        self.assertEqual(stitch_read_probe(session), ())


if __name__ == "__main__":
    unittest.main()
