"""Deterministic review images and externally scored visual gates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .contracts import PageSpec
from .evidence import ExternalEvidence


class DimensionMismatch(ValueError):
    """Images cannot be compared without exact canvas parity."""


@dataclass(frozen=True)
class ComparisonResult:
    review_files: tuple[Path, ...]
    layout_score: float
    algorithm_version: str = "edge-mae-v1"


@dataclass(frozen=True)
class VisualGateResult:
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def compare_images(stitch_path: Path, art_path: Path, output_dir: Path) -> ComparisonResult:
    try:
        from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageStat
    except ModuleNotFoundError as error:
        raise RuntimeError("Pillow runtime is not installed; run setup_harness_runtime.py install") from error

    with Image.open(stitch_path) as stitch_source, Image.open(art_path) as art_source:
        stitch = stitch_source.convert("RGB")
        art = art_source.convert("RGB")
    if stitch.size != art.size:
        raise DimensionMismatch(f"image dimensions differ: {stitch.size} != {art.size}")
    output_dir.mkdir(parents=True, exist_ok=True)
    side_by_side = Image.new("RGB", (stitch.width * 2, stitch.height), "white")
    side_by_side.paste(stitch, (0, 0))
    side_by_side.paste(art, (stitch.width, 0))
    overlay = Image.blend(stitch, art, 0.5)
    difference = ImageChops.difference(stitch, art)
    heatmap = ImageEnhance.Contrast(difference).enhance(4.0)
    files = (
        output_dir / "side-by-side.png",
        output_dir / "overlay.png",
        output_dir / "diff-heatmap.png",
    )
    side_by_side.save(files[0], format="PNG")
    overlay.save(files[1], format="PNG")
    heatmap.save(files[2], format="PNG")
    first_edges = stitch.convert("L").filter(ImageFilter.FIND_EDGES)
    second_edges = art.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_difference = ImageChops.difference(first_edges, second_edges)
    mean_absolute_error = ImageStat.Stat(edge_difference).mean[0] / 255.0
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

