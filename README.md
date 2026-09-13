# Stitch Design for Codex

> Design, verify, art-direct, and deliver editable Google Stitch projects from Codex through 41 workflow-focused Agent Skills and an evidence-driven Harness.

[English](README.md) | [简体中文](README.zh-CN.md) · [Architecture](docs/Stitch-Design-Architecture.md) · [Technical solution](docs/Stitch-Design-Technical-Solution.md)

## Project status

| Property | Value |
|:---|:---|
| Plugin ID | `stitch-design` |
| Release | [v0.4.0](https://github.com/partme-ai/codex-stitch-plugin/releases/tag/v0.4.0) |
| Local candidate | `0.5.0` (not yet published) |
| Host layout | Codex compatibility plugin |
| Skills | 41 |
| MCP endpoint | `https://stitch.googleapis.com/mcp` |
| Authentication | User-owned `STITCH_API_KEY`, requested on first use |
| License | Apache-2.0 |

```text
Codex
  │ user request
  ▼
Stitch Design
  ├─ 41 Skills: routing, safety, design, conversion, delivery
  ├─ Delivery Harness: contracts → gates → receipts → approval
  ├─ local setup UI: get key → system secret store
  └─ bundled stdio proxy → Google Stitch HTTPS MCP
                         │
                         ▼
                 Google Stitch MCP
```

## What it provides

- Create, inspect, edit, and generate variants of Stitch screens.
- Manage design systems and DESIGN.md-based workflows.
- Import local HTML/images into authorized Stitch projects.
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
python3 /path/to/installed/plugin/scripts/stitch_setup.py ui

# Windows
py C:\path\to\installed\plugin\scripts\stitch_setup.py ui
```

The page binds only to `127.0.0.1`, loads no external assets, uses CSRF and Origin checks, never logs the key, and clears the input after every response. It stores the key in macOS Keychain, Windows Credential Manager, or Linux Secret Service. See [Getting started](docs/getting-started.zh-CN.md) and [Privacy](PRIVACY.md).

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
  "command": "python3",
  "args": ["scripts/stitch_mcp_proxy.py"],
  "cwd": "."
}
```

Credential precedence:

1. `STITCH_API_KEY` in the current process.
2. The native system secret store.
3. First-use setup.

Legacy JSON credentials require the explicit `stitch_setup.py migrate` command and are scrubbed only after the system store is verified.

Run a secret-free check:

```bash
python3 scripts/stitch_setup.py check
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
python3 -m unittest discover -s tests -v
python3 scripts/validate_distribution.py .
shellcheck scripts/stitch_setup.sh
git diff --check
```

Published 0.4.0 evidence remains historical. The local 0.5.0 candidate adds 41 Skills, a stdio proxy and Harness; its offline and current-host evidence must not be confused with a push, release, Marketplace upgrade, or cross-platform validation.

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

The 39 upstream Skill snapshots are based on `full-stack-skills/stitch-skills` commit `62ef81825ad6ddc85bb6b8426e65b1a9d07d109b`; `stitch-local-setup` and `stitch-delivery-harness` are plugin-specific. Official adapted material traces to `google-labs-code/stitch-skills` commit `0337446dadde6f8c94210444e2aa9d546126480f`.

See [LICENSE](LICENSE), [NOTICE](NOTICE), and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
