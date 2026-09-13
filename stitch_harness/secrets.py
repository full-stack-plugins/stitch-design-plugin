"""System-backed secret storage for the Stitch API key."""

from __future__ import annotations

import ctypes
import getpass
import hmac
import json
import os
import shutil
import subprocess
import sys
import tempfile
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence


KEY_NAME = "STITCH_API_KEY"
KEYCHAIN_SERVICE = "com.partme.stitch-design"
KEYCHAIN_ACCOUNT = getpass.getuser()


class SecretStoreError(RuntimeError):
    """A secret could not be read, written, or verified safely."""


class SecretProvider(Protocol):
    """Minimal secret provider used by setup and the MCP proxy."""

    def get(self) -> str | None:
        """Return the configured secret without logging it."""

    def set(self, value: str) -> None:
        """Persist a non-empty secret for the current user."""


@dataclass(frozen=True)
class MigrationResult:
    """Result of an explicit legacy-credential migration."""

    migrated: bool
    reason: str


class EnvironmentSecretProvider:
    """Read an explicitly supplied process environment value."""

    def __init__(self, environment: Mapping[str, str] | None = None):
        self._environment = os.environ if environment is None else environment

    def get(self) -> str | None:
        value = self._environment.get(KEY_NAME, "").strip()
        return value or None

    def set(self, value: str) -> None:
        raise SecretStoreError("process environment is read-only")


class CompositeSecretProvider:
    """Read providers in priority order and write to the first writable store."""

    def __init__(self, providers: Sequence[SecretProvider]):
        self._providers = tuple(providers)

    def get(self) -> str | None:
        for provider in self._providers:
            value = provider.get()
            if value:
                return value
        return None

    def set(self, value: str) -> None:
        for provider in self._providers:
            if isinstance(provider, EnvironmentSecretProvider):
                continue
            provider.set(value)
            return
        raise SecretStoreError("no writable system secret store is available")


def _checked_value(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise SecretStoreError("Stitch API key cannot be empty")
    return normalized


class MacOSKeychainProvider:
    """Store the key in the current user's macOS Keychain."""

    def __init__(self, service: str = KEYCHAIN_SERVICE, account: str = KEYCHAIN_ACCOUNT):
        self._service = service
        self._account = account

    def get(self) -> str | None:
        result = subprocess.run(
            [
                "/usr/bin/security",
                "find-generic-password",
                "-a",
                self._account,
                "-s",
                self._service,
                "-w",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 44:
            return None
        if result.returncode != 0:
            raise SecretStoreError("macOS Keychain could not read the Stitch credential")
        value = result.stdout.rstrip("\r\n")
        return value or None

    def set(self, value: str) -> None:
        secret = _checked_value(value)
        result = subprocess.run(
            [
                "/usr/bin/security",
                "add-generic-password",
                "-U",
                "-a",
                self._account,
                "-s",
                self._service,
                "-w",
            ],
            input=secret + "\n",
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise SecretStoreError("macOS Keychain could not save the Stitch credential")


class LinuxSecretServiceProvider:
    """Store the key through libsecret's secret-tool command."""

    def __init__(self, executable: str | None = None):
        self._executable = executable or shutil.which("secret-tool")

    def _require_executable(self) -> str:
        if not self._executable:
            raise SecretStoreError("Linux Secret Service is unavailable; install secret-tool")
        return self._executable

    def get(self) -> str | None:
        result = subprocess.run(
            [self._require_executable(), "lookup", "service", KEYCHAIN_SERVICE, "account", KEYCHAIN_ACCOUNT],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.rstrip("\r\n")
        return value or None

    def set(self, value: str) -> None:
        secret = _checked_value(value)
        result = subprocess.run(
            [
                self._require_executable(),
                "store",
                "--label=Stitch Design",
                "service",
                KEYCHAIN_SERVICE,
                "account",
                KEYCHAIN_ACCOUNT,
            ],
            input=secret,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise SecretStoreError("Linux Secret Service could not save the Stitch credential")


class WindowsCredentialProvider:
    """Store a generic credential with the native Windows Credential API."""

    _CRED_TYPE_GENERIC = 1
    _CRED_PERSIST_LOCAL_MACHINE = 2

    class _CredentialW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    def __init__(self, target: str = KEYCHAIN_SERVICE):
        self._target = target

    def _advapi(self):
        if os.name != "nt":
            raise SecretStoreError("Windows Credential Manager is unavailable on this platform")
        return ctypes.WinDLL("Advapi32.dll", use_last_error=True)

    def get(self) -> str | None:
        advapi = self._advapi()
        pointer = ctypes.POINTER(self._CredentialW)()
        if not advapi.CredReadW(self._target, self._CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            error = ctypes.get_last_error()
            if error == 1168:
                return None
            raise SecretStoreError("Windows Credential Manager could not read the Stitch credential")
        try:
            credential = pointer.contents
            blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return blob.decode("utf-16-le") or None
        finally:
            advapi.CredFree(pointer)

    def set(self, value: str) -> None:
        secret = _checked_value(value)
        advapi = self._advapi()
        blob = secret.encode("utf-16-le")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        credential = self._CredentialW()
        credential.Type = self._CRED_TYPE_GENERIC
        credential.TargetName = self._target
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = self._CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = KEYCHAIN_ACCOUNT
        if not advapi.CredWriteW(ctypes.byref(credential), 0):
            raise SecretStoreError("Windows Credential Manager could not save the Stitch credential")


def system_secret_provider() -> SecretProvider:
    """Return the native writable provider for the current platform."""

    if sys.platform == "darwin":
        return MacOSKeychainProvider()
    if os.name == "nt":
        return WindowsCredentialProvider()
    return LinuxSecretServiceProvider()


def platform_secret_provider() -> SecretProvider:
    """Return the environment-first provider chain for this process."""

    return CompositeSecretProvider([EnvironmentSecretProvider(), system_secret_provider()])


def _atomic_json(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".credentials-", text=True)
    temporary = Path(temporary_name)
    try:
        if os.name != "nt":
            os.chmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def migrate_legacy_key(source: Path, provider: SecretProvider) -> MigrationResult:
    """Explicitly migrate a legacy JSON key after write-and-read verification."""

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return MigrationResult(False, "legacy credential file does not exist")
    except (json.JSONDecodeError, OSError) as error:
        raise SecretStoreError("legacy credential file could not be read") from error
    value = payload.get(KEY_NAME)
    if not isinstance(value, str) or not value.strip():
        return MigrationResult(False, "legacy credential file contains no key")
    secret = value.strip()
    try:
        provider.set(secret)
        stored = provider.get()
    except Exception as error:
        raise SecretStoreError("system secret store could not accept the legacy credential") from error
    if stored is None or not hmac.compare_digest(stored, secret):
        raise SecretStoreError("system secret store verification failed")
    try:
        _atomic_json(source, {"migrated_to": "system-secret-store"})
    except OSError as error:
        raise SecretStoreError("legacy credential marker could not be written") from error
    return MigrationResult(True, "legacy credential migrated")
