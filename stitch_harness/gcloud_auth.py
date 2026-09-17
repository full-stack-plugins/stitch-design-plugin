"""Google Cloud application-default credentials (ADC) support for Stitch auth.

The Stitch MCP endpoint accepts either an API key or an OAuth2 Bearer token.
ADC is the OAuth path: ``gcloud auth application-default login`` performs a
browser consent once, and ``print-access-token`` mints short-lived tokens that
gcloud refreshes automatically from the stored refresh token. No long-lived
secret is stored by this plugin.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Mapping


DEFAULT_TOKEN_TTL_SECONDS = 600.0
DEFAULT_TIMEOUT_SECONDS = 15.0
LOGIN_PROBE_TIMEOUT_SECONDS = 5.0

COMMON_GCLOUD_PATHS = {
    "darwin": (
        "/opt/homebrew/bin/gcloud",
        "/usr/local/bin/gcloud",
        "/Users/Shared/google-cloud-sdk/bin/gcloud",
    ),
    "linux": ("/usr/bin/gcloud", "/usr/local/bin/gcloud", "/snap/bin/gcloud"),
}

TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


class GcloudAuthError(RuntimeError):
    """A sanitized gcloud failure safe to surface to users."""


def _env_flag(name: str, env: Mapping[str, str]) -> bool:
    return str(env.get(name, "")).strip().lower() in TRUTHY_ENV_VALUES


def _clean(value: str) -> str | None:
    value = value.strip()
    return value or None


class GcloudAdcAuth:
    """Locate gcloud, mint ADC access tokens, and run the consent flow."""

    def __init__(
        self,
        *,
        executable: str | None = None,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        project_lookup: Callable[[], str | None] | None = None,
        env: Mapping[str, str] | None = None,
        token_ttl: float = DEFAULT_TOKEN_TTL_SECONDS,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        platform: str | None = None,
    ) -> None:
        self._runner = runner
        self._explicit_executable = executable
        self._project_lookup = project_lookup
        self._env = dict(env) if env is not None else dict(os.environ)
        self._token_ttl = token_ttl
        self._timeout = timeout
        self._clock = clock
        self._platform = platform or sys.platform
        self._executable: str | None | None = None if executable is None else executable
        self._cached_token: str | None = None
        self._cached_at: float | None = None
        self._probe_failed = False

    def disabled(self) -> bool:
        return _env_flag("STITCH_DISABLE_ADC", self._env)

    def find_executable(self) -> str | None:
        """Return a gcloud executable path, or None when none is installed."""

        if self._executable is not None:
            return self._executable
        located = shutil.which("gcloud")
        if located:
            self._executable = located
            return located
        for candidate in COMMON_GCLOUD_PATHS.get(self._platform, ()):
            if Path(candidate).is_file():
                self._executable = candidate
                return candidate
        if self._platform.startswith("win"):
            located = shutil.which("gcloud.cmd")
            if located:
                self._executable = located
                return located
        return None

    def access_token(self) -> str | None:
        """Return a current ADC access token, or None when unavailable."""

        if self.disabled():
            return None
        now = self._clock()
        if (
            self._cached_token is not None
            and self._cached_at is not None
            and now - self._cached_at < self._token_ttl
        ):
            return self._cached_token
        if self._probe_failed and self._cached_token is None:
            return None
        token = self._request_token()
        if token:
            self._cached_token = token
            self._cached_at = now
        else:
            self._probe_failed = True
        return token

    def has_credentials(self) -> bool:
        """ADC counts only when a token can actually be minted from it."""

        return self.access_token() is not None

    def quota_project(self) -> str | None:
        """Google Cloud project used for the X-Goog-User-Project quota header."""

        for name in ("GOOGLE_CLOUD_PROJECT", "STITCH_PROJECT_ID"):
            value = _clean(self._env.get(name, ""))
            if value:
                return value
        if self._project_lookup is not None:
            return _clean(self._project_lookup() or "")
        executable = self.find_executable()
        if executable is None:
            return None
        try:
            completed = self._runner(
                [executable, "config", "get-value", "project"],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if completed.returncode != 0:
            return None
        return _clean(completed.stdout or "")

    def login(self) -> int:
        """Run the browser consent flow and verify a token can be minted.

        Prints the consent URL before launching the browser so headless or
        sandboxed sessions can still complete authorization by hand.
        """

        if self.disabled():
            print("Google Cloud ADC authorization is disabled by STITCH_DISABLE_ADC.", file=sys.stderr)
            return 1
        executable = self.find_executable()
        if executable is None:
            print(
                "gcloud was not found. Install the Google Cloud SDK "
                "(https://cloud.google.com/sdk/docs/install) or fall back to "
                "the Stitch API key method.",
                file=sys.stderr,
            )
            return 1
        try:
            probe = self._runner(
                [executable, "auth", "application-default", "login", "--no-launch-browser"],
                capture_output=True,
                text=True,
                timeout=LOGIN_PROBE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            probe = None
        except OSError as error:
            raise GcloudAuthError(f"could not run gcloud: {error}") from error
        if probe is not None:
            output = (probe.stderr or "") + (probe.stdout or "")
            url_start = output.find("https://accounts.google.com")
            if url_start >= 0:
                url_end = output.find("\n", url_start)
                url = output[url_start:url_end if url_end > 0 else len(output)].strip()
                print(f"If the browser does not open, visit: {url}")
        try:
            code = self._runner(
                [executable, "auth", "application-default", "login", "--quiet"],
            ).returncode
        except OSError as error:
            raise GcloudAuthError(f"could not run gcloud: {error}") from error
        if code != 0:
            return code
        self.invalidate()
        if not self.has_credentials():
            print(
                "Authorization completed but no access token could be minted; "
                "retry or use the Stitch API key method.",
                file=sys.stderr,
            )
            return 1
        return 0

    def invalidate(self) -> None:
        """Drop the cached token so the next call re-mints it."""

        self._cached_token = None
        self._cached_at = None
        self._probe_failed = False

    def _request_token(self) -> str | None:
        executable = self.find_executable()
        if executable is None:
            return None
        try:
            completed = self._runner(
                [executable, "auth", "application-default", "print-access-token"],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if completed.returncode != 0:
            return None
        return _clean(completed.stdout or "")
