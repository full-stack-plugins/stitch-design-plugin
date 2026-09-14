"""Device-fidelity gate for Stitch-generated screens.

The Stitch provider accepts a requested device but does not reliably honour it:
on 2026-09-14 three TABLET requests (`generate_screen_from_text`, `edit_screens`,
and `generate_variants`) all came back as DESKTOP 2560x2048, and one MOBILE
request also fell back to DESKTOP. Provider size is also device-pixel scaled, so
a 390x884 viewport is reported as 780x1768.

This gate makes that fallback fail closed. Without it a desktop fallback can be
recorded as a tablet deliverable, which is the exact fabrication the Harness
exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import CANVAS_DEVICES, PageSpec
from .evidence import ExternalEvidence


PROVIDER_DEVICES = CANVAS_DEVICES
ASPECT_TOLERANCE = 0.01


@dataclass(frozen=True)
class ScreenDeviceResult:
    failures: tuple[str, ...] = ()
    scale: int | None = None

    @property
    def passed(self) -> bool:
        return not self.failures


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def validate_screen_device(spec: PageSpec, evidence: ExternalEvidence) -> ScreenDeviceResult:
    """Verify the provider generated for the requested device and canvas geometry."""

    screen = evidence.result.get("screen")
    if not isinstance(screen, Mapping):
        return ScreenDeviceResult(("Stitch screen device evidence is not asserted",))

    failures: list[str] = []
    requested = spec.canvas.device
    provider_device = screen.get("deviceType")
    if provider_device not in PROVIDER_DEVICES:
        failures.append(
            f"screen deviceType must be one of {', '.join(PROVIDER_DEVICES)}; got {provider_device!r}"
        )
    elif requested != "AGNOSTIC" and provider_device != requested:
        failures.append(
            f"Stitch generated {provider_device} but the page spec requests {requested}; "
            "the provider device routing fell back and this screen is not a deliverable for that device"
        )

    width = _positive_int(screen.get("width"))
    height = _positive_int(screen.get("height"))
    if width is None or height is None:
        failures.append("screen width and height must be positive integers")
        return ScreenDeviceResult(tuple(failures))

    if abs((width / height) - (spec.canvas.width / spec.canvas.height)) > ASPECT_TOLERANCE:
        failures.append(
            f"screen aspect {width}x{height} does not match the canvas aspect "
            f"{spec.canvas.width}x{spec.canvas.height}"
        )

    if width % spec.canvas.width or height % spec.canvas.height:
        failures.append(
            f"screen size {width}x{height} is not an integer multiple of the canvas "
            f"{spec.canvas.width}x{spec.canvas.height}"
        )
    else:
        width_scale = width // spec.canvas.width
        height_scale = height // spec.canvas.height
        if width_scale != height_scale:
            failures.append(
                f"screen size {width}x{height} scales the canvas by {width_scale}x horizontally "
                f"and {height_scale}x vertically"
            )
        elif not failures:
            return ScreenDeviceResult((), width_scale)

    return ScreenDeviceResult(tuple(failures))
