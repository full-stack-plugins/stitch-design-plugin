# Task 3 Report: Repair setup, upload, and Skill contracts

## Status

Implemented and locally verified on 2026-09-14. The plugin version remains `0.5.1`; Task 4 owns the `0.5.2` release bump and publication.

## RED evidence

The first focused run failed on the intended missing behaviors:

- `migrate` remained callable and native migration/provider symbols remained exported.
- uploader still accepted `--api-key`/`--api-url`, allowed arbitrary HTTPS origins, parsed legacy `screens`/`screenInstances`, and accepted Markdown through private REST.
- `stitch-delete-project` and `stitch-design-use` did not exist.
- Skills still documented split `projectId`/`screenId` for `get_screen`, prefixed `list_screens` IDs, retired enums, and broad write permissions.
- distribution still expected 41 Skills.

Two initial test-definition errors (missing `patch` import and a local module binding) were corrected before using the run as behavioral RED evidence.

## Implemented

- Removed the user-facing `migrate` command plus native macOS/Linux/Windows secret-store implementations and migration objects. The supported chain is current-process environment then restricted user config.
- Preserved config-only setup detection through `stitch_setup.py check` and synchronized local setup guidance.
- Hardened the private upload helper:
  - obtains credentials through `platform_secret_provider()`;
  - exposes no key or endpoint argument;
  - pins production requests to `https://stitch.googleapis.com`;
  - permits only an injected loopback origin for offline tests;
  - supports PNG/JPG/JPEG/WEBP/HTML/HTM only;
  - routes Markdown to MCP `upload_design_md` guidance;
  - accepts only current `results[].screen` responses and fails closed otherwise;
  - retains no-redirect and no-automatic-retry behavior.
- Standardized Skill contracts: `get_screen` uses `name: projects/{project}/screens/{screen}` and `list_screens` uses a bare project ID across MCP, conversion, upload, design analysis, and design-system references.
- Removed frozen model/device/font/color-variant enum guidance; live schema is authoritative. Product viewports remain Mobile 390x884, Tablet 768x1024, and Desktop 1280x1024 as prompt/design requirements, not MCP enum claims.
- Added `stitch-delete-project` with exact target preview, target-bound explicit approval, one delete call, and read-only reconciliation.
- Added root `stitch-design-use` routing setup, reads, writes, design systems, assets, delete, and complete Harness delivery.
- Narrowed read-only and prompt-only Skill permissions and added tool-to-Skill coverage tests for all 15 live tools.
- Updated English/Chinese overview and architecture/technical documents to the current 43-Skill inventory and removed obsolete native-store migration claims.

## TRACE self-check

All changed Skill packages were reviewed after content changes using the TRACE checklist. The domain is Google Stitch, so the third-party-platform localization allowance was applied; Chinese user paths and domestic business examples are retained where appropriate.

| Dimension | Score | Evidence |
| --- | ---: | --- |
| Trust | 5.0 | explicit authorization boundaries, secret/privacy prohibitions, destructive target binding, no invented remote proof |
| Reliability | 5.0 | unknown-write reconciliation, no blind retry, precise missing-input paths, config-check fallback |
| Adaptability | 5.0 | narrow router, three viewport targets, read/write/asset/design-system/delete/Harness handoffs |
| Convention | 5.0 | valid frontmatter, quick starts, progressive references/examples, anti-pattern and deep FAQ resources on materially authored Skills |
| Effectiveness | 5.0 | copyable requests, exact live tool arguments, current response contract, tool ownership coverage |

`quick_validate.py` passed for all 43 Skills using the existing `/usr/local/bin/python3` runtime with PyYAML 6.0.3.

## Verification evidence

- Upload tests: `13/13` passed.
- Focused Task 3 and distribution tests: `47/47` passed.
- Full suite with the repository-defined isolated Harness runtime (Pillow 12.3.0): `123/123` passed.
- Distribution validator: `validated 43 skills and compatibility distribution 0.5.1`.
- Skill validation: `43/43` passed.
- Relative Markdown links: `266` files passed.
- `shellcheck scripts/stitch_setup.sh`: passed.
- Python compilation for setup, secrets, and uploader: passed.
- `git diff --check`: passed.

The ordinary Homebrew `python3` lacks Pillow, so its full-suite run reported two visual-gate environment errors. `scripts/setup_harness_runtime.py check` verified the project runtime has Pillow 12.3.0, and the complete suite passed there.

## Compatibility and remaining risk

- No live remote upload or deletion was performed; this task provides offline contract evidence only.
- The loopback upload path is test-injected; production code remains pinned to the exact Google origin.
- Task 4 must perform the version bump, release, installation parity, and host validation. Task 5 owns new executable local asset tools and wider Harness capability closure.
