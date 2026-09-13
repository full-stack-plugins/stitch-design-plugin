import tempfile
import unittest
from pathlib import Path

from stitch_harness.business_gate import validate_business_assertions
from stitch_harness.contracts import PageSpec
from stitch_harness.html_gate import parse_html, validate_html


FIXTURES = Path(__file__).parent / "fixtures"


class HtmlGateTests(unittest.TestCase):
    def setUp(self):
        self.spec = PageSpec.load(FIXTURES / "page-spec.json")

    def test_valid_login_source_passes(self):
        result = validate_html(
            self.spec,
            FIXTURES / "login-valid.html",
            {"width": 1350, "height": 768, "scale": 1},
        )

        self.assertTrue(result.passed, result.failures)

    def test_web_wrapper_dimensions_do_not_count_as_canvas(self):
        result = validate_html(
            self.spec,
            FIXTURES / "login-valid.html",
            {"width": 2560, "height": 2048, "contentWidth": 1350, "contentHeight": 768, "scale": 1},
        )

        self.assertFalse(result.passed)
        self.assertIn("canvas dimensions", " ".join(result.failures))

    def test_flattened_full_page_image_fails_editability(self):
        result = validate_html(
            self.spec,
            FIXTURES / "login-flattened.html",
            {"width": 1350, "height": 768, "scale": 1},
        )

        self.assertFalse(result.passed)
        self.assertIn("flattened", " ".join(result.failures))

    def test_missing_fixed_copy_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            html = Path(directory) / "page.html"
            html.write_text((FIXTURES / "login-valid.html").read_text().replace("统一接待多个客户渠道", "其他文案"))
            result = validate_html(self.spec, html, {"width": 1350, "height": 768, "scale": 1})

        self.assertFalse(result.passed)
        self.assertIn("统一接待多个客户渠道", " ".join(result.failures))

    def test_three_promo_cards_fail_unboxed_assertion(self):
        document = parse_html(FIXTURES / "login-promo-cards.html")

        result = validate_business_assertions(self.spec, document)

        self.assertFalse(result.passed)
        self.assertIn("promo-unboxed", result.failed_ids)


if __name__ == "__main__":
    unittest.main()
