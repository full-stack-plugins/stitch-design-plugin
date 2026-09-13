import importlib.util
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

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


class CredentialTests(unittest.TestCase):
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
                {"STITCH_API_KEY": "file-secret"},
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

    def test_root_is_not_cached(self):
        with urllib.request.urlopen(self.origin + "/") as response:
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])

    def test_save_requires_csrf_and_never_echoes_key(self):
        secret = "secret-must-not-appear"
        request = urllib.request.Request(
            self.origin + "/api/save",
            data=json.dumps({"apiKey": secret}).encode(),
            headers={"Content-Type": "application/json", "Origin": self.origin},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as failure:
            urllib.request.urlopen(request)
        body = failure.exception.read().decode()
        failure.exception.close()
        self.assertEqual(failure.exception.code, 403)
        self.assertNotIn(secret, body)

    def test_valid_save_uses_selected_provider_and_never_echoes_secret(self):
        secret = "secret-must-not-appear"
        request = urllib.request.Request(
            self.origin + "/api/save",
            data=json.dumps({"apiKey": secret, "csrfToken": self.state.csrf_token}).encode(),
            headers={"Content-Type": "application/json", "Origin": self.origin},
            method="POST",
        )

        with urllib.request.urlopen(request) as response:
            body = response.read().decode()

        self.assertEqual(response.status, 200)
        self.assertEqual(self.provider.get(), secret)
        self.assertFalse(self.config.exists())
        self.assertNotIn(secret, body)


class StaticUiTests(unittest.TestCase):
    def test_ui_is_one_card_with_three_steps(self):
        html = (ROOT / "assets" / "setup" / "index.html").read_text()
        self.assertEqual(html.count('class="setup-step"'), 3)
        self.assertIn('class="setup-card"', html)
        self.assertIn('type="password"', html)
        self.assertIn("<details", html)


if __name__ == "__main__":
    unittest.main()
