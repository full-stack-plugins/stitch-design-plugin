## Why

Codex 的 Stitch MCP 使用 `python`，而同一插件的 ZCode/Kimi 使用 `python3`；在默认不提供 `python` 别名的环境中 Codex 无法启动代理。

## What Changes

- Codex MCP 改为 PATH 上的 `python3`。
- 更新分发验证与回归测试。

## Capabilities

### New Capabilities

- `host-runtime-loading`: 三种宿主使用可移植且一致的 Python 启动契约。

### Modified Capabilities

None.

## Impact

影响 Stitch MCP 启动配置、验证器和测试。
