"""OCR recall and forbidden-content gates."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .contracts import PageSpec
from .evidence import ExternalEvidence


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


@dataclass(frozen=True)
class OcrGateResult:
    failures: tuple[str, ...]
    missing_copy: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def validate_ocr(spec: PageSpec, evidence: ExternalEvidence) -> OcrGateResult:
    texts = evidence.result.get("texts")
    if not isinstance(texts, list) or not all(isinstance(value, str) for value in texts):
        return OcrGateResult(("OCR evidence requires a text list",), spec.fixed_copy)
    combined = _normalize(" ".join(texts))
    missing = tuple(value for value in spec.fixed_copy if _normalize(value) not in combined)
    failures = [f"missing critical OCR copy: {value}" for value in missing]
    drift = evidence.result.get("observed_text_drift", [])
    if not isinstance(drift, list) or not all(isinstance(value, str) for value in drift):
        failures.append("OCR observed_text_drift must be a text list")
    elif drift:
        failures.append("OCR text drift was reported: " + "; ".join(drift))
    for pattern in spec.forbidden_patterns:
        try:
            matched = re.search(pattern, combined)
        except re.error:
            failures.append(f"invalid forbidden OCR pattern: {pattern}")
        else:
            if matched:
                failures.append(f"forbidden OCR pattern matched: {pattern}")
    return OcrGateResult(tuple(failures), missing)
