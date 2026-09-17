import unittest
from pathlib import Path

from stitch_harness.contracts import PageSpec
from stitch_harness.evidence import ExternalEvidence
from stitch_harness.ocr_gate import validate_ocr


FIXTURES = Path(__file__).parent / "fixtures"


class OcrGateTests(unittest.TestCase):
    def setUp(self):
        self.spec = PageSpec.load(FIXTURES / "page-spec.json")

    def evidence(self, texts, **metadata):
        return ExternalEvidence.from_dict(
            {
                "schema_version": 1,
                "step": "ocr",
                "provider": {"name": "test-ocr", "tool": "recognize", "model": "1"},
                "invoked_at": "2026-09-14T00:00:00Z",
                "source_artifacts": [{"path": "artifacts/art.png", "sha256": "a" * 64}],
                "artifacts": [{"path": "artifacts/ocr.json", "sha256": "b" * 64, "mime": "application/json"}],
                "result": {"texts": texts, **metadata},
            },
            "ocr",
        )

    def test_critical_copy_requires_full_recall(self):
        result = validate_ocr(self.spec, self.evidence(["WeKefu Desktop"]))

        self.assertFalse(result.passed)
        self.assertIn("统一接待多个客户渠道", result.missing_copy)

    def test_unicode_and_whitespace_are_normalized_without_changing_words(self):
        result = validate_ocr(
            self.spec,
            self.evidence(["ＷｅＫｅｆｕ Desktop", "统一接待多个客户渠道"]),
        )

        self.assertTrue(result.passed, result.failures)

    def test_reported_text_drift_fails_even_when_required_copy_is_present(self):
        result = validate_ocr(
            self.spec,
            self.evidence(
                list(self.spec.fixed_copy),
                observed_text_drift=["我会查询 -> 帮会查询"],
            ),
        )

        self.assertFalse(result.passed)
        self.assertTrue(any("text drift" in failure for failure in result.failures))


if __name__ == "__main__":
    unittest.main()
