"""Verified archive publication and compatibility symlinks."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from .contracts import PageSpec
from .state import InvalidTransition, RunState
from .storage import Run, RunStore, sha256_file


@dataclass(frozen=True)
class MoveResult:
    destination: Path
    sha256: str


@dataclass(frozen=True)
class ArchiveResult:
    destination: Path


class ArchiveManager:
    def __init__(self, project_root: Path, *, store: RunStore | None = None):
        self.project_root = project_root.resolve()
        self.store = store or RunStore()

    def _archive_destination(self, archive: str, run_id: str) -> Path:
        windows_path = PureWindowsPath(archive)
        archive_path = Path(archive)
        if (
            not archive
            or "\\" in archive
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or archive_path.is_absolute()
            or ".." in archive_path.parts
        ):
            raise ValueError("archive destination must be contained under the project root")
        if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
            raise ValueError("archive destination must be contained under the project root")
        destination = self.project_root / archive_path / run_id
        try:
            destination.resolve(strict=False).relative_to(self.project_root)
        except ValueError as error:
            raise ValueError("archive destination must be contained under the project root") from error
        return destination

    def archive(self, run: Run, spec: PageSpec) -> ArchiveResult:
        if run.state != RunState.APPROVED:
            raise InvalidTransition("only an approved run can be archived")
        chain = self.store.verify_chain(run)
        if not chain.valid:
            raise ValueError("receipt chain verification failed before archive: " + "; ".join(chain.errors))
        approval = self.store.verify_approval(run)
        if not approval.valid:
            raise ValueError("approval verification failed before archive: " + "; ".join(approval.errors))
        approved_hashes = self.store.required_approval_artifacts(run)
        destination = self._archive_destination(spec.archive, run.run_id)
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{run.run_id}-", dir=destination.parent))
        try:
            for name in ("manifest.json", "spec.json", "artifacts", "receipts", "comparison"):
                source = run.path / name
                if source.is_dir():
                    shutil.copytree(source, temporary / name)
                elif source.is_file():
                    shutil.copy2(source, temporary / name)
            (temporary / "README.md").write_text(
                f"# {spec.title}\n\n- Run: `{run.run_id}`\n- Canvas: {spec.canvas.width}×{spec.canvas.height}\n- Theme: `{spec.theme}`\n",
                encoding="utf-8",
            )
            archived_run = self.store.load_from_path(temporary, run.run_id)
            if (
                archived_run.page_id != run.page_id
                or archived_run.state != run.state
                or archived_run.latest_receipt_sha256 != run.latest_receipt_sha256
            ):
                raise ValueError("archive copy manifest does not match the approved run")
            archived_chain = self.store.verify_chain(archived_run)
            archived_approval = self.store.verify_approval(archived_run)
            if not archived_chain.valid or not archived_approval.valid:
                raise ValueError("archive copy failed receipt or approval verification")
            for relative, digest in approved_hashes.items():
                if sha256_file(temporary / relative) != digest:
                    raise ValueError(f"archive copy hash mismatch: {relative}")
            temporary.replace(destination)
            published_run = self.store.load_from_path(destination, run.run_id)
            if not self.store.verify_chain(published_run).valid or not self.store.verify_approval(published_run).valid:
                raise ValueError("published archive failed receipt or approval verification")
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return ArchiveResult(destination)

    def move_with_compat_link(self, source: Path, destination: Path) -> MoveResult:
        if source.is_symlink() or not source.is_file():
            raise ValueError("source must be a regular file")
        if destination.exists():
            raise FileExistsError(destination)
        digest = sha256_file(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        relative_target = os.path.relpath(destination, start=source.parent)
        temporary_link = source.parent / f".{source.name}.link"
        try:
            temporary_link.symlink_to(relative_target)
            if sha256_file(temporary_link.resolve()) != digest:
                raise OSError("compatibility symlink hash mismatch")
            temporary_link.replace(source)
        except Exception:
            temporary_link.unlink(missing_ok=True)
            if not source.exists() and destination.exists():
                shutil.move(str(destination), str(source))
            raise
        return MoveResult(destination, digest)
