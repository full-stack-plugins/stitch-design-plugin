"""Environment and restricted-user-config storage for the Stitch API key."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Mapping, Protocol, Sequence


KEY_NAME = "STITCH_API_KEY"


class SecretStoreError(RuntimeError):
    """A secret could not be read, written, or verified safely."""


class SecretProvider(Protocol):
    """Minimal secret provider used by setup and the MCP proxy."""

    def get(self) -> str | None:
        """Return the configured secret without logging it."""

    def set(self, value: str) -> None:
        """Persist a non-empty secret for the current user."""


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
        raise SecretStoreError("no writable credential store is available")


def _checked_value(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise SecretStoreError("Stitch API key cannot be empty")
    return normalized


def _atomic_json(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        if path.parent.is_symlink():
            raise OSError("credential directory must not be a symbolic link")
        directory_stat = path.parent.stat()
        if directory_stat.st_uid != os.getuid():
            raise OSError("credential directory must be owned by the current user")
        path.parent.chmod(0o700)
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


def default_config_path(
    *,
    environment: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home_factory=Path.home,
) -> Path:
    """Return the cross-platform user configuration path."""

    active_environment = os.environ if environment is None else environment
    active_platform = os.name if platform_name is None else platform_name
    override = active_environment.get("STITCH_DESIGN_CONFIG")
    if override:
        return Path(override).expanduser()
    if active_platform == "nt":
        appdata = active_environment.get("APPDATA")
        base = Path(appdata) if appdata else home_factory() / "AppData" / "Roaming"
    else:
        xdg_config_home = active_environment.get("XDG_CONFIG_HOME")
        base = Path(xdg_config_home) if xdg_config_home else home_factory() / ".config"
    return base / "stitch-design" / "credentials.json"


class UserConfigSecretProvider:
    """Store the key in a restricted current-user configuration file."""

    def __init__(self, path: Path | None = None):
        self._path = path

    def _resolved_path(self) -> Path:
        return self._path if self._path is not None else default_config_path()

    def get(self) -> str | None:
        path = self._resolved_path()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, OSError) as error:
            raise SecretStoreError("Stitch credential file could not be read") from error
        value = payload.get(KEY_NAME)
        return value.strip() if isinstance(value, str) and value.strip() else None

    def set(self, value: str) -> None:
        try:
            _atomic_json(self._resolved_path(), {KEY_NAME: _checked_value(value)})
        except OSError as error:
            raise SecretStoreError("Stitch credential file could not be saved") from error


def platform_secret_provider() -> SecretProvider:
    """Return the non-interactive environment-first default provider chain."""

    return CompositeSecretProvider([EnvironmentSecretProvider(), UserConfigSecretProvider()])
