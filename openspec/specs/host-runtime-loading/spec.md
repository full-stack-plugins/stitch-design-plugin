# host-runtime-loading Specification

## Purpose
Define how each supported host launches the plugin with portable, repository-owned runtime commands and validated dependencies.
## Requirements
### Requirement: Stitch MCP uses a consistent Python launcher

The plugin SHALL launch its Python MCP proxy with `python3` on Codex, ZCode, and Kimi and SHALL NOT bind an absolute interpreter path.

#### Scenario: Load the Codex MCP

- **WHEN** the host reads `.mcp.json`
- **THEN** the command is `python3`
