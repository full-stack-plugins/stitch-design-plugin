import http.client
import io
import json
import urllib.error
import unittest
from email.message import Message
from pathlib import Path
from unittest import mock


from stitch_harness import mcp_proxy
from stitch_harness import tool_catalog


FIXTURE = Path(__file__).parent / "fixtures" / "stitch-tool-contract.json"


def load_tool_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["tools"]


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
    def __init__(
        self,
        status,
        body=b"",
        *,
        content_type="application/json",
        headers=None,
        read_error=None,
    ):
        self.status = status
        self._body = body
        self._read_error = read_error
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def read(self, size=-1):
        if self._read_error is not None:
            raise self._read_error
        return self._body if size < 0 else self._body[:size]

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
    def test_missing_credential_opens_local_setup_before_returning_error(self):
        handler = mock.Mock()
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider([None]),
            opener=FakeOpener([]),
            missing_credential_handler=handler,
        )

        with self.assertRaisesRegex(mcp_proxy.ProxyError, "credential is not configured"):
            session.send(INITIALIZE)

        handler.assert_called_once_with()

    def test_setup_launch_failure_does_not_mask_missing_credential_error(self):
        handler = mock.Mock(side_effect=RuntimeError("browser unavailable"))
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider([None]),
            opener=FakeOpener([]),
            missing_credential_handler=handler,
        )

        with self.assertRaisesRegex(mcp_proxy.ProxyError, "credential is not configured"):
            session.send(INITIALIZE)

        handler.assert_called_once_with()

    def test_configured_credential_does_not_open_local_setup(self):
        handler = mock.Mock()
        response = FakeResponse(
            200,
            b'{"jsonrpc":"2.0","id":1,"result":{}}',
        )
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["configured-secret"]),
            opener=FakeOpener([response]),
            missing_credential_handler=handler,
        )

        session.send(INITIALIZE)

        handler.assert_not_called()

    def test_schema_repair_injects_all_referenced_known_definitions(self):
        tools = load_tool_fixture()

        repaired = tool_catalog.repair_tool_schemas(tools)

        self.assertEqual(tool_catalog.validate_tool_catalog(repaired), ())
        definitions = {
            name
            for tool in repaired
            for schema_name in ("inputSchema", "outputSchema")
            for name in tool[schema_name].get("$defs", {})
        }
        self.assertEqual(definitions, {"File", "ScreenInstance", "SelectedScreenInstance"})
        self.assertNotIn("$defs", tools[0]["inputSchema"])

    def test_catalog_validation_rejects_an_unresolved_local_reference(self):
        tools = tool_catalog.repair_tool_schemas(load_tool_fixture())
        tools[0]["inputSchema"]["properties"]["unknown"] = {"$ref": "#/$defs/Missing"}

        errors = tool_catalog.validate_tool_catalog(tools)

        self.assertTrue(any("Missing" in error for error in errors), errors)

    def test_catalog_validation_rejects_a_missing_required_live_tool(self):
        tools = tool_catalog.repair_tool_schemas(load_tool_fixture())
        tools = [tool for tool in tools if tool["name"] != "delete_project"]

        errors = tool_catalog.validate_tool_catalog(tools)

        self.assertTrue(any("delete_project" in error for error in errors), errors)

    def test_catalog_validation_resolves_the_complete_local_pointer(self):
        tools = tool_catalog.repair_tool_schemas(load_tool_fixture())
        schema = tools[0]["inputSchema"]
        schema["$defs"]["Container"] = {"type": "object", "properties": {}}
        schema["properties"]["broken"] = {
            "$ref": "#/$defs/Container/properties/missing"
        }

        errors = tool_catalog.validate_tool_catalog(tools)

        self.assertTrue(any("/properties/missing" in error for error in errors), errors)

    def test_catalog_validation_checks_non_definitions_local_pointers(self):
        tools = tool_catalog.repair_tool_schemas(load_tool_fixture())
        tools[0]["inputSchema"]["properties"]["broken"] = {
            "$ref": "#/properties/missing"
        }

        errors = tool_catalog.validate_tool_catalog(tools)

        self.assertTrue(any("#/properties/missing" in error for error in errors), errors)

    def test_catalog_validation_rejects_a_malformed_referenced_definition(self):
        tools = tool_catalog.repair_tool_schemas(load_tool_fixture())
        schema = tools[0]["inputSchema"]
        schema["$defs"]["Malformed"] = "not-a-schema"
        schema["properties"]["broken"] = {"$ref": "#/$defs/Malformed"}

        errors = tool_catalog.validate_tool_catalog(tools)

        self.assertTrue(any("Malformed" in error for error in errors), errors)

    def test_catalog_validation_accepts_boolean_schema_reference_targets(self):
        for boolean_schema in (True, False):
            with self.subTest(boolean_schema=boolean_schema):
                tools = tool_catalog.repair_tool_schemas(load_tool_fixture())
                schema = tools[0]["inputSchema"]
                schema["$defs"]["BooleanSchema"] = boolean_schema
                schema["properties"]["allowed"] = {"$ref": "#/$defs/BooleanSchema"}

                errors = tool_catalog.validate_tool_catalog(tools)

                self.assertEqual(errors, ())

    def test_tool_catalog_rejects_malformed_entries_instead_of_dropping_them(self):
        tools = tool_catalog.repair_tool_schemas(load_tool_fixture())
        tools.append({"annotations": {"readOnlyHint": True, "openWorldHint": False}})

        with self.assertRaises(ValueError):
            tool_catalog.ToolCatalog(tools)

    def test_write_classification_uses_annotations_and_defaults_to_write(self):
        catalog = tool_catalog.ToolCatalog(tool_catalog.repair_tool_schemas(load_tool_fixture()))

        self.assertFalse(catalog.is_write_tool("list_projects"))
        self.assertTrue(catalog.is_write_tool("generate_screen_from_text"))
        self.assertTrue(catalog.is_write_tool("future_tool"))

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

        self.assertEqual(messages[0]["id"], 2)
        self.assertEqual(
            {tool["name"] for tool in messages[0]["result"]["tools"]},
            {"stitch_local_upload_asset", "stitch_local_download_assets"},
        )

    def test_tool_discovery_appends_namespaced_local_tools(self):
        body = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": load_tool_fixture()}}).encode()
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["test-secret"]),
            opener=FakeOpener([FakeResponse(200, body)]),
        )

        messages = session.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

        names = {tool["name"] for tool in messages[0]["result"]["tools"]}
        self.assertTrue({"stitch_local_upload_asset", "stitch_local_download_assets"}.issubset(names))
        self.assertEqual(session.tool_catalog.validation_errors(), ())

    def test_local_download_can_resolve_explicit_bound_screen_names(self):
        screen_name = "projects/123/screens/" + "1" * 19
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": "local-get-screen",
            "result": {"structuredContent": {
                "name": screen_name,
                "htmlCode": {"downloadUrl": "https://example.invalid/screen.html"},
            }},
        }).encode()
        opener = FakeOpener([FakeResponse(200, body)])
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["test-secret"]),
            opener=opener,
        )

        screens = session._read_project_screens("123", [screen_name])

        self.assertEqual(screens, [{
            "name": screen_name,
            "htmlCode": {"downloadUrl": "https://example.invalid/screen.html"},
        }])
        sent = json.loads(opener.requests[0].data)
        self.assertEqual(sent["params"], {"name": "get_screen", "arguments": {"name": screen_name}})

    def test_local_upload_tool_call_uses_injected_transport_without_provider_forward(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder).resolve() / "screen.html"
            source.write_text("<main>demo</main>", encoding="utf-8")
            result_body = json.dumps({"results": [{"screen": {"name": "projects/123/screens/" + "a" * 32}}]}).encode()
            transport_calls = []

            def transport(request, **kwargs):
                transport_calls.append(request)
                return FakeResponse(200, result_body)

            provider_opener = FakeOpener([])
            session = mcp_proxy.McpHttpSession(
                provider=RotatingSecretProvider(["test-secret"]),
                opener=provider_opener,
                asset_transport=transport,
            )
            messages = session.send({
                "jsonrpc": "2.0", "id": 9, "method": "tools/call",
                "params": {"name": "stitch_local_upload_asset", "arguments": {"projectId": "123", "filePath": str(source)}},
            })

            self.assertEqual(messages[0]["result"]["structuredContent"]["screens"][0]["name"], "projects/123/screens/" + "a" * 32)
            self.assertEqual(len(transport_calls), 1)
            self.assertEqual(provider_opener.requests, [])

    def test_local_unknown_upload_maps_to_unknown_write_result(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder).resolve() / "screen.html"
            source.write_text("<main>demo</main>", encoding="utf-8")
            failure = urllib.error.HTTPError("https://stitch.googleapis.com", 503, "unavailable", Message(), io.BytesIO())
            session = mcp_proxy.McpHttpSession(
                provider=RotatingSecretProvider(["test-secret"]),
                opener=FakeOpener([]),
                asset_transport=lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
            )
            request = {
                "jsonrpc": "2.0", "id": 9, "method": "tools/call",
                "params": {"name": "stitch_local_upload_asset", "arguments": {"projectId": "123", "filePath": str(source)}},
            }
            with self.assertRaises(mcp_proxy.UnknownWriteResult):
                session.send(request)

            output = io.StringIO()
            mcp_proxy.serve_stdio(io.StringIO(json.dumps(request) + "\n"), output, session)
            self.assertEqual(json.loads(output.getvalue())["error"]["code"], -32001)

    def test_local_tool_notification_emits_no_response(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder).resolve() / "screen.html"
            source.write_text("<main>demo</main>", encoding="utf-8")
            body = json.dumps({"results": [{"screen": {"name": "projects/123/screens/" + "a" * 32}}]}).encode()
            session = mcp_proxy.McpHttpSession(
                provider=RotatingSecretProvider(["test-secret"]),
                opener=FakeOpener([]),
                asset_transport=lambda *_args, **_kwargs: FakeResponse(200, body),
            )
            notification = {
                "jsonrpc": "2.0", "method": "tools/call",
                "params": {"name": "stitch_local_upload_asset", "arguments": {"projectId": "123", "filePath": str(source)}},
            }
            self.assertEqual(session.send(notification), [])

            failing = mcp_proxy.McpHttpSession(
                provider=RotatingSecretProvider(["test-secret"]),
                opener=FakeOpener([]),
                asset_transport=lambda *_args, **_kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")),
            )
            output = io.StringIO()
            mcp_proxy.serve_stdio(io.StringIO(json.dumps(notification) + "\n"), output, failing)
            self.assertEqual(output.getvalue(), "")

    def test_tools_list_repairs_missing_definitions_before_forwarding(self):
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 2, "result": {"tools": load_tool_fixture()}}
        ).encode()
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["test-secret"]),
            opener=FakeOpener([FakeResponse(200, body)]),
        )

        messages = session.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

        repaired = messages[0]["result"]["tools"]
        self.assertEqual(tool_catalog.validate_tool_catalog(repaired), ())
        self.assertFalse(session.tool_catalog.is_write_tool("get_screen"))

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

    def test_terminal_unauthorized_opens_local_setup_for_key_rotation(self):
        handler = mock.Mock()
        opener = FakeOpener(
            [
                ("http-error", 401, b'{"error":"unauthorized"}'),
                ("http-error", 401, b'{"error":"unauthorized"}'),
            ]
        )
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["expired-secret", "still-expired-secret"]),
            opener=opener,
            missing_credential_handler=handler,
        )

        with self.assertRaisesRegex(mcp_proxy.ProxyError, "authentication failed"):
            session.send(INITIALIZE)

        handler.assert_called_once_with()

    def test_forbidden_does_not_refresh_or_replay(self):
        opener = FakeOpener([("http-error", 403, b'{"error":"forbidden"}')])
        provider = RotatingSecretProvider(["test-secret", "must-not-be-read"])
        session = mcp_proxy.McpHttpSession(provider=provider, opener=opener)

        with self.assertRaisesRegex(mcp_proxy.ProxyError, "permission denied"):
            session.send(INITIALIZE)

        self.assertEqual(provider.read_count, 1)
        self.assertEqual(len(opener.requests), 1)

    def test_write_http_502_is_unknown_and_not_retried(self):
        opener = FakeOpener([("http-error", 502, b'{"error":"upstream"}')])
        catalog = tool_catalog.ToolCatalog(tool_catalog.repair_tool_schemas(load_tool_fixture()))
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["test-secret"]),
            opener=opener,
            tool_catalog=catalog,
        )
        request = {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "generate_screen_from_text", "arguments": {}},
        }

        with self.assertRaises(mcp_proxy.ProxyError) as raised:
            session.send(request)

        self.assertIsInstance(raised.exception, mcp_proxy.UnknownWriteResult)
        self.assertEqual(len(opener.requests), 1)

    def test_write_http_408_is_unknown_and_not_retried(self):
        opener = FakeOpener([("http-error", 408, b'{"error":"timeout"}')])
        catalog = tool_catalog.ToolCatalog(tool_catalog.repair_tool_schemas(load_tool_fixture()))
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["test-secret"]),
            opener=opener,
            tool_catalog=catalog,
        )
        request = {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "edit_screens", "arguments": {}},
        }

        with self.assertRaises(mcp_proxy.ProxyError) as raised:
            session.send(request)

        self.assertIsInstance(raised.exception, mcp_proxy.UnknownWriteResult)
        self.assertEqual(len(opener.requests), 1)

    def test_read_http_502_is_a_definitive_proxy_failure(self):
        opener = FakeOpener([("http-error", 502, b'{"error":"upstream"}')])
        catalog = tool_catalog.ToolCatalog(tool_catalog.repair_tool_schemas(load_tool_fixture()))
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["test-secret"]),
            opener=opener,
            tool_catalog=catalog,
        )
        request = {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "list_projects", "arguments": {}},
        }

        with self.assertRaises(mcp_proxy.ProxyError) as raised:
            session.send(request)

        self.assertNotIsInstance(raised.exception, mcp_proxy.UnknownWriteResult)

    def test_truncated_read_response_is_a_sanitized_proxy_failure(self):
        catalog = tool_catalog.ToolCatalog(tool_catalog.repair_tool_schemas(load_tool_fixture()))
        opener = FakeOpener(
            [FakeResponse(200, read_error=http.client.IncompleteRead(b'{"partial":', 20))]
        )
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["test-secret"]),
            opener=opener,
            tool_catalog=catalog,
        )
        request = {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "list_projects", "arguments": {}},
        }

        try:
            session.send(request)
        except Exception as error:  # noqa: BLE001 - the regression proves public containment
            raised = error
        else:
            self.fail("truncated response must not be accepted")

        self.assertIsInstance(raised, mcp_proxy.ProxyError)
        self.assertNotIsInstance(raised, mcp_proxy.UnknownWriteResult)
        self.assertNotIn("partial", str(raised))

    def test_truncated_write_response_has_unknown_result(self):
        catalog = tool_catalog.ToolCatalog(tool_catalog.repair_tool_schemas(load_tool_fixture()))
        opener = FakeOpener(
            [FakeResponse(200, read_error=http.client.IncompleteRead(b'{"partial":', 20))]
        )
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["test-secret"]),
            opener=opener,
            tool_catalog=catalog,
        )
        request = {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "edit_screens", "arguments": {}},
        }

        try:
            session.send(request)
        except Exception as error:  # noqa: BLE001 - the regression proves public containment
            raised = error
        else:
            self.fail("truncated response must not be accepted")

        self.assertIsInstance(raised, mcp_proxy.UnknownWriteResult)


    def test_request_timeout_defaults_to_300_seconds(self):
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["test-secret"]),
            opener=FakeOpener([]),
        )

        self.assertEqual(session.timeout, 300.0)

    def test_request_timeout_must_stay_within_bounds(self):
        for invalid in (0, 601):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    mcp_proxy.McpHttpSession(
                        provider=RotatingSecretProvider(["test-secret"]),
                        opener=FakeOpener([]),
                        timeout=invalid,
                    )

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

    def test_truncated_upstream_response_never_crashes_stdio(self):
        catalog = tool_catalog.ToolCatalog(tool_catalog.repair_tool_schemas(load_tool_fixture()))
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider(["test-secret"]),
            opener=FakeOpener(
                [FakeResponse(200, read_error=http.client.IncompleteRead(b"partial", 20))]
            ),
            tool_catalog=catalog,
        )
        input_stream = io.StringIO(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {"name": "edit_screens", "arguments": {}},
                }
            )
            + "\n"
        )
        output_stream = io.StringIO()

        try:
            code = mcp_proxy.serve_stdio(input_stream, output_stream, session=session)
        except Exception as error:  # noqa: BLE001 - the regression proves stdio containment
            self.fail(f"stdio crashed on a truncated upstream response: {type(error).__name__}")

        payload = json.loads(output_stream.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["error"]["code"], -32001)
        self.assertNotIn("partial", output_stream.getvalue())


