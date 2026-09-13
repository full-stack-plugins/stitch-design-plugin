# Stitch Design for Codex

> 通过 43 个面向工作流的 Agent Skills 和证据驱动 Harness，在 Codex 中设计、验证、美术增强并交付可编辑的 Google Stitch 项目。

[English](README.md) | [简体中文](README.zh-CN.md) · [架构文档](docs/Stitch-Design-Architecture.zh_CN.md) · [技术方案](docs/Stitch-Design-Technical-Solution.zh_CN.md) · [0.6.0 Canary 验收](docs/live-canary-acceptance.zh_CN.md)

## 项目状态

| 属性 | 值 |
|:---|:---|
| 插件 ID | `stitch-design` |
| 本地候选版本 | `0.6.0` — 尚未发布 |
| 已发布基线 | [v0.5.4](https://github.com/partme-ai/codex-stitch-plugin/releases/tag/v0.5.4) |
| 宿主布局 | Codex compatibility plugin |
| Skills | 43 |
| MCP Endpoint | `https://stitch.googleapis.com/mcp` |
| 认证 | 用户自有 `STITCH_API_KEY`，首次使用时配置 |
| 许可证 | Apache-2.0 |

```text
Codex
  │ 用户请求
  ▼
Stitch Design
  ├─ 43 个 Skills：路由、安全、设计、转换、交付
  ├─ Delivery Harness：契约 → 门禁 → receipts → 批准
  ├─ 本地设置页：获取 Key → 用户受限配置
  └─ 内置 stdio 代理 → Google Stitch HTTPS MCP
                         │
                         ▼
                 Google Stitch MCP
```

## 提供的能力

- 创建、检查、编辑 Stitch 屏幕并生成变体。
- 管理设计系统和 DESIGN.md 工作流。
- 把本地 HTML/图片导入已授权的 Stitch 项目。
- 转换为 React、React Native、shadcn/ui、Vue、Vant、Element Plus、Bootstrap、Layui、uView、uView Pro 和 uview-plus。
- 生成站点规格、提示词、视觉规范和 Remotion 演示。
- 写操作结果不明时先读取远端状态，再决定是否恢复。
- 执行 Stitch → ImageGen → OCR/业务 → 回灌 → 对比 → 批准的门禁闭环。

插件不托管 Stitch、不内置共享 Key，也不把 ChatGPT 网页认证描述为生产可用。

## 安装

```bash
codex plugin marketplace add partme-ai/codex-stitch-plugin --ref main
codex plugin add stitch-design@partme-ai-stitch
```

安装或升级后重启 Codex，并新建任务。

## 第一次使用

插件已经内置 MCP URL。首次本地 Stitch 请求会由 `stitch-local-setup` 检查凭据；缺少时打开本地三步页面：

1. 打开 Stitch Settings 创建 API Key。
2. 在本地密码输入框粘贴并保存。
3. 打开新 Codex 进程并执行只读项目检查。

手动启动：

```bash
# macOS / Linux
python /已安装插件路径/scripts/stitch_setup.py ui

# Windows
python C:\已安装插件路径\scripts\stitch_setup.py ui
```

页面只监听 `127.0.0.1`，不加载外部资产，校验 CSRF 和 Origin，不记录 Key，并在每次响应后清空输入。所有平台默认保存到当前用户的受限配置文件。详见 [使用指南](docs/getting-started.zh-CN.md) 与 [隐私说明](PRIVACY.md)。

所有支持的宿主上，PATH 中的 `python` 命令必须解析为 Python 3.11 或更高版本。插件 MCP 与 Windows 设置说明有意使用同一个命令。

## 使用示例

```text
只读：列出我的 Stitch 项目，不要创建任何内容。
生成：在 Stitch 中创建响应式产品页面。
编辑：保留设计系统，只修改当前屏幕。
转换：把这个 Stitch 屏幕转换为生产级 React 组件。
```

远程写操作需要明确目标项目与范围。写操作超时后不要立即重发，应先检查项目或屏幕状态。

## 配置

`.mcp.json` 从安装后的插件根目录启动内置 stdio 代理。凭据优先级为：

1. 当前进程中的 `STITCH_API_KEY`。
2. 当前用户的 Stitch Design 凭据文件。
3. 首次设置页面。

Unix 默认位置是 `$XDG_CONFIG_HOME/stitch-design/credentials.json`（未设置时为 `~/.config/...`），Windows 为 `%APPDATA%\stitch-design\credentials.json`。

只检查状态、不回显 Key：

```bash
python scripts/stitch_setup.py check
```

## 架构与安全

Codex 负责插件加载和审批；Google Stitch 负责远程设计数据和工具执行；Stitch Design 负责工作流指令、包验证、本地凭据引导与失败恢复。插件作者不接收 MCP 流量。

- [架构文档](docs/Stitch-Design-Architecture.zh_CN.md)
- [技术方案](docs/Stitch-Design-Technical-Solution.zh_CN.md)
- [Portable 迁移门禁](docs/portable-migration.md)
- [隐私说明](PRIVACY.md)
- [使用条款](TERMS.md)

## 开发与验证

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

本地 0.6.0 候选包含 43 个 Skills、两个带命名空间的本地资产工具、类型化 Harness evidence writer、隔离图片比较、显式对账/恢复状态和可恢复归档发布。正式发布、Marketplace 安装、真实 Canary 与安装宿主证据仍属于 Task 6 门禁；v0.5.4 是已发布基线。

受控 Canary 的仓库准备已完成：仅手动触发的 workflow 使用 `STITCH_API_KEY` Repository Secret、runner 私有状态、脱敏输出，并在最后一个 `always()` 步骤删除远端项目后只读确认不存在。该 workflow 尚未远端实跑，详见 [真实 Canary 验收台账](docs/live-canary-acceptance.zh_CN.md)。

## 故障排查

| 现象 | 处理 |
|:---|:---|
| 找不到 Stitch 工具 | 检查插件状态，重启 Codex，新建任务 |
| 缺少凭据 | 打开 `stitch_setup.py ui` |
| 认证失败 | 更换 Key，重启并只读调用 `list_projects` |
| 写操作超时 | 读取项目/屏幕状态，不盲目重发 |
| ChatGPT 网页停滞 | 保持实验性，使用本地 Codex |

## 升级

```bash
codex plugin marketplace upgrade partme-ai-stitch
codex plugin add stitch-design@partme-ai-stitch
```

## 来源与许可

39 个上游 Skill 快照基于 `full-stack-skills/stitch-skills` 提交 `62ef81825ad6ddc85bb6b8426e65b1a9d07d109b`；`stitch-local-setup`、`stitch-delivery-harness`、`stitch-delete-project` 和 `stitch-design-use` 为插件本地 Skill。官方适配内容可追溯到 `google-labs-code/stitch-skills` 提交 `0337446dadde6f8c94210444e2aa9d546126480f`。

详见 [LICENSE](LICENSE)、[NOTICE](NOTICE) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
