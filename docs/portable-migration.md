# Portable Agent Plugin migration

## Current status

This repository intentionally remains on the supported Codex compatibility layout:

```text
.codex-plugin/plugin.json
.mcp.json
skills/
```

It does not activate root `plugin.json` or `mcp.json` files yet. Adding only a portable manifest would change component discovery and could disable the working Stitch authentication path.

## Authentication blocker

Agent Plugins 1.0 states that clients **MUST NOT perform placeholder or environment-variable expansion in `url`, header names, or header values**. Header values are visible package data, and the portable format has no OAuth or credential-reference field.

The current Codex compatibility configuration safely maps `X-Goog-Api-Key` to the local environment variable name `STITCH_API_KEY` through `env_http_headers`. That client-specific mechanism cannot be copied into portable `mcp.json`.

## Migration gate

Activate root `plugin.json` and `mcp.json` only after one of these paths is verified end to end:

1. Register the Stitch MCP connection in ChatGPT Developer Mode and obtain its `plugin_asdk_app...` technical ID, then map it through `.app.json` and `extensions.com.openai.apps`.
2. Adopt a client-managed Stitch OAuth flow that requires no credential in portable package headers.
3. Adopt a future Agent Plugins schema that defines a portable credential reference.

Before migration, test ChatGPT and Codex separately: installation, skill discovery, MCP provenance, authentication failure, read-only `list_projects`, and revocation. Keep the compatibility files until older supported clients no longer require them.

## References

- [OpenAI: Package your plugin](https://developers.openai.com/plugins/build/plugins)
- [Agent Plugins 1.0 specification](https://agent-plugins.org/specification)
- [Google Stitch MCP setup](https://stitch.withgoogle.com/docs/mcp/setup/)
