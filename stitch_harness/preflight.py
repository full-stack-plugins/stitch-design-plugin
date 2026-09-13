"""Read-only readiness checks for a Harness run."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .secrets import SecretStoreError, platform_secret_provider


def default_preflight(_project_root: Path) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        if not platform_secret_provider().get():
            errors.append("Stitch credential is not configured")
    except SecretStoreError as error:
        errors.append(str(error))
    codex = shutil.which("codex")
    if codex is None:
        errors.append("Codex CLI is unavailable for plugin uniqueness check")
        return tuple(errors)
    result = subprocess.run([codex, "plugin", "list"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        errors.append("Codex plugin list could not be read")
        return tuple(errors)
    enabled = [line for line in result.stdout.splitlines() if "stitch-design@" in line and "enabled" in line]
    if len(enabled) != 1:
        errors.append(f"expected one enabled Stitch Design plugin, found {len(enabled)}")
    return tuple(errors)

