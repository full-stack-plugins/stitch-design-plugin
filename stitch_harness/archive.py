"""Verified archive publication and compatibility symlinks."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .contracts import PageSpec
from .state import InvalidTransition, RunState
from .storage import Run, sha256_file


@dataclass(frozen=True)
class MoveResult:
    destination: Path
    sha256: str


@dataclass(frozen=True)
class ArchiveResult:
    destination: Path


class ArchiveManager:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()

    def archive(self, run: Run, spec: PageSpec) -> ArchiveResult:
        if run.state != RunState.APPROVED:
            raise InvalidTransition("only an approved run can be archived")
        destination = self.project_root / spec.archive / run.run_id
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{run.run_id}-", dir=destination.parent))
        try:
            for name in ("spec.json", "artifacts", "receipts", "comparison"):
                source = run.path / name
                if source.is_dir():
                    shutil.copytree(source, temporary / name)
                elif source.is_file():
                    shutil.copy2(source, temporary / name)
            (temporary / "README.md").write_text(
                f"# {spec.title}\n\n- Run: `{run.run_id}`\n- Canvas: {spec.canvas.width}×{spec.canvas.height}\n- Theme: `{spec.theme}`\n",
                encoding="utf-8",
            )
            temporary.replace(destination)
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

