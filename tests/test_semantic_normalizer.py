import unittest

from stitch_harness.semantic_normalizer import normalize_purposes


class SemanticNormalizerTests(unittest.TestCase):
    def test_normalizes_only_declared_purpose_values(self):
        source = (
            '<header data-purpose="old-header"></header>'
            '<main data-purpose="old-stream"></main>'
            '<p>visible text stays byte-identical</p>'
        )

        result = normalize_purposes(
            source,
            {"old-header": "top-app-bar", "old-stream": "chat-stream"},
        )

        self.assertIn('data-purpose="top-app-bar"', result)
        self.assertIn('data-purpose="chat-stream"', result)
        self.assertIn('<p>visible text stays byte-identical</p>', result)

    def test_rejects_missing_or_duplicate_source_purposes(self):
        with self.assertRaises(ValueError):
            normalize_purposes('<main></main>', {"missing": "chat-stream"})
        with self.assertRaises(ValueError):
            normalize_purposes(
                '<main data-purpose="old"></main><aside data-purpose="old"></aside>',
                {"old": "chat-stream"},
            )


if __name__ == "__main__":
    unittest.main()
