"""Command-line entrypoint for the Stitch Delivery Harness."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .archive import ArchiveManager
from .contracts import ContractError, PageSpec
from .orchestrator import ArtEnhancementDecision, ApprovalDecision, ApprovalRequired, Harness
from .state import RunState
from .evidence_writer import EvidenceWriter
from .visual_gate import compare_images


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stitch_harness.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    spec = subparsers.add_parser("spec")
    spec_commands = spec.add_subparsers(dest="spec_command", required=True)
    spec_init = spec_commands.add_parser("init")
    spec_init.add_argument("--project", required=True, type=Path)
    spec_init.add_argument("--page-id", required=True)
    spec_init.add_argument("--title")
    compare = subparsers.add_parser("compare")
    compare.add_argument("--project", required=True, type=Path)
    compare.add_argument("--run", required=True)
    compare.add_argument("--scores", type=Path)
    for command in ("preflight", "start", "resume", "status", "art-decision", "approve", "archive", "recover", "reconcile"):
        child = subparsers.add_parser(command)
        child.add_argument("--project", required=True, type=Path)
        if command == "start":
            child.add_argument("--spec", required=True)
        if command in {"resume", "status", "art-decision", "approve", "archive", "recover", "reconcile"}:
            child.add_argument("--run", required=True)
        if command == "art-decision":
            child.add_argument("--decision", required=True, choices=("enhance", "keep_stitch", "cancel"))
            child.add_argument("--source", required=True)
        if command == "resume":
            child.add_argument("--evidence", type=Path)
        if command == "approve":
            child.add_argument("--confirmation", required=True, type=Path)
        if command == "recover":
            child.add_argument("--reason", required=True)
        if command == "reconcile":
            child.add_argument("--evidence", required=True, type=Path)
    return parser


def _spec_init(project: Path, page_id: str, title: str | None) -> Path:
    template_path = Path(__file__).with_name("spec-template.json")
    payload = json.loads(template_path.read_text(encoding="utf-8"))
    payload["page_id"] = page_id
    payload["title"] = title or page_id.replace("-", " ").title()
    payload["archive"] = f"docs/design/{page_id}"
    PageSpec.from_dict(payload)
    destination = project / ".stitch" / "specs" / f"{page_id}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return destination


def _archive_or_recover(harness: Harness, project: Path, run_id: str) -> tuple[RunState, Path]:
    run = harness.store.load(project, run_id)
    spec = PageSpec.load(run.path / "spec.json")
    manager = ArchiveManager(project, store=harness.store)
    destination = manager._archive_destination(spec.archive, run.run_id)
    if destination.exists() and run.state == RunState.APPROVED:
        manager.verify_published_copy(run, destination)
    else:
        destination = manager.archive(run, spec).destination
    run = harness.store.update_state(run, RunState.ARCHIVED)
    return run.state, destination


def main(arguments: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(arguments)
    except SystemExit as error:
        return int(error.code)
    harness = Harness()
    try:
        if args.command == "spec":
            destination = _spec_init(args.project, args.page_id, args.title)
            print(json.dumps({"spec": str(destination)}, ensure_ascii=False, separators=(",", ":")))
            return 0
        if args.command == "compare":
            run = harness.store.load(args.project, args.run)
            if run.state != RunState.EDITABILITY_VERIFIED:
                raise ValueError("compare requires the current run to be EDITABILITY_VERIFIED")
            if harness.store.has_accepted_receipt(run, "visual-judge"):
                raise ValueError("compare cannot overwrite an accepted visual-judge receipt")
            art, stitch = harness.store.required_comparison_artifacts(run)
            comparison = compare_images(
                run.path / stitch.path,
                run.path / art.path,
                run.path / "comparison",
                replace_existing=True,
            )
            scores = json.loads(args.scores.read_text(encoding="utf-8")) if args.scores else {}
            evidence = EvidenceWriter(run.path).visual_review(
                artifact_paths=comparison.review_files,
                source_artifact_paths=(run.path / art.path, run.path / stitch.path),
                layout_score=comparison.layout_score,
                scores=scores,
            )
            print(json.dumps({"layout_score": comparison.layout_score, "evidence": str(evidence), "files": [str(path) for path in comparison.review_files]}, separators=(",", ":")))
            return 0
        if args.command == "preflight":
            errors = harness.preflight(args.project)
            payload = {"ok": not errors, "errors": list(errors)}
            print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            return 0 if not errors else 1
        if args.command == "start":
            status = harness.start(args.project, args.spec)
        elif args.command == "resume":
            status = harness.resume(args.project, args.run, args.evidence)
        elif args.command == "status":
            status = harness.status(args.project, args.run)
        elif args.command == "art-decision":
            status = harness.decide_art(
                args.project,
                args.run,
                ArtEnhancementDecision(args.decision, args.source),
            )
        elif args.command == "approve":
            payload = json.loads(args.confirmation.read_text(encoding="utf-8"))
            status = harness.approve(
                args.project,
                args.run,
                ApprovalDecision(payload["decision"], payload["source"], payload["artifact_hashes"]),
            )
        elif args.command == "recover":
            status = harness.recover(args.project, args.run, args.reason)
        elif args.command == "reconcile":
            status = harness.reconcile(args.project, args.run, args.evidence)
        else:
            state, destination = _archive_or_recover(harness, args.project, args.run)
            print(json.dumps({"run_id": args.run, "state": state.value, "archive": str(destination)}, ensure_ascii=False, separators=(",", ":")))
            return 0
    except (OSError, TypeError, ValueError, ContractError, ApprovalRequired, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(status.to_dict(), ensure_ascii=False, separators=(",", ":")))
    return status.exit_code
