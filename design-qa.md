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

final result: passed
