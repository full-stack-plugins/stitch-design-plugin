# Scoring contract

The judge emits exactly one JSON file, `scores.json`, with this schema:

```json
{
  "scores": {
    "hierarchy": 4,
    "density": 4,
    "color": 5,
    "component_quality": 4,
    "completion": 5
  },
  "gaps": [
    {
      "id": "hero-lighting",
      "description": "The hero image renders flat where the target shows a diagonal light falloff.",
      "repair": "Add a linear-gradient overlay at 30 degrees over the hero image."
    }
  ],
  "total": 22
}
```

## Rules

- `scores` MUST contain all five axes. Each value is a number in `[1, 5]`;
  fractional values with one decimal place are allowed.
- `total` MUST equal the sum of the five axis values. The harness cross-checks
  this before consuming the file.
- `gaps` MAY be empty only when every axis is 5. A non-empty gap list with all
  axes at 5 is a contract violation (the judge missed something).
- Each gap entry MUST carry `id`, `description`, and `repair`. `id` is
  kebab-case and stable across rounds for the same defect class.

## Gap id discipline

Stable ids are what make the harness's stall detection work: when the same id
appears in two consecutive verdicts, the round is flagged as stalled. Derive
ids from the defect, not the location, so a relocated copy of the same defect
keeps its id:

- `hero-lighting`, not `hero-section-issue`
- `card-radius`, not `card-3-on-dashboard`

If two distinct defects would collide under one id, disambiguate by the
property that differs (`button-padding`, `button-contrast`), never by round
number or position alone.

## What the harness does with the file

The controlling skill passes the five axis values through the harness compare
step (`stitch_harness.py compare --scores scores.json`). The harness validates
axis presence and range, records the verdict with the real producer identity
(`stitch-visual-judge`), and appends the round to `visual_history` in the run
manifest for stall detection. The judge scores and the deterministic
`layout_score` stay separate evidence fields.
