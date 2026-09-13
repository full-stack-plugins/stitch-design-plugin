import importlib
import json
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
