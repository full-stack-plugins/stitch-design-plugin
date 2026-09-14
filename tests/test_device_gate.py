import json
import unittest
from pathlib import Path

from stitch_harness.contracts import PageSpec
from stitch_harness.device_gate import validate_screen_device
from stitch_harness.evidence import ExternalEvidence


FIXTURES = Path(__file__).parent / "fixtures"


class ScreenDeviceGateTests(unittest.TestCase):
    """Regression coverage for the provider device-routing fallback.

    Every size in this module was observed against the live Stitch provider on
    2026-09-14: three TABLET requests came back as DESKTOP 2560x2048, and one
    MOBILE request came back as MOBILE 780x1768, which is the 2x device-pixel
    render of a 390x884 viewport.
    """

    def setUp(self):
        self.spec = PageSpec.load(FIXTURES / "page-spec.json")

    def spec_with(self, device: str, width: int, height: int) -> PageSpec:
        payload = json.loads((FIXTURES / "page-spec.json").read_text(encoding="utf-8"))
        payload["canvas"] = {"width": width, "height": height, "scale": 1, "device": device}
        return PageSpec.from_dict(payload)

    def evidence(self, screen):
        return ExternalEvidence.from_dict(
            {
                "schema_version": 1,
                "step": "stitch.generate",
                "provider": {"name": "google-stitch", "tool": "generate_screen_from_text", "model": "server"},
                "invoked_at": "2026-09-14T00:00:00Z",
                "source_artifacts": [{"path": "artifacts/screen.html", "sha256": "a" * 64}],
                "artifacts": [{"path": "artifacts/screen.html", "sha256": "a" * 64, "mime": "text/html"}],
                "result": {"screen": screen} if screen is not None else {},
            },
            "stitch.generate",
        )

    def test_tablet_request_that_came_back_as_desktop_fails(self):
        spec = self.spec_with("TABLET", 768, 1024)

        result = validate_screen_device(spec, self.evidence({"deviceType": "DESKTOP", "width": 2560, "height": 2048}))

        self.assertFalse(result.passed)
        self.assertTrue(any("TABLET" in failure and "DESKTOP" in failure for failure in result.failures))

    def test_mobile_deviceless_render_is_an_accepted_integer_scale(self):
        spec = self.spec_with("MOBILE", 390, 884)

        result = validate_screen_device(spec, self.evidence({"deviceType": "MOBILE", "width": 780, "height": 1768}))

        self.assertTrue(result.passed, result.failures)
        self.assertEqual(result.scale, 2)

    def test_desktop_deviceless_render_is_an_accepted_integer_scale(self):
        spec = self.spec_with("DESKTOP", 1280, 1024)

        result = validate_screen_device(spec, self.evidence({"deviceType": "DESKTOP", "width": 2560, "height": 2048}))

        self.assertTrue(result.passed, result.failures)
        self.assertEqual(result.scale, 2)

    def test_matching_device_with_wrong_aspect_fails(self):
        spec = self.spec_with("TABLET", 768, 1024)

        result = validate_screen_device(spec, self.evidence({"deviceType": "TABLET", "width": 1280, "height": 1024}))

        self.assertFalse(result.passed)
        self.assertTrue(any("aspect" in failure for failure in result.failures))

    def test_missing_screen_metadata_is_not_a_silent_pass(self):
        spec = self.spec_with("TABLET", 768, 1024)

        result = validate_screen_device(spec, self.evidence(None))

        self.assertFalse(result.passed)
        self.assertTrue(any("not asserted" in failure for failure in result.failures))

    def test_unknown_provider_device_is_rejected(self):
        spec = self.spec_with("TABLET", 768, 1024)

        result = validate_screen_device(spec, self.evidence({"deviceType": "tablet", "width": 768, "height": 1024}))

        self.assertFalse(result.passed)
        self.assertTrue(any("deviceType" in failure for failure in result.failures))

    def test_agnostic_request_skips_device_equality_but_still_checks_geometry(self):
        agnostic = self.spec_with("AGNOSTIC", 390, 884)

        accepted = validate_screen_device(
            agnostic, self.evidence({"deviceType": "DESKTOP", "width": 780, "height": 1768})
        )
        rejected = validate_screen_device(
            agnostic, self.evidence({"deviceType": "DESKTOP", "width": 2560, "height": 2048})
        )

        self.assertTrue(accepted.passed, accepted.failures)
        self.assertFalse(rejected.passed)

    def test_non_integer_scale_is_rejected(self):
        spec = self.spec_with("MOBILE", 390, 884)

        result = validate_screen_device(spec, self.evidence({"deviceType": "MOBILE", "width": 391, "height": 885}))

        self.assertFalse(result.passed)
        self.assertTrue(any("multiple" in failure for failure in result.failures))


if __name__ == "__main__":
    unittest.main()
