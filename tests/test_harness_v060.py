import contextlib
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from stitch_harness.cli import main
from stitch_harness.contracts import PageSpec
from stitch_harness.evidence import ExternalEvidence
from stitch_harness.evidence_writer import EvidenceWriter
from stitch_harness.orchestrator import Harness
from stitch_harness.state import RunState
from stitch_harness.storage import ArtifactRecord, Receipt


ROOT = Path(__file__).resolve().parents[1]
FIXED = datetime(2026, 9, 14, tzinfo=UTC)


class Harness060Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        (self.project / ".stitch/specs").mkdir(parents=True)
        shutil.copy2(ROOT / "tests/fixtures/page-spec.json", self.project / ".stitch/specs/login.json")

    def tearDown(self):
        self.temp.cleanup()

    def comparison_ready_run(self):
        harness, run = self.roundtripped_run()
        run = harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "editability"))
        return harness, harness.store.update_state(run, RunState.EDITABILITY_VERIFIED)

    def roundtripped_run(self):
        harness = Harness(preflight=lambda _: ())
        started = harness.start(self.project, "login", now=FIXED)
        run = harness.store.load(self.project, started.run_id)
        art = run.path / "artifacts/art.png"
        html = run.path / "artifacts/roundtrip.html"
        stitch = run.path / "artifacts/stitch-final.png"
        shutil.copy2(ROOT / "tests/fixtures/images/art.png", art)
        html.write_text("<main>roundtrip</main>", encoding="utf-8")
        shutil.copy2(ROOT / "tests/fixtures/images/stitch.png", stitch)
        run = harness.store.update_state(run, RunState.STITCH_GENERATED)
        run = harness.store.update_state(run, RunState.SOURCE_ACCEPTED)
        run = harness.store.append_receipt(run, Receipt.passed(
            run.run_id, run.page_id, "imagegen",
            outputs=[ArtifactRecord.from_path(run.path, art, "image/png")],
        ))
        run = harness.store.update_state(run, RunState.ART_GENERATED)
        run = harness.store.append_receipt(run, Receipt.passed(run.run_id, run.page_id, "ocr"))
        run = harness.store.update_state(run, RunState.ART_ACCEPTED)
        run = harness.store.append_receipt(run, Receipt.passed(
            run.run_id, run.page_id, "stitch.roundtrip",
            outputs=[
                ArtifactRecord.from_path(run.path, html, "text/html"),
                ArtifactRecord.from_path(run.path, stitch, "image/png"),
            ],
        ))
        return harness, harness.store.update_state(run, RunState.ROUNDTRIPPED)

    def editability_evidence(self, run, *, before_html=None, before_render=None):
        accepted_html = run.path / "artifacts/roundtrip.html"
        accepted_render = run.path / "artifacts/stitch-final.png"
        before_html = before_html or accepted_html
        before_render = before_render or accepted_render
        edited_html = run.path / "artifacts/edited.html"
        restored_html = run.path / "artifacts/restored.html"
        edited_render = run.path / "artifacts/edited.png"
        restored_render = run.path / "artifacts/restored.png"
        edited_html.write_text("<main>edited</main>", encoding="utf-8")
        restored_html.write_bytes(before_html.read_bytes())
        edited_render.write_bytes(b"edited-render")
        restored_render.write_bytes(before_render.read_bytes())
        return EvidenceWriter(run.path).editability(
            before_html, edited_html, restored_html, before_render, edited_render, restored_render
        )

    def reconciliation_probes(self, run, *, outcome="not_applied"):
        probes = []
        receipt_entries = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in sorted((run.path / "receipts").glob("*.json"))]
        unknown_path, unknown = next(item for item in reversed(receipt_entries) if item[1]["result"] == "unknown")
        attempt_id = hashlib.sha256(unknown_path.read_bytes()).hexdigest()[:12]
        unknown_time = datetime.fromisoformat(unknown["ended_at"].replace("Z", "+00:00"))
        if outcome == "applied":
            statuses = {tool: "found" for tool in ("get_project", "list_screens", "get_screen")}
        else:
            statuses = {"get_project": "found", "list_screens": "not_found", "get_screen": "not_found"}
        for index, tool in enumerate(("get_project", "list_screens", "get_screen"), start=1):
            invoked_at = (unknown_time + timedelta(seconds=index)).isoformat()
            response_id = f"probe-{index}"
            result = {"target_found": statuses[tool] == "found"}
            result_sha256 = hashlib.sha256(
                json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            artifact = run.path / "artifacts" / f"reconcile-{attempt_id}-{tool}.json"
            artifact.write_text(json.dumps({
                "tool": tool, "invoked_at": invoked_at, "response_id": response_id,
                "status": statuses[tool], "result": result,
            }, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            probes.append({
                "tool": tool,
                "invoked_at": invoked_at,
                "response_id": response_id,
                "status": statuses[tool],
                "result_sha256": result_sha256,
                "artifact": {"path": f"artifacts/reconcile-{attempt_id}-{tool}.json", "sha256": digest, "mime": "application/json"},
            })
        return probes

    def no_candidate_reconciliation_probes(self, run, *, project_id="123", expected_title="Gate Fix", complete=True, include_match=False):
        probes = self.reconciliation_probes(run)
        expected_hash = hashlib.sha256(expected_title.strip().encode("utf-8")).hexdigest()
        desired = {
            "get_project": ("found", {"target_found": True}),
            "list_screens": ("found", {
                "target_found": include_match,
                "project_id": project_id,
                "complete": complete,
                "title_hashes": [expected_hash] if include_match else [],
            }),
            "get_screen": ("skipped", {"target_found": False, "reason": "no_candidate_id"}),
        }
        for probe in probes:
            status_value, result = desired[probe["tool"]]
            artifact = run.path / probe["artifact"]["path"]
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            payload["status"] = status_value
            payload["result"] = result
            artifact.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            probe["status"] = status_value
            probe["result_sha256"] = hashlib.sha256(
                json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            probe["artifact"]["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        return probes

    def test_spec_init_is_valid_and_never_overwrites(self):
        output = self.project / ".stitch/specs/new-page.json"
        self.assertEqual(main(["spec", "init", "--project", str(self.project), "--page-id", "new-page"]), 0)
        PageSpec.load(output)
        original = output.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["spec", "init", "--project", str(self.project), "--page-id", "new-page"]), 2)
        self.assertEqual(output.read_bytes(), original)

    def test_typed_evidence_writer_hashes_artifacts_and_rejects_secret_fields(self):
        run = Harness(preflight=lambda _: ()).store.start(
            self.project, PageSpec.load(self.project / ".stitch/specs/login.json"), FIXED
        )
        artifact = run.path / "artifacts/source.html"
        artifact.write_text("<main>safe</main>", encoding="utf-8")
        writer = EvidenceWriter(run.path)
        path = writer.stitch_generation(
            artifact_paths=[artifact],
            render_metadata={"width": 1350, "height": 768, "scale": 1},
            screen={"deviceType": "DESKTOP", "width": 1350, "height": 768},
            provider_resource_ids=["projects/123/screens/" + "a" * 32],
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["step"], "stitch.generate")
        self.assertEqual(payload["artifacts"][0]["sha256"], hashlib.sha256(artifact.read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError, "sensitive"):
            writer.ocr(artifact_paths=[artifact], texts=["ok"], metadata={"authorization": "secret"})
        with self.assertRaisesRegex(ValueError, "sensitive|query or fragment"):
            writer.ocr(
                artifact_paths=[artifact], texts=["ok"],
                metadata={"source": "https://lh3.googleusercontent.com/file?X-Goog-Signature=private"},
            )
        for remote in ("https://example.com/file?cache=1", "https://example.com/file#fragment"):
            with self.subTest(remote=remote), self.assertRaisesRegex(ValueError, "query or fragment"):
                writer.ocr(artifact_paths=[artifact], texts=["ok"], metadata={"source": remote})

    def test_editability_writer_requires_exact_restore_hash_parity(self):
        run = Harness(preflight=lambda _: ()).store.start(
            self.project, PageSpec.load(self.project / ".stitch/specs/login.json"), FIXED
        )
        before_html = run.path / "artifacts/before.html"
        edited_html = run.path / "artifacts/edited.html"
        restored_html = run.path / "artifacts/restored.html"
        before_render = run.path / "artifacts/before.png"
        edited_render = run.path / "artifacts/edited.png"
        restored_render = run.path / "artifacts/restored.png"
        for path, data in ((before_html,b"a"),(edited_html,b"b"),(restored_html,b"a"),(before_render,b"c"),(edited_render,b"d"),(restored_render,b"c")):
            path.write_bytes(data)
        payload = json.loads(EvidenceWriter(run.path).editability(
            before_html, edited_html, restored_html, before_render, edited_render, restored_render
        ).read_text(encoding="utf-8"))
        self.assertTrue(payload["result"]["restored"])
        self.assertEqual(
            {item["path"] for item in payload["source_artifacts"]},
            {"artifacts/before.html", "artifacts/before.png"},
        )
        self.assertEqual(len(payload["artifacts"]), 6)
        self.assertEqual(
            {item["semantic_role"] for item in payload["artifacts"]},
            {"before_html", "edited_html", "restored_html", "before_render", "edited_render", "restored_render"},
        )
        self.assertEqual(
            {item["semantic_role"]: item["mime"] for item in payload["artifacts"]},
            {
                "before_html": "text/html", "edited_html": "text/html", "restored_html": "text/html",
                "before_render": "image/png", "edited_render": "image/png", "restored_render": "image/png",
            },
        )
        restored_html.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "restore"):
            EvidenceWriter(run.path).editability(
                before_html, edited_html, restored_html, before_render, edited_render, restored_render
            )

    def test_imagegen_writer_records_dimensions_required_by_canvas_gate(self):
        run = Harness(preflight=lambda _: ()).store.start(
            self.project, PageSpec.load(self.project / ".stitch/specs/login.json"), FIXED
        )
        artifact = run.path / "artifacts/art.png"
        shutil.copy2(ROOT / "tests/fixtures/images/art.png", artifact)
        payload = json.loads(EvidenceWriter(run.path).imagegen(
            artifact_paths=[artifact], width=1350, height=768
        ).read_text(encoding="utf-8"))
        self.assertEqual((payload["artifacts"][0]["width"], payload["artifacts"][0]["height"]), (1350, 768))

    def test_editability_before_artifacts_bind_exact_roundtrip_receipt_outputs(self):
        harness, run = self.roundtripped_run()
        evidence_path = self.editability_evidence(run)
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        self.assertEqual(
            {item["path"] for item in evidence["source_artifacts"]},
            {"artifacts/roundtrip.html", "artifacts/stitch-final.png"},
        )

        status = harness.resume(self.project, run.run_id, evidence_path)

        self.assertEqual(status.state, RunState.EDITABILITY_VERIFIED)

    def test_editability_rejects_same_hash_before_artifact_at_a_different_path(self):
        harness, run = self.roundtripped_run()
        alternate = run.path / "artifacts/copied-before.html"
        alternate.write_bytes((run.path / "artifacts/roundtrip.html").read_bytes())
        evidence_path = self.editability_evidence(run, before_html=alternate)

        status = harness.resume(self.project, run.run_id, evidence_path)

        self.assertEqual(status.state, RunState.ROUNDTRIPPED)
        self.assertIn("roundtrip receipt", " ".join(status.errors))

    def test_three_unknown_attempts_block_and_explicit_recovery_records_reason(self):
        harness = Harness(preflight=lambda _: ())
        status = harness.start(self.project, "login", now=FIXED)
        evidence = self.project / "unknown.json"
        evidence.write_text(json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}), encoding="utf-8")
        for expected_attempt in (1, 2):
            status = harness.resume(self.project, status.run_id, evidence)
            self.assertEqual(status.state, RunState.RECONCILING)
            self.assertEqual(status.reconciliation_attempts, expected_attempt)
        status = harness.resume(self.project, status.run_id, evidence)
        self.assertEqual(status.state, RunState.BLOCKED)
        self.assertEqual(status.reconciliation_attempts, 3)
        recovered = harness.recover(self.project, status.run_id, "read probes confirmed no remote screen")
        self.assertEqual(recovered.state, RunState.PREFLIGHT_PASSED)
        self.assertEqual(recovered.reconciliation_attempts, 0)
        manifest = json.loads((self.project / ".stitch/runs" / status.run_id / "manifest.json").read_text())
        self.assertEqual(manifest["last_recovery_reason"], "read probes confirmed no remote screen")

    def test_reconciliation_can_resolve_not_applied_before_attempt_limit(self):
        harness = Harness(preflight=lambda _: ())
        status = harness.start(self.project, "login", now=FIXED)
        unknown = self.project / "unknown.json"
        unknown.write_text(json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}), encoding="utf-8")
        status = harness.resume(self.project, status.run_id, unknown)
        run = harness.store.load(self.project, status.run_id)
        evidence = self.project / "reconciliation.json"
        evidence.write_text(json.dumps({
            "schema_version": 1,
            "step": "stitch.generate",
            "reconciliation": {
                "outcome": "not_applied",
                "reason": "all read probes confirm no matching screen",
                "read_probes": self.reconciliation_probes(run),
            },
        }), encoding="utf-8")

        resolved = harness.reconcile(self.project, status.run_id, evidence)

        self.assertEqual(resolved.state, RunState.PREFLIGHT_PASSED)
        self.assertEqual(resolved.reconciliation_attempts, 0)
        manifest = json.loads((self.project / ".stitch/runs" / status.run_id / "manifest.json").read_text())
        self.assertEqual(manifest["last_reconciliation_outcome"], "not_applied")
        receipt = json.loads(sorted((run.path / "receipts").glob("*.json"))[-1].read_text(encoding="utf-8"))
        self.assertEqual(receipt["step"], "reconciliation")
        self.assertEqual(len(receipt["inputs"]), 3)

        second_unknown = harness.resume(self.project, status.run_id, unknown)
        self.assertEqual(second_unknown.state, RunState.RECONCILING)
        run = harness.store.load(self.project, status.run_id)
        second_payload = json.loads(evidence.read_text(encoding="utf-8"))
        second_payload["reconciliation"]["read_probes"] = self.reconciliation_probes(run)
        evidence.write_text(json.dumps(second_payload), encoding="utf-8")
        harness.reconcile(self.project, status.run_id, evidence)
        receipts = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((run.path / "receipts").glob("*.json"))]
        self.assertEqual(sum(item["step"] == "reconciliation" for item in receipts), 2)

    def test_reconciliation_can_accept_applied_write_with_full_evidence(self):
        harness = Harness(preflight=lambda _: ())
        status = harness.start(self.project, "login", now=FIXED)
        unknown = self.project / "unknown.json"
        unknown.write_text(json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}), encoding="utf-8")
        status = harness.resume(self.project, status.run_id, unknown)
        run = harness.store.load(self.project, status.run_id)
        html = run.path / "artifacts/source.html"
        image = run.path / "artifacts/source.png"
        shutil.copy2(ROOT / "tests/fixtures/login-valid.html", html)
        shutil.copy2(ROOT / "tests/fixtures/images/stitch.png", image)
        evidence = self.project / "reconciled-applied.json"
        evidence.write_text(json.dumps({
            "schema_version": 1, "step": "stitch.generate",
            "provider": {"name": "google-stitch", "tool": "generate_screen_from_text", "model": "server"},
            "invoked_at": "2026-09-14T00:00:01Z", "source_artifacts": [],
            "artifacts": [
                {"path": "artifacts/source.html", "sha256": hashlib.sha256(html.read_bytes()).hexdigest(), "mime": "text/html"},
                {"path": "artifacts/source.png", "sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "mime": "image/png"},
            ],
            "result": {"render_metadata": {"width": 1350, "height": 768, "scale": 1}, "screen": {"deviceType": "DESKTOP", "width": 1350, "height": 768}},
            "reconciliation": {
                "outcome": "applied", "reason": "read probes found the unique generated screen",
                "read_probes": self.reconciliation_probes(run, outcome="applied"),
            },
        }), encoding="utf-8")

        resolved = harness.reconcile(self.project, status.run_id, evidence)

        self.assertEqual(resolved.state, RunState.SOURCE_ACCEPTED)
        self.assertEqual(resolved.exit_code, 0)

    def test_not_applied_reconciliation_rejects_untyped_or_unbound_probe_evidence(self):
        harness = Harness(preflight=lambda _: ())
        status = harness.start(self.project, "login", now=FIXED)
        unknown = self.project / "unknown.json"
        unknown.write_text(json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}), encoding="utf-8")
        status = harness.resume(self.project, status.run_id, unknown)
        run = harness.store.load(self.project, status.run_id)
        valid = self.reconciliation_probes(run)
        invalid_sets = []
        invalid_sets.append(["get_project", "list_screens", "get_screen"])
        missing_timezone = json.loads(json.dumps(valid)); missing_timezone[0]["invoked_at"] = "2026-09-14T00:00:01"; invalid_sets.append(missing_timezone)
        duplicate_artifact = json.loads(json.dumps(valid)); duplicate_artifact[1]["artifact"] = duplicate_artifact[0]["artifact"]; duplicate_artifact[1]["result_sha256"] = duplicate_artifact[0]["result_sha256"]; invalid_sets.append(duplicate_artifact)
        hash_mismatch = json.loads(json.dumps(valid)); hash_mismatch[0]["result_sha256"] = "0" * 64; invalid_sets.append(hash_mismatch)
        bad_status = json.loads(json.dumps(valid)); bad_status[0]["status"] = "PRIVATE_RESULT"; invalid_sets.append(bad_status)
        boolean_id = json.loads(json.dumps(valid)); boolean_id[0]["response_id"] = True; invalid_sets.append(boolean_id)
        stale = json.loads(json.dumps(valid)); stale[0]["invoked_at"] = "2000-01-01T00:00:00+00:00"; invalid_sets.append(stale)
        wrong_tool_type = json.loads(json.dumps(valid)); wrong_tool_type[0]["tool"] = {"name": "get_project"}; invalid_sets.append(wrong_tool_type)
        wrong_status_type = json.loads(json.dumps(valid)); wrong_status_type[0]["status"] = {"value": "found"}; invalid_sets.append(wrong_status_type)
        response_mismatch = json.loads(json.dumps(valid)); response_mismatch[0]["response_id"] = "different-response"; invalid_sets.append(response_mismatch)
        for index, probes in enumerate(invalid_sets):
            evidence = self.project / f"invalid-reconciliation-{index}.json"
            evidence.write_text(json.dumps({
                "schema_version": 1, "step": "stitch.generate",
                "reconciliation": {"outcome": "not_applied", "reason": "read probes found no screen", "read_probes": probes},
            }), encoding="utf-8")
            with self.subTest(index=index), self.assertRaises(ValueError):
                harness.reconcile(self.project, status.run_id, evidence)
            self.assertEqual(harness.store.load(self.project, status.run_id).state, RunState.RECONCILING)

    def test_reconcile_cli_converts_malformed_probe_types_to_contract_exit(self):
        harness = Harness(preflight=lambda _: ())
        status = harness.start(self.project, "login", now=FIXED)
        unknown = self.project / "unknown.json"
        unknown.write_text(json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}), encoding="utf-8")
        status = harness.resume(self.project, status.run_id, unknown)
        run = harness.store.load(self.project, status.run_id)
        probes = self.reconciliation_probes(run)
        probes[0]["tool"] = ["get_project"]
        evidence = self.project / "malformed-probe-type.json"
        evidence.write_text(json.dumps({
            "schema_version": 1, "step": "stitch.generate",
            "reconciliation": {"outcome": "not_applied", "reason": "read probes completed", "read_probes": probes},
        }), encoding="utf-8")

        with contextlib.redirect_stderr(io.StringIO()):
            code = main(["reconcile", "--project", str(self.project), "--run", status.run_id, "--evidence", str(evidence)])

        self.assertEqual(code, 2)

    @unittest.skipIf(__import__("os").name == "nt", "Windows symlink creation requires privileges")
    def test_reconciliation_rejects_symlink_probe_artifact(self):
        harness = Harness(preflight=lambda _: ())
        status = harness.start(self.project, "login", now=FIXED)
        unknown = self.project / "unknown.json"
        unknown.write_text(json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}), encoding="utf-8")
        status = harness.resume(self.project, status.run_id, unknown)
        run = harness.store.load(self.project, status.run_id)
        probes = self.reconciliation_probes(run)
        original = run.path / probes[0]["artifact"]["path"]
        target = original.with_name("real-probe.json")
        original.replace(target)
        original.symlink_to(target.name)
        evidence = self.project / "symlink-probe.json"
        evidence.write_text(json.dumps({
            "schema_version": 1, "step": "stitch.generate",
            "reconciliation": {"outcome": "not_applied", "reason": "read probes found no screen", "read_probes": probes},
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "symlink"):
            harness.reconcile(self.project, status.run_id, evidence)

    def test_reconciliation_rejects_contradictory_outcome_contracts(self):
        for outcome, probe_outcome in (("applied", "not_applied"), ("not_applied", "applied")):
            with self.subTest(outcome=outcome):
                with tempfile.TemporaryDirectory() as directory:
                    project = Path(directory).resolve()
                    (project / ".stitch/specs").mkdir(parents=True)
                    shutil.copy2(ROOT / "tests/fixtures/page-spec.json", project / ".stitch/specs/login.json")
                    harness = Harness(preflight=lambda _: ())
                    status = harness.start(project, "login", now=FIXED)
                    unknown = project / "unknown.json"
                    unknown.write_text(json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}), encoding="utf-8")
                    status = harness.resume(project, status.run_id, unknown)
                    run = harness.store.load(project, status.run_id)
                    evidence = project / "contradictory.json"
                    evidence.write_text(json.dumps({
                        "schema_version": 1, "step": "stitch.generate",
                        "reconciliation": {"outcome": outcome, "reason": "read probes completed", "read_probes": self.reconciliation_probes(run, outcome=probe_outcome)},
                    }), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "contract"):
                        harness.reconcile(project, status.run_id, evidence)

    def test_not_applied_reconciliation_allows_missing_screen_id_after_complete_list_probe(self):
        harness = Harness(preflight=lambda _: ())
        status = harness.start(self.project, "login", now=FIXED)
        unknown = self.project / "unknown-with-target.json"
        unknown.write_text(json.dumps({
            "schema_version": 1,
            "step": "stitch.generate",
            "result": "unknown",
            "target": {"project_id": "123", "expected_title": "Gate Fix"},
        }), encoding="utf-8")
        status = harness.resume(self.project, status.run_id, unknown)
        run = harness.store.load(self.project, status.run_id)
        probes = self.no_candidate_reconciliation_probes(run)
        evidence = self.project / "no-candidate-id.json"
        evidence.write_text(json.dumps({
            "schema_version": 1,
            "step": "stitch.generate",
            "reconciliation": {
                "outcome": "not_applied",
                "reason": "complete screen inventory contains no matching title",
                "read_probes": probes,
            },
        }), encoding="utf-8")

        resolved = harness.reconcile(self.project, status.run_id, evidence)

        self.assertEqual(resolved.state, RunState.PREFLIGHT_PASSED)
        manifest = json.loads((run.path / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["last_reconciliation_target"],
            {"project_id": "123", "expected_title": "Gate Fix"},
        )

    def test_no_candidate_reconciliation_rejects_unbound_or_incomplete_inventory(self):
        cases = (
            {"project_id": "999"},
            {"complete": False},
            {"include_match": True},
        )
        for index, options in enumerate(cases):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                project = Path(directory).resolve()
                (project / ".stitch/specs").mkdir(parents=True)
                shutil.copy2(ROOT / "tests/fixtures/page-spec.json", project / ".stitch/specs/login.json")
                harness = Harness(preflight=lambda _: ())
                status = harness.start(project, "login", now=FIXED)
                unknown = project / "unknown-with-target.json"
                unknown.write_text(json.dumps({
                    "schema_version": 1,
                    "step": "stitch.generate",
                    "result": "unknown",
                    "target": {"project_id": "123", "expected_title": "Gate Fix"},
                }), encoding="utf-8")
                status = harness.resume(project, status.run_id, unknown)
                run = harness.store.load(project, status.run_id)
                probes = self.no_candidate_reconciliation_probes(run, **options)
                evidence = project / f"unsafe-no-candidate-{index}.json"
                evidence.write_text(json.dumps({
                    "schema_version": 1,
                    "step": "stitch.generate",
                    "reconciliation": {
                        "outcome": "not_applied",
                        "reason": "inventory did not contain the target",
                        "read_probes": probes,
                    },
                }), encoding="utf-8")

                with self.assertRaisesRegex(ValueError, "contract|inventory"):
                    harness.reconcile(project, status.run_id, evidence)

    def test_applied_reconciliation_keeps_persisted_state_until_provider_receipt_commit(self):
        harness = Harness(preflight=lambda _: ())
        status = harness.start(self.project, "login", now=FIXED)
        unknown = self.project / "unknown.json"
        unknown.write_text(json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}), encoding="utf-8")
        status = harness.resume(self.project, status.run_id, unknown)
        run = harness.store.load(self.project, status.run_id)
        html = run.path / "artifacts/source.html"
        image = run.path / "artifacts/source.png"
        shutil.copy2(ROOT / "tests/fixtures/login-valid.html", html)
        shutil.copy2(ROOT / "tests/fixtures/images/stitch.png", image)
        evidence = self.project / "crash-applied.json"
        evidence.write_text(json.dumps({
            "schema_version": 1, "step": "stitch.generate",
            "provider": {"name": "google-stitch", "tool": "generate_screen_from_text", "model": "server"},
            "invoked_at": "2026-09-14T00:00:10+00:00", "source_artifacts": [],
            "artifacts": [
                {"path": "artifacts/source.html", "sha256": hashlib.sha256(html.read_bytes()).hexdigest(), "mime": "text/html"},
                {"path": "artifacts/source.png", "sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "mime": "image/png"},
            ],
            "result": {"render_metadata": {"width": 1350, "height": 768, "scale": 1}, "screen": {"deviceType": "DESKTOP", "width": 1350, "height": 768}},
            "reconciliation": {"outcome": "applied", "reason": "read probes found one screen", "read_probes": self.reconciliation_probes(run, outcome="applied")},
        }), encoding="utf-8")
        original_append = harness.store.append_receipt

        def crash_after_provider_receipt(candidate, receipt):
            persisted = json.loads((candidate.path / "manifest.json").read_text(encoding="utf-8"))["state"]
            if receipt.step == "stitch.generate" and receipt.result == "passed":
                self.assertEqual(persisted, RunState.RECONCILING.value)
                original_append(candidate, receipt)
                raise OSError("simulated crash after provider receipt")
            return original_append(candidate, receipt)

        harness.store.append_receipt = crash_after_provider_receipt
        with self.assertRaisesRegex(OSError, "simulated crash"):
            harness.reconcile(self.project, status.run_id, evidence)
        self.assertEqual(harness.store.load(self.project, status.run_id).state, RunState.RECONCILING)
        harness.store.append_receipt = original_append

        resolved = harness.reconcile(self.project, status.run_id, evidence)

        self.assertEqual(resolved.state, RunState.SOURCE_ACCEPTED)
        receipts = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((run.path / "receipts").glob("*.json"))]
        self.assertEqual(sum(item["step"] == "reconciliation" for item in receipts), 1)
        self.assertEqual(sum(item["step"] == "stitch.generate" and item["result"] == "passed" for item in receipts), 1)

    def test_recovery_reason_rejects_control_characters_and_sensitive_content(self):
        harness = Harness(preflight=lambda _: ())
        status = harness.start(self.project, "login", now=FIXED)
        unknown = self.project / "unknown.json"
        unknown.write_text(json.dumps({"schema_version": 1, "step": "stitch.generate", "result": "unknown"}), encoding="utf-8")
        for _ in range(3):
            status = harness.resume(self.project, status.run_id, unknown)
        for reason in ("two\nlines", "Authorization: private", "https://example.com/?token=private"):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, "reason"):
                harness.recover(self.project, status.run_id, reason)

    def test_compare_command_uses_only_receipt_bound_sources_and_receipt_inputs(self):
        harness, run = self.comparison_ready_run()
        scores = self.project / "scores.json"
        scores.write_text(json.dumps({name: 5 for name in ("hierarchy", "density", "color", "component_quality", "completion")}), encoding="utf-8")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main([
                "compare", "--project", str(self.project), "--run", run.run_id,
                "--scores", str(scores),
            ])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(len(payload["files"]), 3)
        evidence = json.loads(Path(payload["evidence"]).read_text(encoding="utf-8"))
        self.assertEqual(evidence["result"]["layout_score"], payload["layout_score"])
        self.assertEqual(len(evidence["artifacts"]), 3)
        self.assertEqual(
            {item["path"] for item in evidence["source_artifacts"]},
            {"artifacts/art.png", "artifacts/stitch-final.png"},
        )
        status = harness.resume(self.project, run.run_id, Path(payload["evidence"]))
        self.assertEqual(status.state, RunState.AWAITING_USER_APPROVAL)
        receipt = json.loads(sorted((run.path / "receipts").glob("*.json"))[-1].read_text(encoding="utf-8"))
        self.assertEqual(
            {item["path"] for item in receipt["inputs"]},
            {"artifacts/art.png", "artifacts/stitch-final.png"},
        )

    def test_compare_rejects_caller_selected_images(self):
        _, run = self.comparison_ready_run()
        with contextlib.redirect_stderr(io.StringIO()):
            code = main([
                "compare", "--project", str(self.project), "--run", run.run_id,
                "--stitch", str(ROOT / "tests/fixtures/images/stitch.png"),
                "--art", str(ROOT / "tests/fixtures/images/art.png"),
            ])
        self.assertEqual(code, 2)

    def test_compare_can_replace_unaccepted_outputs_but_not_accepted_visual_receipt(self):
        harness, run = self.comparison_ready_run()
        arguments = ["compare", "--project", str(self.project), "--run", run.run_id]
        self.assertEqual(main(arguments), 0)
        first_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (run.path / "comparison").glob("*.png")}
        self.assertEqual(main(arguments), 0)
        second_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (run.path / "comparison").glob("*.png")}
        self.assertEqual(second_hashes, first_hashes)

        evidence = run.path / "evidence/visual-judge.json"
        payload = json.loads(evidence.read_text(encoding="utf-8"))
        payload["result"]["scores"] = {name: 5 for name in ("hierarchy", "density", "color", "component_quality", "completion")}
        evidence.write_text(json.dumps(payload), encoding="utf-8")
        status = harness.resume(self.project, run.run_id, evidence)
        self.assertEqual(status.state, RunState.AWAITING_USER_APPROVAL)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(arguments), 2)
        self.assertEqual(
            {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (run.path / "comparison").glob("*.png")},
            second_hashes,
        )

    def test_compare_lock_uses_visual_receipt_even_when_state_update_was_interrupted(self):
        harness, run = self.comparison_ready_run()
        arguments = ["compare", "--project", str(self.project), "--run", run.run_id]
        self.assertEqual(main(arguments), 0)
        evidence = ExternalEvidence.load(run.path / "evidence/visual-judge.json", "visual-judge")
        receipt = Receipt.passed(
            run.run_id, run.page_id, "visual-judge",
            inputs=[ArtifactRecord(item.path, item.sha256, item.mime or "application/octet-stream") for item in evidence.source_artifacts],
            outputs=[ArtifactRecord(item.path, item.sha256, item.mime or "application/octet-stream") for item in evidence.artifacts],
        )
        run = harness.store.append_receipt(run, receipt)
        self.assertEqual(run.state, RunState.EDITABILITY_VERIFIED)
        before = {path.name: path.read_bytes() for path in (run.path / "comparison").glob("*.png")}

        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(arguments), 2)
        self.assertEqual({path.name: path.read_bytes() for path in (run.path / "comparison").glob("*.png")}, before)


if __name__ == "__main__":
    unittest.main()
