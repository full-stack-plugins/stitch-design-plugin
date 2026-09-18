import http.client
import json
import unittest
import urllib.error
import urllib.request
from unittest import mock

from stitch_harness import http_endpoint
from stitch_harness.auth import StitchCredential
from stitch_harness.http_endpoint import (
    DEFAULT_SCOPES,
    HttpEndpointConfig,
    create_http_endpoint,
    env_quota_project,
    env_scopes,
)
from stitch_harness.mcp_proxy import McpHttpSession


class StaticProvider:
    def __init__(self, value="stored-key"):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeAdc:
    def access_token(self):
        return None

    def invalidate(self):
        return None


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
            raise urllib.error.HTTPError(request.full_url, status, "error", _message("application/json", {}), __import__("io").BytesIO(body))
        return outcome


class FakeResponse:
    def __init__(self, status=200, body=b'{"jsonrpc":"2.0","id":1,"result":{}}', content_type="application/json", headers=None):
        self.status = status
        self._body = body
        self.headers = _message(content_type, headers or {})

    def read(self, size=-1):
        return self._body if size < 0 else self._body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _message(content_type, headers):
    from email.message import Message

    message = Message()
    message["Content-Type"] = content_type
    for key, value in headers.items():
        message[key] = value
    return message


def make_session_with_opener(opener):
    return McpHttpSession(provider=StaticProvider(), opener=opener, enable_adc=False)


class HttpEndpointTests(unittest.TestCase):
    def setUp(self):
        self.opener = FakeOpener([
            FakeResponse(200, b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}', "application/json", {"Mcp-Session-Id": "sess-9"}),
        ])
        self.session = make_session_with_opener(self.opener)
        config = HttpEndpointConfig(host="127.0.0.1", port=0, scopes=["s1"], quota_project="quota-p")
        self.server = create_http_endpoint(self.session, config, bound_base_url="http://127.0.0.1:21434")
        self.thread = __import__("threading").Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _get(self, path):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode()), response.headers
        finally:
            connection.close()

    def _post(self, path, payload, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(
                "POST", path,
                body=json.dumps(payload),
                headers={"Content-Type": "application/json", **(headers or {})},
            )
            response = connection.getresponse()
            body = response.read()
            return response.status, response.headers, body
        finally:
            connection.close()

    def test_well_known_variants_advertise_google(self):
        for path in (
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
        ):
            status, body, _headers = self._get(path)
            self.assertEqual(status, 200)
            self.assertEqual(body["resource"], "http://127.0.0.1:21434/mcp")
            self.assertEqual(body["authorization_servers"], ["https://accounts.google.com"])
            self.assertEqual(body["scopes_supported"], ["s1"])
            self.assertEqual(body["bearer_methods_supported"], ["header"])

    def test_unauthenticated_post_gets_401_challenge(self):
        status, headers, body = self._post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(status, 401)
        challenge = headers["WWW-Authenticate"]
        self.assertIn("Bearer", challenge)
        self.assertIn(
            'resource_metadata="http://127.0.0.1:21434/.well-known/oauth-protected-resource"',
            challenge,
        )
        self.assertIn("authorization required", body.decode())

    def test_bearer_token_is_forwarded_and_session_returned(self):
        status, headers, body = self._post(
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_projects", "arguments": {}}},
            headers={"Authorization": "Bearer host-token-1"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["Mcp-Session-Id"], "sess-9")
        self.assertIn('"ok":true', body.decode())
        upstream = self.opener.requests[0]
        self.assertEqual(upstream.headers["Authorization"], "Bearer host-token-1")
        self.assertEqual(upstream.headers["X-goog-user-project"], "quota-p")
        self.assertEqual(upstream.host, "stitch.googleapis.com")

    def test_rotated_host_token_replaces_credential(self):
        self.opener.outcomes = [
            FakeResponse(200, b'{"jsonrpc":"2.0","id":1,"result":{}}'),
            FakeResponse(200, b'{"jsonrpc":"2.0","id":2,"result":{}}'),
        ]
        self._post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "x"}, headers={"Authorization": "Bearer tok-a"})
        self._post("/mcp", {"jsonrpc": "2.0", "id": 2, "method": "x"}, headers={"Authorization": "Bearer tok-b"})
        self.assertEqual(self.opener.requests[0].headers["Authorization"], "Bearer tok-a")
        self.assertEqual(self.opener.requests[1].headers["Authorization"], "Bearer tok-b")

    def test_upstream_401_maps_to_401_challenge_without_retry(self):
        self.opener.outcomes = [
            ("http-error", 401, b'{"error":"expired"}'),
        ]
        status, headers, _body = self._post(
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_projects", "arguments": {}}},
            headers={"Authorization": "Bearer stale-token"},
        )
        self.assertEqual(status, 401)
        self.assertIn("resource_metadata", headers["WWW-Authenticate"])
        self.assertEqual(len(self.opener.requests), 1)

    def test_upstream_proxy_error_maps_to_jsonrpc_error(self):
        self.opener.outcomes = [
            ("http-error", 403, b'{"error":"denied"}'),
        ]
        status, _headers, body = self._post(
            "/mcp",
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "x", "arguments": {}}},
            headers={"Authorization": "Bearer tok"},
        )
        self.assertEqual(status, 200)
        payload = json.loads(body.decode())
        self.assertEqual(payload["error"]["code"], -32000)
        self.assertEqual(payload["id"], 7)

    def test_unknown_path_is_404(self):
        status, _headers, _body = self._get("/nope")
        self.assertEqual(status, 404)


class ConfigHelperTests(unittest.TestCase):
    def test_scopes_default_and_env_override(self):
        self.assertEqual(env_scopes({}), list(DEFAULT_SCOPES))
        self.assertEqual(env_scopes({"STITCH_OAUTH_SCOPES": "a b"}), ["a", "b"])
        self.assertEqual(env_scopes({"STITCH_OAUTH_SCOPES": "  "}), list(DEFAULT_SCOPES))

    def test_quota_project_precedence(self):
        self.assertIsNone(env_quota_project({}))
        self.assertEqual(env_quota_project({"STITCH_PROJECT_ID": "p2", "GOOGLE_CLOUD_PROJECT": "p1"}), "p1")
        self.assertEqual(env_quota_project({"STITCH_PROJECT_ID": "p2"}), "p2")


if __name__ == "__main__":
    unittest.main()
