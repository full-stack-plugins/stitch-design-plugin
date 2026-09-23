"""Direct contract tests for Harness._validate_reconciliation_probes.

The reconciliation flow tests in test_harness_v060.py exercise these rules
through reconcile(); this module pins every per-probe rejection branch and
acceptance contract of the validator itself.
"""

import hashlib
import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from stitch_harness.evidence import EvidenceError
from stitch_harness.orchestrator import Harness

ROOT = Path(__file__).resolve().parents[1]
FIXED = datetime(2026, 9, 14, tzinfo=UTC)
TOOLS = ("get_project", "list_screens", "get_screen")


class ProbeContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        (self.project / ".stitch/specs").mkdir(parents=True)
        shutil.copy2(ROOT / "tests/fixtures/page-spec.json", self.project / ".stitch/specs/login.json")
        self.harness = Harness(preflight=lambda _: ())
        started = self.harness.start(self.project, "login", now=FIXED)
        self.run = self.harness.store.load(self.project, started.run_id)

    def tearDown(self):
        self.temp.cleanup()

    def make_probe(self, tool, index, status, *, result=None, relpath=None, second=None):
        result = {"target_found": status == "found"} if result is None else result
        invoked_at = datetime(2026, 9, 14, 0, 0, index, tzinfo=UTC).isoformat()
        response_id = f"probe-{index}"
        relpath = relpath or f"artifacts/probe-{index}.json"
        payload = {
            "tool": tool, "invoked_at": invoked_at, "response_id": response_id,
            "status": status, "result": result,
        }
        if second is not None:
            payload.update(second)
        artifact = self.run.path / relpath
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        probe = {
            "tool": tool,
            "invoked_at": invoked_at,
            "response_id": response_id,
            "status": status,
            "result_sha256": hashlib.sha256(
                json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "artifact": {
                "path": relpath,
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "mime": "application/json",
            },
        }
        return probe

    def build_probes(self, outcome="applied"):
        if outcome == "applied":
            statuses = dict.fromkeys(TOOLS, "found")
        else:
            statuses = {"get_project": "found", "list_screens": "not_found", "get_screen": "not_found"}
        return [self.make_probe(tool, index, statuses[tool]) for index, tool in enumerate(TOOLS, start=1)]

    def validate(self, probes, outcome="applied"):
        return self.harness._validate_reconciliation_probes(
            self.run, probes, outcome=outcome, unknown_ended_at=FIXED,
        )

    def assert_rejects(self, probes, message, outcome="applied"):
        with self.assertRaises(ValueError) as caught:
            self.validate(probes, outcome=outcome)
        self.assertEqual(str(caught.exception), message)

    # ---- entry shape -------------------------------------------------

    def test_requires_three_typed_entries(self):
        for broken in ([], self.build_probes()[:2], self.build_probes() + [{}], "probes", [1, 2, 3]):
            with self.subTest(broken=repr(broken)[:30]):
                self.assert_rejects(broken, "reconciliation requires three typed read probe entries")

    def test_probe_fields_must_match_contract(self):
        for mutation in ({"extra": 1}, None):
            probes = self.build_probes()
            if mutation:
                probes[0].update(mutation)
            else:
                del probes[0]["status"]
            with self.subTest(mutation=repr(mutation)):
                self.assert_rejects(probes, "reconciliation probe fields do not match the typed contract")

    def test_sensitive_probe_content_rejected(self):
        probes = self.build_probes()
        probes[0]["response_id"] = "https://evil.example.com/secret.png"
        with self.assertRaises(EvidenceError):
            self.validate(probes)

    # ---- field contracts ---------------------------------------------

    def test_tool_must_be_string(self):
        probes = self.build_probes()
        probes[0]["tool"] = 123
        self.assert_rejects(probes, "reconciliation probe tool must be a string")

    def test_invoked_at_requires_timezone_timestamp(self):
        for bad in (123, "yesterday", "2026-09-14T00:00:01"):
            probes = self.build_probes()
            probes[0]["invoked_at"] = bad
            with self.subTest(bad=bad):
                self.assert_rejects(probes, "reconciliation probe requires a timezone timestamp")

    def test_stale_probe_timestamp_rejected(self):
        probes = self.build_probes()
        probes[0]["invoked_at"] = FIXED.isoformat()
        self.assert_rejects(probes, "reconciliation probe timestamp is stale")

    def test_response_id_invalid(self):
        for bad in (True, "", "x" * 129):
            probes = self.build_probes()
            probes[0]["response_id"] = bad
            with self.subTest(bad=repr(bad)[:20]):
                self.assert_rejects(probes, "reconciliation probe response id is invalid")

    def test_response_ids_must_be_unique(self):
        probes = self.build_probes()
        probes[1]["response_id"] = probes[0]["response_id"]
        self.assert_rejects(probes, "reconciliation probe response ids must be unique")

    def test_status_contract(self):
        probes = self.build_probes()
        probes[0]["status"] = 7
        self.assert_rejects(probes, "reconciliation probe status must be a string")
        probes = self.build_probes()
        probes[0]["status"] = "maybe"
        self.assert_rejects(probes, "reconciliation probe status is invalid")

    # ---- artifact contracts ------------------------------------------

    def test_artifact_object_contract(self):
        for bad in ("file.json", {"path": "artifacts/x.json"}):
            probes = self.build_probes()
            probes[0]["artifact"] = bad
            with self.subTest(bad=repr(bad)):
                self.assert_rejects(probes, "reconciliation probe artifact is invalid")

    def test_artifact_must_be_run_local_json(self):
        probes = self.build_probes()
        probes[0]["artifact"]["mime"] = "text/html"
        self.assert_rejects(probes, "reconciliation probe artifact must be run-local JSON")
        probes = self.build_probes()
        probes[1]["artifact"]["path"] = "data/probe.json"
        self.assert_rejects(probes, "reconciliation probe artifact must be run-local JSON")

    def test_artifact_paths_must_be_unique(self):
        probes = self.build_probes()
        shared = probes[0]["artifact"]["path"]
        probes[1]["artifact"] = dict(probes[0]["artifact"], path=shared)
        self.assert_rejects(probes, "reconciliation probe artifacts must be unique")

    def test_artifact_path_escape_rejected(self):
        probes = self.build_probes()
        probes[0]["artifact"]["path"] = "artifacts/../escape.json"
        with self.assertRaises(EvidenceError) as caught:
            self.validate(probes)
        self.assertEqual(str(caught.exception), "evidence artifact path must stay beneath the run")

    def test_artifact_missing_path_rejected_as_uncontained(self):
        probes = self.build_probes()
        probes[0]["artifact"]["path"] = "artifacts/missing.json"
        self.assert_rejects(probes, "reconciliation probe artifact must stay contained under the run")

    def test_artifact_directory_rejected_as_missing(self):
        probes = self.build_probes()
        (self.run.path / "artifacts/not-a-file.json").mkdir()
        probes[0]["artifact"]["path"] = "artifacts/not-a-file.json"
        self.assert_rejects(probes, "reconciliation probe artifact is missing")

    def test_artifact_hash_mismatch(self):
        probes = self.build_probes()
        artifact = self.run.path / probes[0]["artifact"]["path"]
        artifact.write_text(artifact.read_text(encoding="utf-8") + " ", encoding="utf-8")
        self.assert_rejects(probes, "reconciliation probe artifact hash mismatch")

    def test_artifact_must_be_valid_utf8_json(self):
        probes = self.build_probes()
        artifact = self.run.path / probes[0]["artifact"]["path"]
        artifact.write_text("not-json{", encoding="utf-8")
        probes[0]["artifact"]["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        self.assert_rejects(probes, "reconciliation probe artifact must be valid UTF-8 JSON")

    def test_artifact_payload_keys_contract(self):
        probes = self.build_probes()
        original = self.make_probe("get_project", 1, "found", second={"extra": 1})
        probes[0] = original
        self.assert_rejects(probes, "reconciliation probe artifact content does not match its declaration")

    def test_artifact_declaration_must_match_content(self):
        probes = self.build_probes()
        original = self.make_probe("get_project", 1, "found", second=None)
        relpath = original["artifact"]["path"]
        payload = json.loads((self.run.path / relpath).read_text(encoding="utf-8"))
        payload["status"] = "not_found"
        (self.run.path / relpath).write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        original["artifact"]["sha256"] = hashlib.sha256((self.run.path / relpath).read_bytes()).hexdigest()
        probes[0] = original
        self.assert_rejects(probes, "reconciliation probe artifact content does not match its declaration")

    def test_result_sha256_must_match_parsed_result(self):
        probes = self.build_probes()
        probes[0]["result_sha256"] = "0" * 64
        self.assert_rejects(probes, "reconciliation result hash does not match the parsed result")

    # ---- result contracts --------------------------------------------

    def test_result_shape_contract(self):
        for result in ("text", {"target_found": "yes"}, {"target_found": True, "reason": "no_candidate_id"}):
            probes = self.build_probes()
            replacement = self.make_probe(probes[0]["tool"], 1, probes[0]["status"], result=result)
            probes[0] = replacement
            with self.subTest(result=repr(result)):
                self.assert_rejects(probes, "reconciliation probe result contract is invalid")

    def test_skipped_result_requires_no_candidate_reason(self):
        probes = self.build_probes()
        replacement = self.make_probe(
            "get_screen", 3, "skipped",
            result={"target_found": False, "reason": "other"},
        )
        probes[2] = replacement
        self.assert_rejects(probes, "reconciliation probe result contract is invalid")

    def test_inventory_result_contract(self):
        self.write_manifest_target()
        for bad in (
            {"target_found": False, "project_id": 7, "complete": True, "title_hashes": []},
            {"target_found": False, "project_id": "123", "complete": "yes", "title_hashes": []},
            {"target_found": False, "project_id": "123", "complete": True, "title_hashes": ["zz"]},
            {"target_found": False, "project_id": "123", "complete": True,
             "title_hashes": ["0" * 64, "0" * 64]},
        ):
            probes = self.build_probes(outcome="not_applied")
            probes[1] = self.make_probe("list_screens", 2, "found", result=bad)
            with self.subTest(bad=repr(bad)[:50]):
                self.assert_rejects(probes, "reconciliation probe result contract is invalid", outcome="not_applied")

    # ---- trio and outcome contracts ----------------------------------

    def test_tool_trio_required(self):
        probes = self.build_probes()
        probes[2] = self.make_probe("get_project", 3, "found")
        self.assert_rejects(probes, "reconciliation requires get_project, list_screens, and get_screen")

    def test_applied_contract_contradiction(self):
        probes = self.build_probes()
        probes[1] = self.make_probe("list_screens", 2, "not_found", result={"target_found": False})
        self.assert_rejects(probes, "reconciliation applied probe contract is contradictory")

    def test_applied_happy_path_returns_records_and_checks(self):
        records, checks = self.validate(self.build_probes())
        self.assertEqual(len(records), 3)
        self.assertEqual([check["tool"] for check in checks], list(TOOLS))
        self.assertTrue(all(check["target_found"] for check in checks))

    def test_legacy_not_applied_contract_accepted(self):
        records, checks = self.validate(self.build_probes(outcome="not_applied"), outcome="not_applied")
        self.assertEqual(len(records), 3)
        self.assertEqual([check["target_found"] for check in checks], [True, False, False])

    def write_manifest_target(self, expected_title="Gate Fix", project_id="123"):
        manifest_path = self.run.path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["reconciliation_target"] = {"project_id": project_id, "expected_title": expected_title}
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        return hashlib.sha256(expected_title.strip().encode("utf-8")).hexdigest()

    def no_candidate_probes(self, title_hashes):
        probes = self.build_probes(outcome="not_applied")
        probes[0] = self.make_probe("get_project", 1, "found", result={"target_found": True})
        probes[1] = self.make_probe("list_screens", 2, "found", result={
            "target_found": False, "project_id": "123", "complete": True,
            "title_hashes": list(title_hashes),
        })
        probes[2] = self.make_probe(
            "get_screen", 3, "skipped",
            result={"target_found": False, "reason": "no_candidate_id"},
        )
        return probes

    def test_no_candidate_contract_accepted_when_title_unbound(self):
        expected_hash = self.write_manifest_target()
        records, checks = self.validate(self.no_candidate_probes([]), outcome="not_applied")
        self.assertEqual(len(records), 3)
        self.assertEqual(checks[-1]["reason"], "no_candidate_id")
        self.assertNotIn(expected_hash, checks[1]["title_hashes"])

    def test_no_candidate_contract_rejects_bound_title(self):
        expected_hash = self.write_manifest_target()
        self.assert_rejects(
            self.no_candidate_probes([expected_hash]),
            "reconciliation not_applied probe contract is contradictory",
            outcome="not_applied",
        )


if __name__ == "__main__":
    unittest.main()
