# Stitch Design for Codex

![Codex × Google Stitch — Turn ideas into editable interfaces](assets/stitch-hero.png)

> Design, verify, art-direct, and deliver editable Google Stitch projects from Codex through 43 workflow-oriented Agent Skills and an evidence-driven Harness.

[![Version](https://img.shields.io/badge/candidate-0.7.2-1A73E8)](https://github.com/partme-ai/codex-stitch-plugin)
[![Tests](https://img.shields.io/badge/tests-222%20passing-18a957)](#development-and-verification)
[![MCP tools](https://img.shields.io/badge/MCP%20tools-17-00A67E)](#what-you-can-build)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

[English](README.md) | [简体中文](README.zh-CN.md) · [Quick start](#install-in-two-commands) · [Examples](#example-requests) · [Architecture](docs/Stitch-Design-Architecture.md) · [Troubleshooting](#troubleshooting)

## Stitch Design in Codex

![Stitch Design plugin details in Codex, including starter prompts, MCP server, and 43 Skills](assets/readme/stitch-design-plugin-overview.png)

The installed plugin exposes three ready-to-run prompts, one bundled Stitch MCP server, 43 workflow Skills, and a secure local Token setup directly in Codex.

## Positioning

`stitch-design` turns product ideas and existing interfaces into editable Google Stitch screens, then carries those artifacts into production frontend workflows. It combines live Stitch generation and editing, design-system operations, code-to-design, local asset import/export, framework conversion, and an evidence-driven Delivery Harness.

| 43 workflow Skills | 17 MCP tools | 15+ frontend targets | 3 verified viewports |
|:---:|:---:|:---:|:---:|
| Design, safety, conversion, delivery | 15 Google Stitch + 2 local asset tools | React, Vue, mobile and more | Desktop, tablet, mobile |

## Quick start

Recommended: track the repository's `main` branch explicitly.

```bash
codex plugin marketplace add partme-ai/codex-stitch-plugin --ref main
codex plugin add stitch-design@partme-ai-stitch
```

Restart Codex or the ChatGPT desktop app, open a new task, and ask Stitch Design to list your projects.

### Other supported Marketplace sources

GitHub shorthand using the repository's default branch:

```bash
codex plugin marketplace add partme-ai/codex-stitch-plugin
codex plugin add stitch-design@partme-ai-stitch
```

Full Git URL pinned to `main`:

```bash
codex plugin marketplace add https://github.com/partme-ai/codex-stitch-plugin.git --ref main
codex plugin add stitch-design@partme-ai-stitch
```

Sparse Git checkout when only Marketplace metadata is needed:

```bash
codex plugin marketplace add https://github.com/partme-ai/codex-stitch-plugin.git \
  --ref main \
  --sparse .agents/plugins
codex plugin add stitch-design@partme-ai-stitch
```

Local checkout for development:

```bash
git clone https://github.com/partme-ai/codex-stitch-plugin.git
codex plugin marketplace add ./codex-stitch-plugin
codex plugin add stitch-design@partme-ai-stitch
```

Confirm or refresh the installation:

```bash
codex plugin marketplace list
codex plugin list
codex plugin marketplace upgrade partme-ai-stitch
```

The Marketplace name is `partme-ai-stitch`; the install selector is `stitch-design@partme-ai-stitch`.

## First use: one local Token screen

The plugin already bundles its MCP connection. The first Stitch request checks credentials and opens the local Token screen only when `STITCH_API_KEY` is missing.

```mermaid
flowchart LR
    A[Install plugin] --> B[Restart and open a new task]
    B --> C{Token available?}
    C -->|No| D[Open local Token screen]
    D --> E[Create key in Stitch Settings]
    E --> F[Save to restricted user config]
    C -->|Yes| G[Read-only project check]
    F --> G
    G --> H[Generate · edit · export]
```

On the first MCP request without a credential, or after a refreshed credential is still rejected with HTTP 401, the plugin automatically opens this local Token screen. A 10-minute cooldown prevents repeated windows while setup is in progress.

1. Create your key in [Stitch Settings](https://stitch.withgoogle.com/settings).
2. Paste it into the masked local field. Never paste it into chat.
3. Return to Codex; start with a read-only request such as “List my Stitch projects.”

Manual fallback if the browser does not open:

```bash
# macOS / Linux
python /path/to/installed/plugin/scripts/stitch_setup.py ui

# Windows
python C:\path\to\installed\plugin\scripts\stitch_setup.py ui
```

The setup page listens only on `127.0.0.1`, loads bundled assets, validates Origin and CSRF, never logs the key, and clears the field after every response. The cooldown marker stores only a launch timestamp. The `python` command on PATH must resolve to Python 3.11 or newer.

## What you can build

| Workflow | Built-in path | Verifiable output |
|:---|:---|:---|
| Create and iterate | Generate, inspect, edit, variants | Bound project and screen identities |
| Govern visual systems | Create, update, list, apply design systems | Design-system identity and version evidence |
| Bring existing UI into Stitch | Upload reviewed HTML/images | Same-project screen resources |
| Export for production | Download HTML, screenshots and referenced assets | Atomic files and SHA-256 manifest |
| Generate frontend code | React, React Native, shadcn/ui, Vue, Vant, Element Plus, Bootstrap, Layui, uView | Editable component source |
| Deliver with gates | Stitch → ImageGen → OCR → roundtrip → comparison → approval | Receipt chain and explicit human approval |

The plugin does not host Stitch or bundle a shared key. Ambiguous writes are reconciled with read operations before any retry.

## Package self-check against OpenAI guidance

| Official requirement | Current repository | Result |
|:---|:---|:---:|
| Stable plugin identity and metadata | `.codex-plugin/plugin.json`, `stitch-design`, publisher and URLs | Pass |
| Skills at the plugin root | `skills/` with 43 validated Skills | Pass |
| Bundled MCP configuration | `.mcp.json` compatibility mapping to the local stdio proxy | Pass for Codex compatibility |
| Visual install metadata | Logo, composer icon, default prompts and README screenshot | Pass |
| Marketplace policy metadata | Installation, `ON_USE` authentication and `Creativity` category | Pass |
| Portable Agent Plugins root manifest | Root `plugin.json` and portable `mcp.json` | Not yet migrated |
| Universal public Plugins Directory | Requires separate OpenAI submission and remote HTTPS MCP review | Not published |

This repository intentionally remains a Codex compatibility package while the portable/public migration gate is open. See [Portable migration gate](docs/portable-migration.md).

## Status and version

| Property | Value |
|:---|:---|
| Plugin ID | `stitch-design` |
| Current candidate | `0.7.2` |
| Current release | [v0.7.1](https://github.com/partme-ai/codex-stitch-plugin/releases/tag/v0.7.1) |
| Previous release | [v0.7.0](https://github.com/partme-ai/codex-stitch-plugin/releases/tag/v0.7.0) |
| Marketplace | `partme-ai-stitch` |
| Authentication | User-owned `STITCH_API_KEY`, requested on first use |
| License | Apache-2.0 |

## Example requests

```text
Read-only: List my Stitch projects and do not create anything.
Generate: Create a responsive product screen in Stitch.
Edit: Preserve the design system and only update the current screen.
Convert: Turn this Stitch screen into production React components.
```

Remote writes require the target project and intended scope. If a write times out, do not immediately repeat it; inspect the project/screen state first.

## Configuration

`.mcp.json` starts the bundled proxy from the installed plugin root:

```json
{
  "type": "stdio",
  "command": "python",
  "args": ["scripts/stitch_mcp_proxy.py"],
  "cwd": "."
}
```

Credential precedence:

1. `STITCH_API_KEY` in the current process.
2. The current-user Stitch Design credential file.
3. First-use setup.

Default locations are `$XDG_CONFIG_HOME/stitch-design/credentials.json` (or `~/.config/...`) on Unix and `%APPDATA%\stitch-design\credentials.json` on Windows.

Run a secret-free check:

```bash
python scripts/stitch_setup.py check
```

## Architecture and security

Codex owns plugin loading and approvals. Google Stitch owns remote design data and tool execution. Stitch Design owns workflow instructions, package validation, local credential bootstrap, and error recovery. The authors do not receive MCP traffic.

- [Architecture](docs/Stitch-Design-Architecture.md)
- [Technical solution](docs/Stitch-Design-Technical-Solution.md)
- [Portable migration gate](docs/portable-migration.md)
- [Privacy](PRIVACY.md)
- [Terms](TERMS.md)

## Development and verification

```bash
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
python scripts/validate_distribution.py .
python scripts/validate_skills.py skills
python scripts/validate_markdown_links.py .
python scripts/scan_secrets.py .
find scripts skills -type f -name '*.sh' -exec shellcheck {} +
python -m compileall -q scripts stitch_harness skills
git diff --check
```

Version 0.7.1 accepts `withgoogle.com` in the download allowlist, so artwork served from Stitch's own web domain can be downloaded; the boundary tests reject lookalike hosts and unsafe URLs. 0.7.0 fails closed when the Stitch provider ignores the requested device, so a desktop fallback can no longer be delivered as a tablet screen. Page specs require `canvas.device`, and the typed evidence writer requires the generated screen metadata, so existing spec files must add the field before they load. The 0.6.0 feature set is unchanged: 43 Skills, two namespaced local asset tools, typed Harness evidence writers, isolated comparison, explicit reconciliation/recovery, and recoverable archive publication.

Repository preparation for the provider + asset live smoke is complete: the manual-only workflow uses the `STITCH_API_KEY` repository secret, private runner state, sanitized output, and a final `always()` cleanup with read-back absence proof. It has not been run remotely and is not Harness acceptance. The full Harness remains an [interactive local controller path](docs/live-harness-controller.md). See the [live-smoke acceptance register](docs/live-canary-acceptance.md).

## Troubleshooting

| Symptom | Action |
|:---|:---|
| Stitch tools are missing | Confirm plugin status, restart Codex, open a new task |
| Credentials are missing | Open `stitch_setup.py ui` |
| Authentication fails | Replace the key, restart, run read-only `list_projects` |
| A write times out | Read project/screen state; do not blindly resubmit |
| ChatGPT web stalls | Treat the path as experimental; use local Codex |

## Upgrade

```bash
codex plugin marketplace upgrade partme-ai-stitch
codex plugin add stitch-design@partme-ai-stitch
```

## Source and license

The 39 upstream Skill snapshots are based on `full-stack-skills/stitch-skills` commit `62ef81825ad6ddc85bb6b8426e65b1a9d07d109b`; `stitch-local-setup`, `stitch-delivery-harness`, `stitch-delete-project`, and `stitch-design-use` are plugin-specific. Official adapted material traces to `google-labs-code/stitch-skills` commit `0337446dadde6f8c94210444e2aa9d546126480f`.

See [LICENSE](LICENSE), [NOTICE](NOTICE), and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
