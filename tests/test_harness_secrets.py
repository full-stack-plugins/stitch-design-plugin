import importlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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
    def test_native_migration_surface_is_absent(self):
        module = secrets_module()
        self.assertFalse(hasattr(module, "MigrationResult"))
        self.assertFalse(hasattr(module, "migrate_legacy_key"))
        self.assertFalse(hasattr(module, "system_secret_provider"))

    def test_environment_provider_has_precedence(self):
        module = secrets_module()
        provider = module.CompositeSecretProvider(
            [
                module.EnvironmentSecretProvider({"STITCH_API_KEY": "env-secret"}),
                FakeSecretProvider("stored-secret"),
            ]
        )

        self.assertEqual(provider.get(), "env-secret")

    def test_default_provider_uses_user_config_without_touching_system_store(self):
        module = secrets_module()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "credentials.json"
            with mock.patch.dict(
                os.environ,
                {"STITCH_DESIGN_CONFIG": str(target)},
                clear=True,
            ):
                provider = module.platform_secret_provider()
                provider.set("file-secret")

                self.assertEqual(provider.get(), "file-secret")
                self.assertEqual(
                    json.loads(target.read_text(encoding="utf-8")),
                    {"STITCH_API_KEY": "file-secret"},
                )

    @unittest.skipIf(os.name == "nt", "POSIX permission test")
    def test_user_config_restricts_an_existing_directory(self):
        module = secrets_module()
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "stitch-design"
            parent.mkdir(mode=0o755)
            parent.chmod(0o755)
            provider = module.UserConfigSecretProvider(parent / "credentials.json")

            provider.set("file-secret")

            self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o700)
            self.assertEqual(
                stat.S_IMODE((parent / "credentials.json").stat().st_mode),
                0o600,
            )

if __name__ == "__main__":
    unittest.main()
