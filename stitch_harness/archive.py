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

    def verify_published_copy(self, source: Run, published_path: Path) -> Run:
        """Verify identity, spec, chain and approval parity for an archive copy."""

        published = self.store.load_from_path(published_path, source.run_id)
        if (
            published.run_id != source.run_id
            or published.page_id != source.page_id
            or published.state != source.state
            or published.latest_receipt_sha256 != source.latest_receipt_sha256
        ):
            raise ValueError("archive copy manifest does not match the approved source run")
        source_spec = source.path / "spec.json"
        published_spec = published.path / "spec.json"
        if not source_spec.is_file() or not published_spec.is_file() or sha256_file(source_spec) != sha256_file(published_spec):
            raise ValueError("archive copy spec does not match the approved source run")
        source_chain = self.store.verify_chain(source)
        published_chain = self.store.verify_chain(published)
        source_approval = self.store.verify_approval(source)
        published_approval = self.store.verify_approval(published)
        if not source_chain.valid or not published_chain.valid or not source_approval.valid or not published_approval.valid:
            raise ValueError("archive copy failed source/published receipt or approval verification")
        if self.store.required_approval_artifacts(source) != self.store.required_approval_artifacts(published):
            raise ValueError("archive copy approval set does not match the approved source run")
        return published

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
            self.verify_published_copy(run, temporary)
            for relative, digest in approved_hashes.items():
                if sha256_file(temporary / relative) != digest:
                    raise ValueError(f"archive copy hash mismatch: {relative}")
            temporary.replace(destination)
            try:
                self.verify_published_copy(run, destination)
            except Exception as error:
                destination.replace(temporary)
                raise ValueError("published archive failed source/copy verification") from error
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
