import importlib
import json
import getpass
import os
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
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

    def test_default_provider_uses_user_config_without_touching_system_store(self):
        module = secrets_module()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "credentials.json"
            with mock.patch.dict(
                os.environ,
                {"STITCH_DESIGN_CONFIG": str(target)},
                clear=True,
            ), mock.patch.object(
                module,
                "system_secret_provider",
                side_effect=AssertionError("default provider must not access the system store"),
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

    @unittest.skipUnless(
        sys.platform == "darwin" and os.environ.get("STITCH_TEST_SYSTEM_SECRET_STORE") == "1",
        "macOS Keychain integration test is explicit opt-in",
    )
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
