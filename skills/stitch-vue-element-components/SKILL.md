---
name: stitch-vue-element-components
license: Apache-2.0
description: Convert Stitch designs into modular Vite/Vue 3 and Element Plus components. Uses Stitch MCP get_screen to retrieve design JSON and HTML; supports high-reliability fetch via scripts; enforces Vue SFC structure, data decoupling, and Element Plus component contracts.
---
# Stitch to Vue 3 + Element Plus Components

**Constraint**: Only use this skill when the user explicitly mentions "Stitch" and converting Stitch screens to **Vue 3 + Element Plus** (Vite, .vue SFC).

You are a **frontend engineer** turning Stitch designs into clean, modular Vue 3 + Element Plus code. Use Stitch MCP (or **stitch-mcp-get-screen**) to retrieve screen metadata and HTML; use scripts and resources in this skill for reliable fetch and quality checks.

## Prerequisites

- Stitch MCP Server (https://stitch.withgoogle.com/docs/mcp/guide/)
- Node.js and npm (for Vite/Vue 3 project)
- Stitch project and screen IDs — **two ways**: (1) From a **Stitch design URL**: parse **projectId** from path and **screenId** from `node-id` query (see **stitch-mcp-get-screen**). (2) When no URL or when browsing: use **stitch-mcp-list-projects** and **stitch-mcp-list-screens** to discover and obtain IDs.

## Official Documentation

- **Element Plus**: [Official (zh-CN)](https://element-plus.org/zh-CN/) · [Design Guide](https://element-plus.org/en-US/guide/design) · [Component Overview](https://element-plus.org/en-US/component/overview) · [GitHub](https://github.com/element-plus/element-plus)
- Full links and usage: [references/official.md](references/official.md)

## Retrieval and Networking

1. **Discover Stitch MCP prefix**: Run `list_tools` to find the prefix (e.g. `mcp_stitch__stitch:`).
2. **Resolve projectId and screenId**: (1) If the user provided a **Stitch design URL**, parse **projectId** from the path and **screenId** from the `node-id` query. (2) Otherwise, or when the user wants to choose a project/screen, call **list_projects** (e.g. filter `view=owned`) then **list_screens** with the chosen projectId to get screenIds.
3. **Fetch screen metadata**: Construct `name: projects/{project}/screens/{screen}` from the string ID segments and call `[prefix]:get_screen` to get design JSON, `htmlCode.downloadUrl`, `screenshot.downloadUrl`, dimensions, deviceType.
4. **High-reliability HTML download**: AI fetch tools can fail on Google Cloud Storage URLs. Use Bash to run the skill script:
   ```bash
   bash scripts/fetch-stitch.sh "<htmlCode.downloadUrl>" "temp/source.html"
   ```
   This uses `curl -L` for redirects and TLS. Ensure the URL is quoted.
5. **Visual reference**: Use `screenshot.downloadUrl` to confirm layout and details.

## Architectural Rules

- **Modular components**: Split the design into separate .vue files; avoid one giant SFC.
- **Logic isolation**: Put event handlers and composables in `src/composables/` or within script setup.
- **Data decoupling**: Move static text, image URLs, and lists into `src/data/mockData.js` (or .ts).
- **Element Plus only (use framework components when available)**: Use **el-card** for cards, **el-alert** for tips; do not use div.card or custom .card-header/.tips-text. Use `<el-*>` components per [references/contract.md](references/contract.md); do not use raw HTML for buttons, forms, layout when an Element component exists.
- **Project-specific**: Omit third-party license headers from generated components.

## Execution Steps

1. **Environment**: If the project has no `node_modules`, run `npm install`.
2. **Data layer**: Create `src/data/mockData.js` from the design content.
3. **Component drafting**: Use `resources/component-template.vue` as base; replace placeholder with real component name and Element Plus tags per contract.
4. **Wiring**: Update the app entry (e.g. `App.vue` or router) to render the new components.
5. **Quality check**: Verify against `resources/architecture-checklist.md`; run `npm run dev` to confirm visually.

## Integration with This Repo

- **Get screen**: Use **stitch-mcp-get-screen** (or MCP `get_screen`) with `name: projects/{project}/screens/{screen}`. Obtain the ID segments from a Stitch URL or the list Skills.
- **Design spec**: If Stitch was generated with **stitch-ui-design-spec-element-plus** constraints, map to Vue SFC and Element Plus components. If converting from Stitch HTML (e.g. get_screen htmlCode), use [references/tailwind-to-element-plus.md](references/tailwind-to-element-plus.md) for Tailwind utility → px/theme, then [references/contract.md](references/contract.md) for component API.
- **Design system**: If the project has DESIGN.md (from **stitch-design-md**), align colors and typography with that semantic system when mapping to Element tokens.

## Troubleshooting

- **Fetch errors**: Quote the URL in the bash command to avoid shell issues; ensure `scripts/fetch-stitch.sh` is executable.
- **Component mapping**: Follow [references/contract.md](references/contract.md) for layout (`el-row`/`el-col`), buttons (`el-button`), forms (`el-form`, `el-input`), etc.

## Keywords

**English:** Stitch, Vue 3, Element Plus, Vite, components, el-button, el-form.  
**中文关键词：** Stitch、Vue 3、Element Plus、组件、饿了么。

## References

- [Examples](examples/usage.md)
- [Scripts](scripts/fetch-stitch.sh)
- [Component index (per-component doc links)](references/component-index.md)
- [Tailwind → Element Plus](references/tailwind-to-element-plus.md) — Tailwind utility → px/theme when converting Stitch HTML.
- [Contract (Element Plus mapping)](references/contract.md)
- [Component API (props/events quick reference)](api/component-api.md)
- [Official documentation](references/official.md)
- [Architecture checklist](resources/architecture-checklist.md)
- [Component template](resources/component-template.vue)
- [Stitch API / MCP](https://stitch.withgoogle.com/docs/mcp/guide/)

<!-- QUALITY_BASELINE_V1 -->
## When to use（什么时候使用）

当用户需要 **为当前请求选择并执行可验证、可恢复的专业工作流** 时加载本技能。先从请求中提取目标、输入、约束、交付格式和验收标准；描述摘要为：Convert Stitch designs into modular Vite/Vue 3 and Element Plus components. Uses Stitch MCP get_screen to retrieve design JSON and HTML; supports high-reliability fetch via scripts; enforces Vue SFC structure, data decoupling, and Element Plus component contracts.。

## Rules

- 先读后写：先确认当前状态与真实能力，再执行会改变外部状态的动作。
- 权限最小化：只使用完成当前步骤所需的文件、工具、账户与网络范围。
- 证据优先：运行结果、资源 ID、版本、哈希或测试输出缺失时，明确标记为 `NOT_VERIFIED`。
- 幂等优先：保留请求标识与阶段状态；结果不明确时先查询，不进行盲目重试。
- 隐私安全：日志、示例、回执和错误信息不得包含 token、cookie、密钥或个人敏感数据。

## Workflow

### Step 1：澄清意图

确认本技能是否匹配目标；若只是相邻需求，交给更精确的技能。
### Step 2：执行预检

确认目标、输入、约束、可用工具、成功标准和失败边界；任一关键条件未知时停止在只读阶段。
### Step 3：形成计划

列出将调用的工具、会改变的对象、成功标准以及失败后的安全退出方式。
### Step 4：执行动作

按最小充分步骤执行，并在关键状态变化处记录证据；每个外部调用均保留可关联的状态或回执。
### Step 5：验证交付

输出结果、验证证据、未完成项、风险和明确的下一步，并把事实、推断和未验证项分开陈述。

## Validation checklist

- [ ] 技能触发条件与用户意图一致，没有把相邻任务误路由到本技能。
- [ ] 输入、目标对象、版本和输出位置均已明确，且没有使用猜测值替代必填值。
- [ ] 所有写入、付费、发布或不可逆动作都在用户授权范围内。
- [ ] 结果已用独立检查验证；仅有“命令成功”或“文件存在”不算完整验收。
- [ ] 输出包含实际证据、失败/跳过项、剩余风险和可执行的下一步。

## Gotchas

1. **把计划当结果**：文档或提示词不等于真实执行；必须标明实际运行层级。
2. **错误重试**：超时或响应丢失可能已经产生远端状态，先查询再决定是否重试。
3. **隐式扩大范围**：批量、全量、发布、覆盖和付费不是普通读写的自然延伸。
4. **版本漂移**：引用外部资源时记录版本、tag 或提交；不要把可变分支当发布证据。
5. **证据过期**：缓存、旧截图和历史测试不能证明当前环境；在交付前刷新关键证据。

## 不适用与边界

不超出用户给定范围；写入、付费、发布和不可逆动作需要明确授权。 如果请求需要别的技能，不复制其正文；按技能名称进行交接，并保留当前任务上下文。

## Progressive disclosure

- 需要确定输入/输出、状态和授权点时，读取 `references/workflow-contract.md`。
- 需要交付前自检时，读取 `references/validation-checklist.md`。
- 遇到超时、部分成功或恢复场景时，读取 `references/error-recovery.md`。
- 首次运行、拒绝越权和失败恢复分别参考 `examples/happy-path.md`、`examples/boundary-refusal.md`、`examples/failure-recovery.md`。
