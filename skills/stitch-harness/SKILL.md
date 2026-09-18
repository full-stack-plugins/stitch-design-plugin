---
name: stitch-harness
description: "Stitch calling spec: the local stdio MCP proxy (Python 3.11+ hard requirement), credential setup via stitch-local-setup, remote Stitch MCP auth, and the 43-skill routing surface. Read this before any Stitch task."
---

# Stitch 调用规范

执行通道：本地 stdio MCP 代理 `scripts/stitch_mcp_proxy.py` → 远程 Stitch MCP
（`stitch-design` 技能含工具面）。**Python 3.11+ 硬要求**——低于此版本代理拒绝启动。

## 1. 凭据与环境

- 首次使用经 `stitch-local-setup` / `stitch-mcp-*` 技能完成 OAuth/登录配置。
- 凭据由代理托管，不进环境变量与日志。

## 2. 硬规则（来自上游验证记录）

- 代理脚本路径解析基于 `__file__`，从任何 cwd 启动均可；不要复制脚本到别处运行。
- 无 Playwright/浏览器兜底——Stitch 的浏览器能力由远端 MCP 提供。

## 3. 标准工作流

1. `probe` 确认代理与凭据就绪。
2. 生成/编辑走 `stitch-ui-designer`；设计↔代码走 `stitch-code-to-design` /
   `stitch-extract-static-html`；设计系统走 `stitch-manage-design-system`。
3. 交付：产物链接/导出文件 + 所用工具 + 未验证项。

## 4. 纪律

- 付费动作（生成配额）一次性提交；失败原文上报。
- 43 个技能的路由入口是 `stitch-design-use`；不要凭记忆猜技能名。
