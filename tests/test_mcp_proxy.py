import io
import json
import urllib.error
import unittest
from email.message import Message


from stitch_harness import mcp_proxy


class RotatingSecretProvider:
    def __init__(self, values):
        self.values = list(values)
        self.read_count = 0

    def get(self):
        index = min(self.read_count, len(self.values) - 1)
        self.read_count += 1
        return self.values[index]

    def set(self, value):
        raise AssertionError("proxy must not write credentials")


class FakeResponse:
    def __init__(self, status, body=b"", *, content_type="application/json", headers=None):
        self.status = status
        self._body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeOpener:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, tuple) and outcome[0] == "http-error":
            _, status, body = outcome
            raise urllib.error.HTTPError(request.full_url, status, "error", Message(), io.BytesIO(body))
        return outcome


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}


class McpHttpSessionTests(unittest.TestCase):
    def test_initialize_injects_key_and_forwards_session(self):
        response = FakeResponse(
            200,
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}).encode(),
            headers={"Mcp-Session-Id": "session-1"},
        )
        opener = FakeOpener([response])
        provider = RotatingSecretProvider(["test-secret"])
        session = mcp_proxy.McpHttpSession(provider=provider, opener=opener)

        messages = session.send(INITIALIZE)

        self.assertEqual(messages[0]["id"], 1)
        self.assertEqual(opener.requests[0].headers["X-goog-api-key"], "test-secret")
        self.assertEqual(session.session_id, "session-1")

    def test_notification_with_empty_accepted_body_emits_nothing(self):
        opener = FakeOpener([FakeResponse(202)])
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["test-secret"]),
            opener=opener,
        )

        messages = session.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        self.assertEqual(messages, [])

    def test_session_reuses_secret_until_authentication_rejects_it(self):
        opener = FakeOpener([FakeResponse(202), FakeResponse(202)])
        provider = RotatingSecretProvider(["test-secret"])
        session = mcp_proxy.McpHttpSession(provider=provider, opener=opener)

        session.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        session.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        self.assertEqual(provider.read_count, 1)

    def test_cached_secret_is_excluded_from_session_repr(self):
        secret = "secret-must-not-appear"

        class ReprSecretProvider(RotatingSecretProvider):
            def __repr__(self):
                return f"Provider(secret={self.values[0]!r})"

        provider = ReprSecretProvider([secret])
        session = mcp_proxy.McpHttpSession(
            provider=provider,
            opener=FakeOpener([FakeResponse(202)]),
        )

        session.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        self.assertNotIn(secret, repr(session))

    def test_sse_messages_are_parsed(self):
        body = (
            b"event: message\n"
            b'data: {"jsonrpc":"2.0","id":2,"result":{"tools":[]}}\n\n'
        )
        opener = FakeOpener([FakeResponse(200, body, content_type="text/event-stream")])
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["test-secret"]),
            opener=opener,
        )

        messages = session.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

        self.assertEqual(messages, [{"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}])

    def test_unauthorized_refreshes_secret_once(self):
        opener = FakeOpener(
            [
                ("http-error", 401, b'{"error":"unauthorized"}'),
                FakeResponse(200, b'{"jsonrpc":"2.0","id":1,"result":{}}'),
            ]
        )
        provider = RotatingSecretProvider(["expired-secret", "fresh-secret"])
        session = mcp_proxy.McpHttpSession(provider=provider, opener=opener)

        self.assertTrue(session.send(INITIALIZE))
        self.assertEqual(provider.read_count, 2)
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(opener.requests[1].headers["X-goog-api-key"], "fresh-secret")

    def test_write_timeout_is_unknown_and_not_retried(self):
        opener = FakeOpener([urllib.error.URLError(TimeoutError("timed out"))])
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["test-secret"]),
            opener=opener,
        )
        request = {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "generate_screen_from_text", "arguments": {}},
        }

        with self.assertRaises(mcp_proxy.UnknownWriteResult):
            session.send(request)

        self.assertEqual(len(opener.requests), 1)


class StdioServerTests(unittest.TestCase):
    def test_parse_error_is_jsonrpc_error_and_does_not_echo_input(self):
        input_stream = io.StringIO("{secret-not-json}\n")
        output_stream = io.StringIO()

        code = mcp_proxy.serve_stdio(input_stream, output_stream, session=None)

        payload = json.loads(output_stream.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["error"]["code"], -32700)
        self.assertNotIn("secret-not-json", output_stream.getvalue())


if __name__ == "__main__":
    unittest.main()
