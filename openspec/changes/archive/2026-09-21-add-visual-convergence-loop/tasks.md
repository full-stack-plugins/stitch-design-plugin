## 1. Convergence state machine

- [x] 1.1 Add the non-converged return edge in `stitch_harness/state.py`: `ART_GENERATED` returns to `ART_ENHANCEMENT_APPROVED`.
- [x] 1.2 Authorize the edge in `_target_states` and add a delivery round counter separate from `reconciliation_attempts`; the target state already exposes `imagegen.generate` through `_ACTIONS`.
- [x] 1.3 Enter `BLOCKED` when the round budget is exhausted without convergence, preserving all evidence for the user; never extend the budget automatically.
- [x] 1.4 Make the return edge bypass no existing gate: after returning, OCR, business assertions, semantic normalization, roundtrip and the editability probe all re-run as a whole.

## 2. Comparison boundary

- [x] 2.1 Narrow the comparison overwrite lock in `cli.py` from "the whole run's `visual-judge` step" to "the artifacts accepted for this round".
- [x] 2.2 Preserve the "same artifacts are never overwritten" protection and add the regression coverage it currently lacks (no test in `tests/` covers that lock today).
- [x] 2.3 Fail the comparison step with a non-zero status when scores are incomplete instead of emitting a submittable `scores: {}` evidence file.

## 3. Independent judge

- [x] 3.1 Add a plugin-local judge skill and declare it in `plugin-local-skills.json`; its name must not collide with a managed skill.
- [x] 3.2 Run the judge in a fresh context with only the target reference, the three comparison images and the previous verdict; it must not receive the executor's own diagnosis or act as the executor.
- [x] 3.3 Make the scoring contract emit the five axis scores (1-5) together with a gap list whose entries carry stable ids, attributable descriptions and repair directions.
- [x] 3.4 Encode the anti-ratchet rule: the judge is not obliged to beat the previous score, and a regression must score lower.
- [x] 3.5 Present the deterministic layout score and the judge scores as distinct sources.

## 4. Evidence provenance

- [x] 4.1 Record the real producer in `evidence_writer.visual_review()` instead of inheriting the `local-harness`/`deterministic` defaults.
- [x] 4.2 Label the deterministic layout score with its algorithm name and version inside the evidence result.
- [x] 4.3 Keep validation and loading tolerant of existing evidence files and never rewrite historical runs.

## 5. Spec contract

- [x] 5.1 Add the optional round ceiling to the `comparison` allowlist in `stitch_harness/contracts.py`, defaulting to 3.
- [x] 5.2 Update `stitch_harness/spec.schema.json` and `stitch_harness/spec-template.json` in the same batch; keep `schema_version` at 1 so existing specs need no migration.
- [x] 5.3 Update the schema validation cases in `tests/test_harness_contracts.py`.

## 6. Convergence policy

- [x] 6.1 Implement stall detection: two consecutive rounds without a full point gained across the five axes, or the same gap id named in two consecutive verdicts.
- [x] 6.2 Require a structural rework on stall and forbid treating incremental tweaks as progress.
- [x] 6.3 Stop and hand back to the user when a structural rework still shows no improvement, without consuming further rounds.
- [x] 6.4 Keep convergence a decision about continuing iteration only; entering user approval remains unchanged and no judge score may replace an explicit user approval.

## 7. Verification

- [x] 7.1 Add regression cases for the return edge, budget exhaustion into `BLOCKED`, per-round re-comparison and stall detection.
- [x] 7.2 Run plugin tests, distribution validation, and the offline plus online skill integrity checks.
- [x] 7.3 Run strict OpenSpec validation and archive the change.

## 8. Publication

- [x] 8.1 Bump the version per `AGENTS.md` and sync the three host manifests and the marketplace catalogs.
- [x] 8.2 Commit, confirm remote CI, then create the immutable tag and GitHub Release.

## 9. Upstream dependency

- [x] 9.1 Open a separate change in `full-stack-skills/stitch-skills` aligning the convergence loop and judge protocol into `stitch-delivery-harness` and `stitch-loop`; this change does not modify those managed skills.
- [x] 9.2 After the upstream release, refresh the lock file and per-skill digests through the existing sync flow.
