"""Deterministic review images and externally scored visual gates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile

from .contracts import PageSpec
from .evidence import ExternalEvidence


class DimensionMismatch(ValueError):
    """Images cannot be compared without exact canvas parity."""


@dataclass(frozen=True)
class ComparisonResult:
    review_files: tuple[Path, ...]
    layout_score: float
    algorithm_version: str = "coarse-edge-mae-v2"


@dataclass(frozen=True)
class VisualGateResult:
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def compare_images(stitch_path: Path, art_path: Path, output_dir: Path, *, replace_existing: bool = False) -> ComparisonResult:
    try:
        from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageStat
    except ModuleNotFoundError as error:
        raise RuntimeError("Pillow runtime is not installed; run setup_harness_runtime.py install") from error

    with Image.open(stitch_path) as stitch_source, Image.open(art_path) as art_source:
        stitch = stitch_source.convert("RGB")
        art = art_source.convert("RGB")
    if stitch.size != art.size:
        raise DimensionMismatch(f"image dimensions differ: {stitch.size} != {art.size}")
    output_has_files = output_dir.exists() and any(output_dir.iterdir())
    if output_has_files and not replace_existing:
        raise FileExistsError("comparison output directory must be empty")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    side_by_side = Image.new("RGB", (stitch.width * 2, stitch.height), "white")
    side_by_side.paste(stitch, (0, 0))
    side_by_side.paste(art, (stitch.width, 0))
    overlay = Image.blend(stitch, art, 0.5)
    difference = ImageChops.difference(stitch, art)
    heatmap = ImageEnhance.Contrast(difference).enhance(4.0)
    staged_files = (
        stage / "side-by-side.png",
        stage / "overlay.png",
        stage / "diff-heatmap.png",
    )
    try:
        side_by_side.save(staged_files[0], format="PNG")
        overlay.save(staged_files[1], format="PNG")
        heatmap.save(staged_files[2], format="PNG")
        blur_radius = max(1.0, min(stitch.size) / 220.0)
        first_edges = stitch.convert("L").filter(ImageFilter.GaussianBlur(blur_radius)).filter(ImageFilter.FIND_EDGES)
        second_edges = art.convert("L").filter(ImageFilter.GaussianBlur(blur_radius)).filter(ImageFilter.FIND_EDGES)
        edge_difference = ImageChops.difference(first_edges, second_edges)
        mean_absolute_error = ImageStat.Stat(edge_difference).mean[0] / 255.0
        backup: Path | None = None
        if output_dir.exists():
            if output_has_files:
                backup = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-backup-", dir=output_dir.parent))
                backup.rmdir()
                output_dir.replace(backup)
            else:
                output_dir.rmdir()
        try:
            stage.replace(output_dir)
        except Exception:
            if backup is not None and backup.exists() and not output_dir.exists():
                backup.replace(output_dir)
            raise
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    files = tuple(output_dir / path.name for path in staged_files)
    return ComparisonResult(files, round(max(0.0, 1.0 - mean_absolute_error), 6))


def validate_visual_scores(spec: PageSpec, evidence: ExternalEvidence) -> VisualGateResult:
    scores = evidence.result.get("scores")
    required = ("hierarchy", "density", "color", "component_quality", "completion")
    if not isinstance(scores, dict):
        return VisualGateResult(("visual evidence requires scores",))
    failures: list[str] = []
    for name in required:
        score = scores.get(name)
        if not isinstance(score, (int, float)) or not 1 <= score <= 5:
            failures.append(f"{name} score must be between 1 and 5")
        elif score < spec.comparison.visual_quality_score_min:
            failures.append(f"{name} score {score} is below {spec.comparison.visual_quality_score_min}")
    return VisualGateResult(tuple(failures))
