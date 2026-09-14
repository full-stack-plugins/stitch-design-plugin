"""Deterministic normalization of Stitch semantic purpose attributes."""

from __future__ import annotations

import re
from collections.abc import Mapping


def normalize_purposes(source: str, mapping: Mapping[str, str]) -> str:
    """Rename declared data-purpose values without changing visible content."""

    result = source
    for old, new in mapping.items():
        if not old or not new:
            raise ValueError("semantic purpose names must be non-empty")
        pattern = re.compile(rf'(data-purpose=["\']){re.escape(old)}(["\'])')
        if len(pattern.findall(result)) != 1:
            raise ValueError(f"source purpose must occur exactly once: {old}")
        result = pattern.sub(rf"\g<1>{new}\g<2>", result, count=1)
    return result
