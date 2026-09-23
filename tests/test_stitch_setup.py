import importlib.util
import http.client
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import contextlib
import io
from pathlib import Path
from unittest.mock import patch

from stitch_harness.secrets import KEY_NAME

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("stitch_setup", ROOT / "scripts" / "stitch_setup.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class FakeSecretProvider:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeAdc:
    """Deterministic ADC double so tests never probe the host's real gcloud."""

    def __init__(self, ready=False, project="quota-proj", found=True):
        self.ready = ready
        self.project = project
        self.found = found

    def find_executable(self):
        return "/usr/bin/gcloud" if self.found else None

    def has_credentials(self):
        return self.ready

    def login(self):
        return 0 if self.ready else 3

    def quota_project(self):
        return self.project if self.ready else None


class CredentialTests(unittest.TestCase):
    def test_check_detects_config_only_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "credentials.json"
            target.write_text(json.dumps({KEY_NAME: "config-only-" + "secret"}), encoding="utf-8")
            with patch.dict(os.environ, {"STITCH_DESIGN_CONFIG": str(target)}, clear=True), \
                 patch.object(setup, "PLUGIN_ROOT", ROOT), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                result = setup.check(adc=FakeAdc(ready=False))

        self.assertEqual(result, 0)
        self.assertIn("available through the configured secret provider", output.getvalue())
        self.assertNotIn("config-only-" + "secret", output.getvalue())

    def test_check_prefers_ready_adc_without_api_key(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"STITCH_DESIGN_CONFIG": directory}, clear=True), \
                 patch.object(setup, "PLUGIN_ROOT", ROOT), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                result = setup.check(adc=FakeAdc(ready=True))

        self.assertEqual(result, 0)
        self.assertIn("Google Cloud ADC credential is available", output.getvalue())
        self.assertNotIn("STITCH_API_KEY is available", output.getvalue())

    def test_check_adc_ready_without_mcp_config_reports_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True), \
                 patch.object(setup, "PLUGIN_ROOT", Path(directory)), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                result = setup.check(adc=FakeAdc(ready=True))

        self.assertEqual(result, 1)
        self.assertIn("Stitch MCP configuration is missing", output.getvalue())

    def test_check_falls_through_to_api_key_when_adc_not_ready(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(setup, "PLUGIN_ROOT", ROOT), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = setup.check(FakeSecretProvider("k"), adc=FakeAdc(ready=False))

        self.assertEqual(result, 0)
        self.assertIn("available through the configured secret provider", output.getvalue())

    def test_gcloud_command_reports_success_and_quota_project(self):
        adc = FakeAdc(ready=True)
        with patch.object(setup, "GcloudAdcAuth", return_value=adc), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = setup.main(["gcloud"])

        self.assertEqual(result, 0)
        self.assertIn("ADC authorization succeeded", output.getvalue())
        self.assertIn("quota-proj", output.getvalue())

    def test_gcloud_command_failure_suggests_api_key_fallback(self):
        class FailingAdc(FakeAdc):
            def login(self):
                return 3

        with patch.object(setup, "GcloudAdcAuth", return_value=FailingAdc()), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            result = setup.main(["gcloud"])

        self.assertEqual(3, result)
        self.assertIn("API key", errors.getvalue())

    def test_gcloud_command_surfaces_sanitized_gcloud_errors(self):
        class BrokenAdc(FakeAdc):
            def login(self):
                raise setup.GcloudAuthError("could not run gcloud")

        with patch.object(setup, "GcloudAdcAuth", return_value=BrokenAdc()), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            result = setup.main(["gcloud"])

        self.assertEqual(1, result)
        self.assertIn("could not run gcloud", errors.getvalue())

    def test_migrate_is_not_a_user_facing_command(self):
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            result = setup.main(["migrate"])

        self.assertEqual(result, 2)
        self.assertNotIn("migrate", errors.getvalue())

    def test_blank_key_is_rejected_without_changing_provider(self):
        provider = FakeSecretProvider("existing")

        with self.assertRaises(ValueError):
            setup.save_key("   ", provider)

        self.assertEqual(provider.get(), "existing")

    def test_saved_key_uses_explicit_provider(self):
        provider = FakeSecretProvider()
        with tempfile.TemporaryDirectory() as directory:
            legacy = Path(directory) / "credentials.json"
            os.environ["STITCH_DESIGN_CONFIG"] = str(legacy)
            try:
                setup.save_key("secret", provider)
            finally:
                os.environ.pop("STITCH_DESIGN_CONFIG", None)

        self.assertEqual(provider.get(), "secret")
        self.assertFalse(legacy.exists())

    def test_saved_key_defaults_to_user_config(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "credentials.json"
            os.environ["STITCH_DESIGN_CONFIG"] = str(target)
            try:
                setup.save_key("file-secret")
                self.assertEqual(setup.load_key(), "file-secret")
            finally:
                os.environ.pop("STITCH_DESIGN_CONFIG", None)

            self.assertEqual(
                json.loads(target.read_text(encoding="utf-8")),
                {KEY_NAME: "file-" + "secret"},
            )


class SetupServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Path(self.temp.name) / "credentials.json"
        os.environ["STITCH_DESIGN_CONFIG"] = str(self.config)
        self.provider = FakeSecretProvider()
        self.server, self.state = setup.create_setup_server(secret_provider=self.provider)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        os.environ.pop("STITCH_DESIGN_CONFIG", None)
        self.temp.cleanup()

    def _request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.headers, response.read()
        finally:
            connection.close()

    def _post_json(self, path):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(
                "POST", path,
                body=json.dumps({"csrfToken": self.state.csrf_token}),
                headers={"Content-Type": "application/json", "Origin": self.origin},
            )
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode())
        finally:
            connection.close()

    def test_glaunch_endpoint_launches_detached_gcloud_command(self):
        launched = []
        with patch.object(setup, "_launch_detached", side_effect=lambda command: launched.append(command)), \
             patch.object(setup, "GcloudAdcAuth", return_value=FakeAdc(ready=False, found=True)):
            status, body = self._post_json("/api/glaunch")

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(len(launched), 1)
        self.assertEqual(launched[0][-3], "gcloud")
        self.assertEqual(launched[0][-2], "--log")
        self.assertIn("stitch_setup.py", launched[0][-4])

    def test_glaunch_endpoint_reports_missing_gcloud_without_launching(self):
        launched = []
        with patch.object(setup, "_launch_detached", side_effect=lambda command: launched.append(command)), \
             patch.object(setup, "GcloudAdcAuth", return_value=FakeAdc(ready=False, found=False)):
            status, body = self._post_json("/api/glaunch")

        self.assertEqual(status, 200)
        self.assertFalse(body["ok"])
        self.assertEqual(body["reason"], "gcloud-missing")
        self.assertEqual(launched, [])

    def test_gverify_endpoint_reports_ready_adc(self):
        with patch.object(setup, "GcloudAdcAuth", return_value=FakeAdc(ready=True)):
            status, body = self._post_json("/api/gverify")

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(body["gcloudFound"])
        self.assertTrue(body["quotaProjectSet"])

    def test_gverify_endpoint_reports_missing_adc_without_error(self):
        with patch.object(setup, "GcloudAdcAuth", return_value=FakeAdc(ready=False)):
            status, body = self._post_json("/api/gverify")

        self.assertEqual(status, 200)
        self.assertFalse(body["ok"])
        self.assertFalse(body["quotaProjectSet"])

    def test_gverify_endpoint_reports_missing_gcloud(self):
        with patch.object(setup, "GcloudAdcAuth", return_value=FakeAdc(ready=False, found=False)):
            status, body = self._post_json("/api/gverify")

        self.assertEqual(status, 200)
        self.assertFalse(body["ok"])
        self.assertFalse(body["gcloudFound"])

    def test_root_is_not_cached(self):
        status, headers, _body = self._request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])

    def test_setup_serves_the_bundled_stitch_logo(self):
        status, headers, body = self._request("GET", "/logo.png")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), "image/png")
        self.assertTrue(body.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_save_requires_csrf_and_never_echoes_key(self):
        secret = "secret-must-" + "not-appear"
        status, _headers, body = self._request(
            "POST", "/api/save",
            body=json.dumps({"apiKey": secret}),
            headers={"Content-Type": "application/json", "Origin": self.origin},
        )
        self.assertEqual(status, 403)
        self.assertNotIn(secret, body.decode())

    def test_valid_save_uses_selected_provider_and_never_echoes_secret(self):
        secret = "secret-must-" + "not-appear"
        status, _headers, body = self._request(
            "POST", "/api/save",
            body=json.dumps({"apiKey": secret, "csrfToken": self.state.csrf_token}),
            headers={"Content-Type": "application/json", "Origin": self.origin},
        )

        self.assertEqual(status, 200)
        self.assertEqual(self.provider.get(), secret)
        self.assertFalse(self.config.exists())
        self.assertNotIn(secret, body.decode())


class StaticUiTests(unittest.TestCase):
    def test_ui_is_one_card_with_one_token_input(self):
        html = (ROOT / "assets" / "setup" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count('class="setup-card"'), 1)
        self.assertNotRegex(html, r'class="[^"]*\bsetup-step\b')
        self.assertIn('class="brand-mark"', html)
        self.assertIn('src="/logo.png"', html)
        self.assertEqual(html.count('type="password"'), 1)
        self.assertIn('Google Stitch <span aria-hidden="true"></span> <em>MCP</em>', html)
        self.assertIn('href="/title.css"', html)
        self.assertIn("h1{font-weight:400}", (ROOT / "assets" / "setup" / "title.css").read_text(encoding="utf-8"))
        self.assertNotIn("<details", html)
        self.assertIn('class="advanced-settings"', html)
        self.assertNotIn('id="launch"', html)


if __name__ == "__main__":
    unittest.main()
