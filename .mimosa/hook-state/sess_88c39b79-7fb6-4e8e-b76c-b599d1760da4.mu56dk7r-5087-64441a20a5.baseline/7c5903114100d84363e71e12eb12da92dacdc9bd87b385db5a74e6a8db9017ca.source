import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from stitch_harness.evidence import EvidenceError, ExternalEvidence


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExternalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.artifact = self.root / "artifacts" / "art.png"
        self.artifact.parent.mkdir()
        self.artifact.write_bytes(b"png-content")

    def tearDown(self):
        self.temp.cleanup()

    def payload(self):
        return {
            "schema_version": 1,
            "step": "imagegen",
            "provider": {"name": "openai", "tool": "imagegen", "model": "reported-by-tool"},
            "invoked_at": "2026-09-14T00:00:00Z",
            "source_artifacts": [],
            "artifacts": [
                {
                    "path": "artifacts/art.png",
                    "sha256": digest(self.artifact),
                    "mime": "image/png",
                    "width": 1350,
                    "height": 768,
                }
            ],
            "result": {"status": "generated"},
        }

    def test_real_artifact_hash_is_accepted(self):
        evidence_path = self.root / "evidence.json"
        evidence_path.write_text(json.dumps(self.payload()), encoding="utf-8")

        evidence = ExternalEvidence.load(evidence_path, "imagegen")

        self.assertEqual(evidence.verify_artifacts(self.root), ())

    def test_provider_success_without_artifact_is_rejected(self):
        payload = self.payload()
        payload["artifacts"] = []

        with self.assertRaises(EvidenceError):
            ExternalEvidence.from_dict(payload, "imagegen")

    def test_changed_artifact_hash_is_rejected(self):
        evidence_path = self.root / "evidence.json"
        evidence_path.write_text(json.dumps(self.payload()), encoding="utf-8")
        evidence = ExternalEvidence.load(evidence_path, "imagegen")
        self.artifact.write_bytes(b"changed")

        self.assertIn("hash mismatch", " ".join(evidence.verify_artifacts(self.root)))

    def test_unknown_step_is_rejected_even_when_expected_matches(self):
        payload = self.payload()
        payload["step"] = "../../outside"

        with self.assertRaisesRegex(EvidenceError, "allowlist"):
            ExternalEvidence.from_dict(payload, "../../outside")

    def test_remote_url_query_or_fragment_is_rejected_anywhere_in_evidence(self):
        for remote in ("https://example.com/file?cache=1", "https://example.com/file#part"):
            payload = self.payload()
            payload["result"]["remote"] = remote
            with self.subTest(remote=remote), self.assertRaisesRegex(EvidenceError, "query or fragment"):
                ExternalEvidence.from_dict(payload, "imagegen")

    def test_sensitive_keys_and_embedded_sensitive_text_are_rejected_recursively(self):
        unsafe_values = (
            {"nested": {"sessionTokenValue": "private"}},
            {"note": "Bearer private-value"},
            {"note": "use api-key private-value"},
            {"note": "access_token is private"},
            {"note": "see prefix(https://example.com/file?cache=1)"},
        )
        for unsafe in unsafe_values:
            payload = self.payload()
            payload["result"] = unsafe
            with self.subTest(unsafe=unsafe), self.assertRaisesRegex(EvidenceError, "sensitive|query or fragment"):
                ExternalEvidence.from_dict(payload, "imagegen")

    def test_safe_words_that_merely_contain_sensitive_substrings_are_allowed(self):
        payload = self.payload()
        payload["result"] = {
            "designTheme": "light",
            "keyboard_navigation": True,
            "assignment": "reviewer",
            "monkey": "demo",
        }

        evidence = ExternalEvidence.from_dict(payload, "imagegen")

        self.assertEqual(evidence.result["designTheme"], "light")


if __name__ == "__main__":
    unittest.main()
