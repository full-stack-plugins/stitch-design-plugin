"""Command-line entrypoint for the Stitch Delivery Harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .archive import ArchiveManager
from .contracts import ContractError, PageSpec
from .orchestrator import ApprovalDecision, ApprovalRequired, Harness
from .state import RunState


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stitch_harness.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("preflight", "start", "resume", "status", "approve", "archive"):
        child = subparsers.add_parser(command)
        child.add_argument("--project", required=True, type=Path)
        if command == "start":
            child.add_argument("--spec", required=True)
        if command in {"resume", "status", "approve", "archive"}:
            child.add_argument("--run", required=True)
        if command == "resume":
            child.add_argument("--evidence", type=Path)
        if command == "approve":
            child.add_argument("--confirmation", required=True, type=Path)
    return parser


def main(arguments: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(arguments)
    except SystemExit as error:
        return int(error.code)
    harness = Harness()
    try:
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
        elif args.command == "approve":
            payload = json.loads(args.confirmation.read_text(encoding="utf-8"))
            status = harness.approve(
                args.project,
                args.run,
                ApprovalDecision(payload["decision"], payload["source"], payload["artifact_hashes"]),
            )
        else:
            run = harness.store.load(args.project, args.run)
            spec = PageSpec.load(run.path / "spec.json")
            result = ArchiveManager(args.project).archive(run, spec)
            run = harness.store.update_state(run, RunState.ARCHIVED)
            print(json.dumps({"run_id": run.run_id, "state": run.state.value, "archive": str(result.destination)}, ensure_ascii=False, separators=(",", ":")))
            return 0
    except (OSError, ValueError, ContractError, ApprovalRequired, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(status.to_dict(), ensure_ascii=False, separators=(",", ":")))
    return status.exit_code
