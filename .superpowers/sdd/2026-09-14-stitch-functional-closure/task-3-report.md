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

## Review Round 1

Reviewer findings were addressed in a second RED → GREEN cycle:

- Removed every `allowed-tools` entry from read-only MCP Skills, prompt/spec/router Skills, `stitch-mcp-create-project`, and `stitch-delete-project`. Deletion now explicitly requires both target-bound user approval and host runtime approval; its Skill never preapproves a wildcard MCP namespace.
- Strengthened repository tests to reject any `allowed-tools` frontmatter in those least-privilege Skills and to require each of the 15 live tools to be named by its owning Skill package.
- Expanded negative resource-name scans and corrected the remaining React/Vite dashboard and generation local-validation wording. `get_screen` always uses the full `name`; `list_screens` always uses a bare project ID.
- Removed native-store labels and migration claims from current public README, privacy, getting-started, architecture, technical, setup, and Harness Skill surfaces. Privacy and architecture now state that only HTTP 401 refreshes/retries once; HTTP 403 is permission denied and is never refreshed or replayed.
- Split root routing into local preparation, explicit upload, and explicit download. Generic local asset work no longer selects the remote uploader, and the router states that batch local asset tools remain a later 0.6.0 capability.
- Corrected current inventory references to 43 Skills while preserving manifest/release-candidate truth at `0.5.1`; Task 4 still owns the `0.5.2` bump and release.

Round 1 verification: focused Skill/distribution tests `24/24`; full isolated-runtime suite `126/126`; uploader `13/13`; distribution `43` Skills; `quick_validate` `43/43`; relative links `266` files; ShellCheck, Python compilation, and diff whitespace gates passed.

## Review Round 2

A third RED → GREEN cycle closed the remaining permission and documentation findings:

- Added an all-Skill negative scan for `stitch*:*` and a dedicated zero-preapproval contract for the seven local conversion Skills: uView, uview-plus, uView Pro, Vue Bootstrap, Vue Element Plus, Vue Layui, and Vue Vant.
- Removed the complete `allowed-tools` field from those seven Skills, including the quoted comma-form syntax in uview-plus. The only remaining `allowed-tools` entry in the repository is the local-only `Read Write Bash` declaration on `stitch-skill-creator`; no Skill preapproves a remote Stitch wildcard.
- Made the public-document stale-storage scan case-insensitive.
- Renamed the two remaining English Mermaid nodes from `System secret store` to `Restricted user config`.

Round 2 RED contained 16 expected failures: each of the seven conversion Skills failed both wildcard and local-conversion checks, and each stale English diagram node failed the case-insensitive documentation check. The focused checks passed after the minimal changes.

Round 2 final verification: isolated-runtime suite `128/128`; uploader `13/13`; distribution `43` Skills; `quick_validate` `43/43`; relative links `266` files; ShellCheck, Python compilation, and diff whitespace gates passed.
