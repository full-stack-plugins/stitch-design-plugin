---
name: stitch-visual-judge
description: Score a Stitch delivery candidate against its art target as an independent judge. Use when the delivery harness reaches the visual comparison step and needs the five-axis 1-5 ratings plus an actionable gap list; the executor of the candidate must not judge its own work.
license: Apache-2.0
---

# Stitch Visual Judge

Produce the visual score evidence for one convergence round of the Stitch
delivery harness. You are the **judge**, not the builder: you score the current
candidate against the accepted art target and emit a machine-readable verdict
that the harness consumes as external evidence.

## When to use

- The current run is at `EDITABILITY_VERIFIED` and the harness asks for
  `visual-judge` evidence.
- A new round started after the user rejected a previous candidate and you are
  scoring the rework.

Do not use this skill to build, edit, or re-generate any artifact. If the work
is construction, hand off to `stitch-delivery-harness`.

## Independence rules (mandatory)

1. Run in a **fresh context**. Do not fork a conversation that built the
   candidate; self-scored work drifts upward.
2. Receive only: the accepted art target image, the three comparison images
   (`side-by-side.png`, `overlay.png`, `diff-heatmap.png`) from
   `compare`, the previous round's verdict if any, and the page spec's
   `comparison` thresholds.
3. Never receive the executor's own diagnosis, intended-fix notes, or rationale
   for the current round. If the prompt contains any of these, stop and say so.
4. Score what you see, not what was intended. Never invent detail you cannot
   point to in the images.

## Scoring

Rate each axis 1-5 (fractional scores allowed, one decimal):

| Axis | Question |
|---|---|
| `hierarchy` | Are heading levels, reading order, and emphasis correct versus the target? |
| `density` | Does spacing, whitespace, and content volume match the target rhythm? |
| `color` | Do palette, contrast, and surface tones match the target? |
| `component_quality` | Do controls, cards, and imagery render at target fidelity (not blocky, plasticky, or placeholder)? |
| `completion` | Is every region of the target represented with no missing or stub content? |

Total = sum of the five axes (max 25).

## Gap list (mandatory)

List every gap that blocks a perfect score. Each entry:

- `id`: stable identifier, kebab-case, deterministic for the same defect class
  (for example `hero-lighting`, `card-radius`, `form-label-density`). Reuse the
  id when the same defect appears in a later round — this is how the harness
  detects a repeated gap.
- `description`: what exactly looks wrong and where, attributable to something
  visible in the images.
- `repair`: a concrete direction another agent can execute.

Ban non-actionable feedback. "Looks fake" is invalid; "the hero image shows
flat shading with no gradient where the target has a diagonal light falloff;
add a linear-gradient overlay at 30 degrees" is valid.

## Anti-ratchet

- Consistency with the previous verdict is required, obligation to raise the
  score is not. If the candidate regressed, score it lower than the previous
  round.
- Do not soften a gap because the previous round already named it; repeat the
  same id instead.

## Output

Write `scores.json` beneath the run directory with exactly this shape (see
[references/scoring-contract.md](references/scoring-contract.md) for the full
schema):

```json
{
  "scores": {"hierarchy": 4, "density": 4, "color": 5, "component_quality": 4, "completion": 5},
  "gaps": [
    {"id": "hero-lighting", "description": "...", "repair": "..."}
  ],
  "total": 22
}
```

Then the controlling skill feeds it to the harness compare step with the real
producer identity (`stitch-visual-judge`).

## Reporting

Present the deterministic layout score (`layout_score` from the harness
compare, algorithm `coarse-edge-mae-v2`) and the judge scores as **distinct
sources** in the final report. Never merge them into one number and never let
either replace the user's explicit approval.

## Failure handling

- Missing or unreadable comparison images: stop, name the missing file, do not
  guess scores.
- Ambiguous target: report the assumption you scored against and mark it
  `NOT_VERIFIED`.
