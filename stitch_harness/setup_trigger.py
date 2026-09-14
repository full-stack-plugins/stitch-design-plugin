"""Open the local credential UI once when Stitch authentication is missing."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from .secrets import default_config_path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
TRIGGER_COOLDOWN_SECONDS = 600.0


def _launch_detached(command: list[str]) -> None:
    subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )


def launch_setup_ui_once(
    *,
    plugin_root: Path = PLUGIN_ROOT,
    marker_path: Path | None = None,
    now: Callable[[], float] = time.time,
    launcher: Callable[[list[str]], None] = _launch_detached,
) -> bool:
    """Launch one setup window per cooldown period without exposing credentials."""

    script = Path(plugin_root).resolve() / "scripts" / "stitch_setup.py"
    if not script.is_file():
        return False
    marker = marker_path or default_config_path().parent / "setup-ui-trigger.json"
    marker.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        marker.parent.chmod(0o700)
    timestamp = float(now())
    for _attempt in range(2):
        try:
            descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            try:
                payload = json.loads(marker.read_text(encoding="utf-8"))
                launched_at = float(payload.get("launched_at"))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                launched_at = 0.0
            if timestamp - launched_at < TRIGGER_COOLDOWN_SECONDS:
                return False
            try:
                marker.unlink()
            except FileNotFoundError:
                continue
            except OSError:
                return False
            continue
        except OSError:
            return False
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump({"launched_at": timestamp}, stream, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            launcher([sys.executable, str(script), "ui"])
        except OSError:
            marker.unlink(missing_ok=True)
            return False
        return True
    return False
