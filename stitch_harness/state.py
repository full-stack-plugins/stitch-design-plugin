"""Finite states and legal transitions for one design delivery run."""

from __future__ import annotations

from enum import StrEnum


class RunState(StrEnum):
    DRAFT = "DRAFT"
    PREFLIGHT_PASSED = "PREFLIGHT_PASSED"
    STITCH_GENERATED = "STITCH_GENERATED"
    SOURCE_ACCEPTED = "SOURCE_ACCEPTED"
    AWAITING_ART_DECISION = "AWAITING_ART_DECISION"
    ART_ENHANCEMENT_APPROVED = "ART_ENHANCEMENT_APPROVED"
    STITCH_ONLY_SELECTED = "STITCH_ONLY_SELECTED"
    ART_GENERATED = "ART_GENERATED"
    ART_ACCEPTED = "ART_ACCEPTED"
    ROUNDTRIPPED = "ROUNDTRIPPED"
    EDITABILITY_VERIFIED = "EDITABILITY_VERIFIED"
    COMPARISON_ACCEPTED = "COMPARISON_ACCEPTED"
    AWAITING_USER_APPROVAL = "AWAITING_USER_APPROVAL"
    APPROVED = "APPROVED"
    ARCHIVED = "ARCHIVED"
    RECONCILING = "RECONCILING"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class InvalidTransition(ValueError):
    """A requested state change would bypass an approved gate."""


_TRANSITIONS = {
    RunState.DRAFT: {RunState.PREFLIGHT_PASSED, RunState.BLOCKED},
    RunState.PREFLIGHT_PASSED: {RunState.STITCH_GENERATED, RunState.RECONCILING, RunState.BLOCKED},
    RunState.STITCH_GENERATED: {RunState.SOURCE_ACCEPTED, RunState.RECONCILING, RunState.BLOCKED},
    RunState.SOURCE_ACCEPTED: {RunState.AWAITING_ART_DECISION, RunState.RECONCILING, RunState.BLOCKED},
    RunState.AWAITING_ART_DECISION: {
        RunState.ART_ENHANCEMENT_APPROVED,
        RunState.STITCH_ONLY_SELECTED,
        RunState.CANCELLED,
        RunState.BLOCKED,
    },
    RunState.ART_ENHANCEMENT_APPROVED: {RunState.ART_GENERATED, RunState.RECONCILING, RunState.BLOCKED},
    RunState.STITCH_ONLY_SELECTED: {RunState.AWAITING_USER_APPROVAL, RunState.BLOCKED},
    RunState.ART_GENERATED: {RunState.ART_ACCEPTED, RunState.RECONCILING, RunState.BLOCKED},
    RunState.ART_ACCEPTED: {RunState.ROUNDTRIPPED, RunState.RECONCILING, RunState.BLOCKED},
    RunState.ROUNDTRIPPED: {RunState.EDITABILITY_VERIFIED, RunState.RECONCILING, RunState.BLOCKED},
    RunState.EDITABILITY_VERIFIED: {RunState.COMPARISON_ACCEPTED, RunState.RECONCILING, RunState.BLOCKED},
    RunState.COMPARISON_ACCEPTED: {RunState.AWAITING_USER_APPROVAL, RunState.BLOCKED},
    RunState.AWAITING_USER_APPROVAL: {RunState.APPROVED, RunState.ART_GENERATED, RunState.BLOCKED},
    RunState.APPROVED: {RunState.ARCHIVED, RunState.AWAITING_USER_APPROVAL, RunState.BLOCKED},
    RunState.ARCHIVED: set(),
    RunState.RECONCILING: {RunState.BLOCKED},
    RunState.BLOCKED: set(),
    RunState.CANCELLED: set(),
}


def transition(current: RunState, target: RunState) -> RunState:
    """Return the target when the approved state graph allows it."""

    if target not in _TRANSITIONS[current]:
        raise InvalidTransition(f"cannot transition from {current} to {target}")
    return target