class FakeAdc:
    """Scripted ADC double: pops scripted tokens, counts invalidations."""

    def __init__(self, tokens=(), project="quota-proj"):
        self.tokens = list(tokens)
        self.project = project
        self.invalidations = 0

    def access_token(self):
        if self.tokens:
            return self.tokens.pop(0)
        return None

    def invalidate(self):
        self.invalidations += 1

    def quota_project(self):
        return self.project


class AdcCredentialTests(unittest.TestCase):
    def test_adc_credential_sends_bearer_and_quota_headers(self):
        opener = FakeOpener([FakeResponse(200, b'{"jsonrpc":"2.0","id":1,"result":{}}')])
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider([]),
            opener=opener,
            auth_resolver=auth_resolver_with(FakeAdc(["tok-1"])),
        )

        self.assertTrue(session.send(INITIALIZE))

        headers = opener.requests[0].headers
        self.assertEqual(headers["Authorization"], "Bearer tok-1")
        self.assertEqual(headers["X-goog-user-project"], "quota-proj")
        self.assertNotIn("X-goog-api-key", headers)

    def test_adc_unavailable_falls_back_to_stored_key(self):
        opener = FakeOpener([FakeResponse(200, b'{"jsonrpc":"2.0","id":1,"result":{}}')])
        provider = RotatingSecretProvider(["stored-secret"])
        session = mcp_proxy.McpHttpSession(
            provider=provider,
            opener=opener,
            auth_resolver=auth_resolver_with(FakeAdc([]), provider=provider),
        )

        self.assertTrue(session.send(INITIALIZE))

        self.assertEqual(opener.requests[0].headers["X-goog-api-key"], "stored-secret")

    def test_unauthorized_refreshes_adc_token_once(self):
        opener = FakeOpener(
            [
                ("http-error", 401, b'{"error":"unauthorized"}'),
                FakeResponse(200, b'{"jsonrpc":"2.0","id":1,"result":{}}'),
            ]
        )
        adc = FakeAdc(["expired-token", "fresh-token"])
        session = mcp_proxy.McpHttpSession(
            provider=RotatingSecretProvider([]),
            opener=opener,
            auth_resolver=auth_resolver_with(adc),
        )

        self.assertTrue(session.send(INITIALIZE))

        self.assertEqual(adc.invalidations, 1)
        self.assertEqual(opener.requests[0].headers["Authorization"], "Bearer expired-token")
        self.assertEqual(opener.requests[1].headers["Authorization"], "Bearer fresh-token")

    def test_terminal_unauthorized_with_adc_opens_local_setup(self):
        handler = mock.Mock()
        opener = FakeOpener(
            [
                ("http-error", 401, b'{"error":"unauthorized"}'),
                ("http-error", 401, b'{"error":"unauthorized"}'),
            ]
        )
        provider = RotatingSecretProvider([None])
        session = mcp_proxy.McpHttpSession(
            provider=provider,
            opener=opener,
            auth_resolver=auth_resolver_with(FakeAdc(["expired-token", "still-expired-token"]), provider=provider),
            missing_credential_handler=handler,
        )

        with self.assertRaisesRegex(mcp_proxy.ProxyError, "authentication failed"):
            session.send(INITIALIZE)

        handler.assert_called_once_with()

    def test_missing_credentials_message_mentions_both_paths(self):
        handler = mock.Mock()
        provider = RotatingSecretProvider([None])
        session = mcp_proxy.McpHttpSession(
            provider=provider,
            opener=FakeOpener([]),
            auth_resolver=auth_resolver_with(FakeAdc([]), provider=provider),
            missing_credential_handler=handler,
        )

        with self.assertRaisesRegex(
            mcp_proxy.ProxyError,
            "gcloud auth application-default login",
        ):
            session.send(INITIALIZE)

    def test_adc_upload_uses_bearer_headers(self):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder).resolve() / "screen.html"
            source.write_text("<main>demo</main>", encoding="utf-8")
            result_body = json.dumps({"results": [{"screen": {"name": "projects/123/screens/" + "a" * 32}}]}).encode()
            transport_calls = []

            def transport(request, **kwargs):
                transport_calls.append(request)
                return FakeResponse(200, result_body)

            provider_opener = FakeOpener([])
            session = mcp_proxy.McpHttpSession(
                provider=RotatingSecretProvider(["unused-secret"]),
                opener=provider_opener,
                asset_transport=transport,
                auth_resolver=auth_resolver_with(FakeAdc(["upload-token"])),
            )
            messages = session.send({
                "jsonrpc": "2.0", "id": 9, "method": "tools/call",
                "params": {"name": "stitch_local_upload_asset", "arguments": {"projectId": "123", "filePath": str(source)}},
            })

            self.assertEqual(messages[0]["result"]["structuredContent"]["screens"][0]["name"], "projects/123/screens/" + "a" * 32)
            self.assertEqual(transport_calls[0].headers["Authorization"], "Bearer upload-token")
            self.assertEqual(provider_opener.requests, [])


def auth_resolver_with(adc, provider=None):
    from stitch_harness.auth import AuthResolver

    return AuthResolver(provider if provider is not None else RotatingSecretProvider([]), adc=adc)


if __name__ == "__main__":
    unittest.main()
