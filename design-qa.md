# Google Stitch Token Setup Design QA

- Source visual truth: `/var/folders/_s/9_xnnkz141920t1yv5zhvd1r0000gn/T/codex-clipboard-b67357a4-5c45-49d8-8857-e4f86618025f.png`
- Implementation screenshots: `/tmp/stitch-setup-visual/desktop-v3.png`, `/tmp/stitch-setup-visual/tablet-v3.png`, `/tmp/stitch-setup-visual/mobile-v3.png`
- Full-view comparison: `/tmp/stitch-setup-visual/reference-vs-desktop.png`
- Viewports: Desktop `1280x1024`, Tablet `768x1024`, Mobile `390x884`
- Density normalization: Codex in-app browser verified at `devicePixelRatio=1`; source and implementation were fit into one comparison canvas without changing their internal proportions.
- State: initial empty Token input; advanced settings collapsed.

## Findings

No actionable P0, P1, or P2 differences remain.

- Fonts and typography: the single-line desktop headline, brand lockup, subtitle hierarchy, card heading, input text, and instruction copy follow the reference proportions. System font fallbacks intentionally replace the source product font.
- Spacing and layout rhythm: the page preserves the reference's large brand-level whitespace, centered hero, compact single card, generous card padding, rounded corners, and input-to-instruction rhythm.
- Colors and visual tokens: the pale blue, yellow-green, and cyan soft-light background and neutral white card match the reference balance; black CTA and muted supporting copy retain accessible contrast.
- Image quality and asset fidelity: the bundled Google Stitch plugin logo is used at both brand and card scale. No third-party ProcessOn or Jimeng brand asset is copied or hotlinked.
- Copy and content: the structure is exactly `Google Stitch | MCP`, one headline, one subtitle, one Token input, one save action, and three concise instructions.
- Interaction: empty submission focuses the input and shows the inline error state; Enter and click share the same save handler; the field is cleared after every response; advanced settings remain collapsed.
- Responsive/overflow: browser metrics were exact at all required sizes. Desktop: `1280/1280` width and `1024/1024` height. Tablet: `768/768` and `1024/1024`. Mobile: `390/390` and `884/884`. No horizontal or vertical overflow is present.

## Comparison History

1. Initial implementation used three large step rows and produced an oversized card. Replaced it with one Token card and three lightweight instructions.
2. First desktop pass wrapped the headline. Expanded only the hero width and reduced the desktop headline size while keeping the card at 800px.
3. CLI Chrome mobile screenshots were invalid because macOS applied a minimum outer-window width. Revalidated with the Codex in-app browser's explicit viewport capability and direct DOM scroll metrics.

## Focused Region Comparison

The Token input row was checked separately for its gray inset surface, one-pixel border, 15px radius, compact black save button, placeholder hierarchy, focus ring, and inline status spacing. No additional crop is necessary because the control remains clearly readable in the full comparison.

## Follow-up Polish

- P3: If Google later publishes a dedicated monochrome Stitch wordmark for redistribution, it could replace the current bundled square mark while preserving the same measured slot.

## Skill TRACE verification

Gate: `docs/superpowers/plans/2026-09-13-stitch-first-use-onboarding.md`, Task 4 Step 6 ("Evaluate Trust, Reliability, Adaptability, Convention, and Effectiveness. Fix every sub-item below 5.0.").

Method: `skill-trace-checker` applied strictly to `skills/stitch-local-setup/` with all four referenced files plus `scripts/stitch_setup.py` and `scripts/stitch_setup.sh` read, including the checker's automatic skill-type determination and its 20 sub-items.

- Round 1: **4.875 / 5.0 — FAIL.** Four sub-items below 5.0 (R 异常处理 4.0, R 功能完善性 4.5, E 输出准确性 4.5, E 内容完整度 4.5), all from one root cause: the skill described `check` with a single failure branch and claimed a path output, while `check()` has two failure branches and prints no path.
- Fix: documentation was aligned to the code. `check()` itself was **not** modified, and its content was confirmed byte-identical after the fix. `SKILL.md` steps 1 and 3 now state what `check` validates and split the two failure branches with distinct remediation; `references/workflow.md` item 6 lists the four actual status lines verbatim, states that no path is printed, and covers the unreadable-credential stderr branch; credential removal is documented in `SKILL.md` FAQ Q4 and `references/faq-deep.md` Q9.
- Round 2: **5.000 / 5.0 — PASS.** No sub-item remains below 5.0 and no defect was introduced; every quoted status string was verified verbatim against `check()`, and the frontmatter `description:` remains a single-line plain scalar.

final result: passed
