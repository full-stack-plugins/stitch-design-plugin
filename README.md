# Stitch Design for Codex

> Design, verify, art-direct, and deliver editable Google Stitch projects from Codex through 43 workflow-oriented Agent Skills and an evidence-driven Harness.

[English](README.md) | [简体中文](README.zh-CN.md) · [Architecture](docs/Stitch-Design-Architecture.md) · [Technical solution](docs/Stitch-Design-Technical-Solution.md) · [0.6.0 live-smoke acceptance](docs/live-canary-acceptance.md)

## Project status

| Property | Value |
|:---|:---|
| Plugin ID | `stitch-design` |
| Candidate | `0.6.0` — local, not yet published |
| Released baseline | [v0.5.4](https://github.com/partme-ai/codex-stitch-plugin/releases/tag/v0.5.4) |
| Host layout | Codex compatibility plugin |
| Skills | 43 |
| MCP endpoint | `https://stitch.googleapis.com/mcp` |
| Authentication | User-owned `STITCH_API_KEY`, requested on first use |
| License | Apache-2.0 |

```text
Codex
  │ user request
  ▼
Stitch Design
  ├─ 43 Skills: routing, safety, design, conversion, delivery
  ├─ Delivery Harness: contracts → gates → receipts → approval
  ├─ local asset tools: safe upload → verified atomic export
  ├─ local setup UI: get key → user configuration
  └─ bundled stdio proxy → Google Stitch HTTPS MCP
                         │
                         ▼
                 Google Stitch MCP
```

## What it provides

- Create, inspect, edit, and generate variants of Stitch screens.
- Manage design systems and DESIGN.md-based workflows.
- Import local HTML/images into authorized Stitch projects.
- Export HTML, screenshots, available DESIGN.md, and referenced assets with hashes through `stitch_local_download_assets`.
- Convert Stitch outputs to React, React Native, shadcn/ui, Vue, Vant, Element Plus, Bootstrap, Layui, uView, uView Pro, and uview-plus.
- Generate site specifications, prompt architecture, visual guidance, and Remotion walkthroughs.
- Recover safely from ambiguous remote writes by reading state before any retry.
- Run a gated Stitch → ImageGen → OCR/business → roundtrip → comparison → approval workflow.

The plugin does not host Stitch, bundle a shared API key, or make ChatGPT web authentication production-ready.

## Install

```bash
codex plugin marketplace add partme-ai/codex-stitch-plugin --ref main
codex plugin add stitch-design@partme-ai-stitch
```

Restart Codex and open a new task after installing or upgrading.

## First use

The plugin already contains its MCP URL. On the first local Stitch request, `stitch-local-setup` checks for credentials. If none are available, it opens a local three-step page:

1. Open Stitch Settings and create an API key.
2. Paste the key into the masked local input and save.
3. Open a new Codex process and run a read-only project check.

Manual launch:

```bash
# macOS / Linux
python /path/to/installed/plugin/scripts/stitch_setup.py ui

# Windows
python C:\path\to\installed\plugin\scripts\stitch_setup.py ui
```

The page binds only to `127.0.0.1`, loads no external assets, uses CSRF and Origin checks, never logs the key, and clears the input after every response. It stores the key in a restricted current-user configuration file on every supported platform. See [Getting started](docs/getting-started.zh-CN.md) and [Privacy](PRIVACY.md).

The `python` command on PATH must resolve to Python 3.11 or newer on every supported host. The plugin MCP and Windows setup instructions intentionally use that same command.

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

The local 0.6.0 candidate contains 43 Skills, two namespaced local asset tools, typed Harness evidence writers, isolated comparison, explicit reconciliation/recovery, and recoverable archive publication. Release, Marketplace installation, live canary, and installed-host evidence remain separate Task 6 gates; v0.5.4 is the published baseline.

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
