import json
import tempfile
import unittest
from pathlib import Path

from stitch_harness.contracts import ContractError, PageSpec


FIXTURE = Path(__file__).parent / "fixtures" / "page-spec.json"


class PageSpecTests(unittest.TestCase):
    def test_valid_page_spec_loads_exact_desktop_canvas(self):
        spec = PageSpec.load(FIXTURE)

        self.assertEqual(spec.page_id, "login")
        self.assertEqual((spec.canvas.width, spec.canvas.height, spec.canvas.scale), (1350, 768, 1))
        self.assertEqual(spec.comparison.critical_copy_recall, 1.0)

    def test_page_id_rejects_path_escape(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["page_id"] = "../login"

        with self.assertRaises(ContractError):
            PageSpec.from_dict(payload)

    def test_archive_rejects_absolute_or_parent_path(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for unsafe in ("/tmp/login", "docs/../outside"):
            payload["archive"] = unsafe
            with self.subTest(unsafe=unsafe), self.assertRaises(ContractError):
                PageSpec.from_dict(payload)

    def test_unknown_business_assertion_fails_closed(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["business_assertions"][0]["type"] = "natural-language"

        with self.assertRaises(ContractError):
            PageSpec.from_dict(payload)


if __name__ == "__main__":
    unittest.main()
