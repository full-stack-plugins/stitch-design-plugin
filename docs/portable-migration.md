# Portable Agent Plugin migration

**Status: migrated to Agent Plugins v1.0.0** (2026-09-28).

## What ships now

| File | Role |
|------|------|
| `plugin.json` | Canonical portable manifest (published `agent-plugins.org` 1.0.0 schema) |
| `mcp.json` | Portable MCP configuration (local stdio proxy) |
| `.codex-plugin/plugin.json` | Codex compatibility manifest, unchanged |
| `.zcode-plugin/plugin.json` | ZCode compatibility manifest, unchanged |
| `kimi.plugin.json` | Kimi compatibility manifest, unchanged |
| `.mcp.json` | Claude Code compatibility MCP config, unchanged |

Before this, the package shipped only per-client manifests. None of those is
part of the Agent Plugins format, so a conformant client rejected the package
outright and never reached the 45 skills inside it — a missing root manifest is
fatal, not a warning (§5.1, §5.3).

## Correction to the previous version of this document

This file previously stated that the package could not adopt a portable
`mcp.json`, because the specification says that clients
MUST NOT perform placeholder or environment-variable expansion in `url`, header
names, or header values, and because `X-Goog-Api-Key` maps to `STITCH_API_KEY`
only through `env_http_headers`.

That reasoning conflated two different things, and its conclusion was too broad:

- The credential concern is real, but it attaches to a **remote** Stitch MCP
  endpoint declared as an `streamable-http` or `sse` server carrying an
  `X-Goog-Api-Key` header. A portable format has neither header expansion nor a
  portable credential field (§7.2.1), so *that* configuration still cannot be
  expressed portably. This has not changed.
- The MCP configuration this package actually ships is **not** that remote
  endpoint. `.mcp.json` declares a single **stdio** server running
  `scripts/stitch_mcp_proxy.py`, a local Python process. It declares no `url`,
  no `headers`, and no credential of any kind.

The proxy resolves the Stitch credential itself, in application code, through
`stitch_harness/secrets.py` (`platform_secret_provider`). Nothing sensitive is
present in the package manifest, so there is nothing for §7.2.1's "configured
headers are visible package data" rule to prohibit.

The portable `mcp.json` is therefore a faithful, credential-free representation:

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "stitch": {
      "type": "stdio",
      "command": "python3",
      "args": ["./scripts/stitch_mcp_proxy.py"],
      "cwd": "./"
    }
  }
}
```

`.mcp.json` is left in place and unchanged, so clients that already load it keep
their current behaviour. Agent Plugins reads only `mcp.json` (§7.2.1), which is
why the dotted file alone left this server invisible to a conformant client.

## What remains blocked

The three gates below are **still open**. None of them blocks what shipped
above — they gate a *future* direct remote connection, not the current local
proxy:

1. Register the Stitch MCP connection in ChatGPT Developer Mode and obtain its
   `plugin_asdk_app...` technical ID, then map it through `.app.json` and
   `extensions.com.openai.apps`.
2. Adopt a client-managed Stitch OAuth flow that requires no credential in
   portable package headers.
3. Adopt a future Agent Plugins schema that defines a portable credential
   reference.

Until one of these is verified end to end, do not add a remote `streamable-http`
Stitch server to `mcp.json`. Doing so would require putting a credential in a
header, which §7.2.1 forbids in the portable format.

## Client coverage

`skills/` and `mcp.json` are the portable component types, so **every client in
the [Agent Plugins registry](https://agent-plugins.org/compatible-clients) loads
this package with no client-specific work**: VS Code, Cursor, GitHub Copilot,
ChatGPT & Codex, Kiro, Hermes Agent, OpenClaw, Grok Bot, NanoClaw and OpenHands.

Commands, agents and hooks are explicitly *not* portable, so a client reads them
from the extension directory it owns (§8.2). This package mirrors accordingly:

- `com.github.copilot/` — `hooks/` for VS Code and GitHub Copilot (they share
  this namespace)
- `dev.openhands/` — `commands/`, `hooks/` for OpenHands
- `extensions["com.openai"]` — manifest data for ChatGPT & Codex

The root `commands/` and `hooks/` directories are kept unchanged, so the Codex,
ZCode and Kimi channels keep working. `scripts/validate_portable_plugin.py`
fails if a mirror drifts from its root copy.

> **OpenClaw precedence.** OpenClaw checks for a client-specific bundle marker
> (`.codex-plugin/`) before a root `plugin.json`, and treats the client-specific
> format as winning so its richer mappings survive. This package ships both, so
> OpenClaw loads it as a Codex bundle — which keeps its commands and hooks
> working — rather than as an Agent Plugins bundle. Removing `.codex-plugin/`
> would change that and break the Codex channel, so it stays.

## Layout rules honoured

- `plugin.json`, `mcp.json` and `skills/` all live at the package root.
- The portable manifest declares **only** published-schema fields. The schema is
  closed (`additionalProperties: false`), so it deliberately omits `skills` and
  `mcpServers`:
  - `skills/` is a fixed discovery location and MUST NOT be declared (§6.1).
  - MCP is discovered from `mcp.json` and MUST NOT be declared inline (§7.2.1).
- Client-owned data — the `interface` block — lives under
  `extensions["com.openai"]["interface"]`, a reverse-domain client extension
  namespace (§8).
- `name` is `stitch-design`, satisfying §5.5.
- `version` is the **base** version `0.8.6`. The `+codex.<stamp>` build metadata
  in `.codex-plugin/plugin.json` describes that compatibility channel's build,
  not the portable plugin, so it stays there.

## Verifying

The check is machine-runnable and needs no network access or third-party
package:

```bash
python3 scripts/validate_portable_plugin.py
```

## References

- [Agent Plugins specification](https://agent-plugins.org/specification)
- [Plugin manifest schema](https://agent-plugins.org/schemas/1.0.0/plugin.schema.json)
- [MCP configuration schema](https://agent-plugins.org/schemas/1.0.0/mcp.schema.json)
- [Google Stitch MCP setup](https://stitch.withgoogle.com/docs/mcp/setup/)
