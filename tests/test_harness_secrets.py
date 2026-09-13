import importlib
import json
import getpass
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


def secrets_module():
    try:
        return importlib.import_module("stitch_harness.secrets")
    except ModuleNotFoundError as error:
        raise AssertionError("stitch_harness.secrets must implement the secret-store contract") from error


class FakeSecretProvider:
    def __init__(self, value=None, *, fail_on_set=False):
        self.value = value
        self.fail_on_set = fail_on_set

    def get(self):
        return self.value

    def set(self, value):
        if self.fail_on_set:
            raise RuntimeError("store unavailable")
        self.value = value


class SecretProviderTests(unittest.TestCase):
    def test_environment_provider_has_precedence(self):
        module = secrets_module()
        provider = module.CompositeSecretProvider(
            [
                module.EnvironmentSecretProvider({"STITCH_API_KEY": "env-secret"}),
                FakeSecretProvider("stored-secret"),
            ]
        )

        self.assertEqual(provider.get(), "env-secret")

    def test_legacy_file_is_scrubbed_only_after_verified_store(self):
        module = secrets_module()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "credentials.json"
            source.write_text('{"STITCH_API_KEY":"legacy-secret"}\n', encoding="utf-8")
            provider = FakeSecretProvider()

            result = module.migrate_legacy_key(source, provider)

            self.assertEqual(provider.get(), "legacy-secret")
            self.assertEqual(
                json.loads(source.read_text(encoding="utf-8")),
                {"migrated_to": "system-secret-store"},
            )
            self.assertTrue(result.migrated)

    def test_failed_secret_store_preserves_legacy_file(self):
        module = secrets_module()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "credentials.json"
            original = '{"STITCH_API_KEY":"legacy-secret"}\n'
            source.write_text(original, encoding="utf-8")

            with self.assertRaises(module.SecretStoreError):
                module.migrate_legacy_key(source, FakeSecretProvider(fail_on_set=True))

            self.assertEqual(source.read_text(encoding="utf-8"), original)

    @unittest.skipUnless(sys.platform == "darwin", "macOS Keychain integration test")
    def test_macos_keychain_provider_roundtrips_secret(self):
        module = secrets_module()
        service = f"com.partme.stitch-design.test.{uuid.uuid4().hex}"
        account = getpass.getuser()
        provider = module.MacOSKeychainProvider(service=service, account=account)
        try:
            provider.set("synthetic-keychain-secret")
            self.assertEqual(provider.get(), "synthetic-keychain-secret")
        finally:
            subprocess.run(
                ["/usr/bin/security", "delete-generic-password", "-a", account, "-s", service],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )


if __name__ == "__main__":
    unittest.main()
