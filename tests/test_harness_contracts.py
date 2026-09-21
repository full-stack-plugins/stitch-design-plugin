import json
import unittest
from pathlib import Path

import jsonschema

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

    def test_runtime_and_json_schema_reject_the_same_structural_edge_cases(self):
        schema = json.loads((Path(__file__).parents[1] / "stitch_harness/spec.schema.json").read_text(encoding="utf-8"))
        base = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cases = []
        root_extra = json.loads(json.dumps(base)); root_extra["unexpected"] = True; cases.append(root_extra)
        canvas_extra = json.loads(json.dumps(base)); canvas_extra["canvas"]["unexpected"] = True; cases.append(canvas_extra)
        comparison_extra = json.loads(json.dumps(base)); comparison_extra["comparison"]["unexpected"] = True; cases.append(comparison_extra)
        boolean_width = json.loads(json.dumps(base)); boolean_width["canvas"]["width"] = True; cases.append(boolean_width)
        boolean_score = json.loads(json.dumps(base)); boolean_score["comparison"]["visual_quality_score_min"] = True; cases.append(boolean_score)
        blank_theme = json.loads(json.dumps(base)); blank_theme["theme"] = "   "; cases.append(blank_theme)
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertFalse(jsonschema.Draft202012Validator(schema).is_valid(payload))
                with self.assertRaises(ContractError):
                    PageSpec.from_dict(payload)

    def test_max_rounds_defaults_to_three_when_omitted(self):
        spec = PageSpec.from_dict(json.loads(FIXTURE.read_text(encoding="utf-8")))
        self.assertEqual(spec.comparison.max_rounds, 3)

    def test_max_rounds_is_loaded_when_declared(self):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["comparison"]["max_rounds"] = 5
        self.assertEqual(PageSpec.from_dict(payload).comparison.max_rounds, 5)

    def test_max_rounds_must_be_a_positive_integer(self):
        schema = json.loads((Path(__file__).parents[1] / "stitch_harness/spec.schema.json").read_text(encoding="utf-8"))
        base = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for bad in (0, -1, 1.5, True, "3"):
            payload = json.loads(json.dumps(base))
            payload["comparison"]["max_rounds"] = bad
            with self.subTest(value=bad):
                self.assertFalse(jsonschema.Draft202012Validator(schema).is_valid(payload))
                with self.assertRaises(ContractError):
                    PageSpec.from_dict(payload)


if __name__ == "__main__":
    unittest.main()
