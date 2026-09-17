"""Credential resolution for the Stitch MCP endpoint.

Stitch accepts either an API key or an OAuth2 Bearer token. The resolver
prefers Google Cloud ADC (browser-authorized, auto-refreshed by gcloud) and
falls back to the stored Stitch key, mirroring the official SDK rule:
``X-Goog-Api-Key`` when a key is present, otherwise ``Authorization:
Bearer`` plus an optional ``X-Goog-User-Project`` quota header.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .gcloud_auth import GcloudAdcAuth
from .secrets import SecretProvider, SecretStoreError


AUTH_MODE_ENV = "STITCH_AUTH_MODE"
STORED_KEY_MODE = "stored_key"
ADC_MODE = "adc"
AUTO_MODE = "auto"
VALID_MODES = {STORED_KEY_MODE, ADC_MODE, AUTO_MODE}

SOURCE_ADC = "gcloud-adc"
SOURCE_STORED_KEY = "stored-key"


@dataclass(frozen=True)
class StitchCredential:
    """One resolved credential for authenticating Stitch requests."""

    stored_key: str | None = None
    access_token: str | None = None
    quota_project: str | None = None
    source: str = "unknown"

    def headers(self) -> dict[str, str]:
        """Build upstream auth headers; never returns an empty auth set."""

        if self.stored_key:
            return {"X-Goog-Api-Key": self.stored_key}
        if self.access_token:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            if self.quota_project:
                headers["X-Goog-User-Project"] = self.quota_project
            return headers
        raise SecretStoreError("credential carries no authentication material")


class AuthResolver:
    """Resolve a StitchCredential, preferring ADC and falling back to the stored key.

    ``adc`` selects the Google Cloud ADC source: ``None`` lazily builds the
    real one, ``False`` disables ADC entirely (stored-key-only, deterministic
    for tests), and a :class:`GcloudAdcAuth` instance is used as given.
    """

    def __init__(
        self,
        secret_provider: SecretProvider,
        adc: GcloudAdcAuth | bool | None = None,
        *,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._secret_provider = secret_provider
        self._adc_enabled = adc is not False
        self._adc = None if adc is False or adc is True else adc
        self._env: Mapping[str, str] = {} if env is None else env

    @property
    def adc(self) -> GcloudAdcAuth:
        if self._adc is None:
            self._adc = GcloudAdcAuth(env=self._env)
        return self._adc

    def mode(self) -> str:
        value = str(self._env.get(AUTH_MODE_ENV, AUTO_MODE)).strip().lower()
        return value if value in VALID_MODES else AUTO_MODE

    def get(self) -> StitchCredential | None:
        """Return the best available credential, or None when none exists."""

        if not self._adc_enabled:
            return self._stored_key_credential(raise_on_error=True)
        mode = self.mode()
        if mode != STORED_KEY_MODE:
            token = self.adc.access_token()
            if token:
                return StitchCredential(
                    access_token=token,
                    quota_project=self.adc.quota_project(),
                    source=SOURCE_ADC,
                )
            if mode == ADC_MODE:
                return None
        return self._stored_key_credential(raise_on_error=False)

    def refresh(self) -> StitchCredential | None:
        """Drop caches and re-resolve after an authentication rejection."""

        if self._adc_enabled and self._adc is not None:
            self._adc.invalidate()
        return self.get()

    def _stored_key_credential(self, *, raise_on_error: bool) -> StitchCredential | None:
        try:
            key = self._secret_provider.get()
        except SecretStoreError:
            if raise_on_error:
                raise
            return None
        if key:
            return StitchCredential(stored_key=key, source=SOURCE_STORED_KEY)
        return None
