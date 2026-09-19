---
name: stitch-uview-plus-components
license: Apache-2.0
description: "Convert Stitch designs into uni-app + Vue 3 + uview-plus pages and components. Use when the user mentions Stitch, uview-plus, up- components, or uni-app Vue 3 conversion targeting uview-plus. Retrieves screen HTML via Stitch MCP get_screen, rewrites Tailwind structure into up-* components, and enforces stronger setup, theme, safe-area, tabbar, popup, upload, and dark-mode rules than the generic uView Pro conversion skill."
---
# Stitch to uni-app + uview-plus Components

**Constraint**: Only use this skill when the user explicitly mentions **Stitch** and wants conversion to **uni-app + Vue 3 + uview-plus** with **`up-*`** components.

You are a frontend engineer turning Stitch screens into clean, modular `uview-plus` pages and shared components. Use Stitch MCP (or **stitch-mcp-get-screen**) to retrieve metadata and HTML, then rebuild the screen with `up-*` components, `rpx`, and the current `uview-plus` theme/runtime model.

## What makes this skill different

This is not a rename of `stitch-uviewpro-components`.

It is a stronger `uview-plus`-specific skill that:
- defaults to **`up-*`** instead of `u-*`
- aligns with current `uview-plus` docs, setup, and theme guidance
- covers **`up-status-bar`**, **`up-safe-bottom`**, **`up-popup`**, **`up-upload`**, **`up-subsection`**, **`up-tabbar`**, **`up-empty`**, **`up-gap`**, and **`up-line`**
- prefers CSS variables like **`--up-*`** and runtime theme config over hardcoded colors
- requires stronger page-shell, safe-area, and bottom-CTA handling than the generic uView Pro skill

## Prerequisites

- Stitch MCP Server: https://stitch.withgoogle.com/docs/mcp/guide/
- `uni-app` / HBuilderX or Vue CLI project using **Vue 3**
- `uview-plus` installed and wired for Vue 3
- Stitch project and screen IDs, resolved in one of two ways:
  1. Parse a **Stitch design URL**: `projectId` from the `/projects/{id}` path and `screenId` from the `node-id` query
  2. Browse with **stitch-mcp-list-projects** and **stitch-mcp-list-screens**

## Official Documentation

- **uview-plus docs**: https://uview-plus.jiangruyi.com/
- **Quick start**: https://uview-plus.jiangruyi.com/components/quickstart.html
- **Install / setup**: https://uview-plus.jiangruyi.com/components/setting.html
- **Setup rationale**: https://uview-plus.jiangruyi.com/components/settingDesc.html
- **Theme**: https://uview-plus.jiangruyi.com/guide/theme.html
- **Dark mode**: https://uview-plus.jiangruyi.com/guide/darkMode.html
- **Root bridge**: https://uview-plus.jiangruyi.com/guide/root.html
- Full links and key component docs: [references/official.md](references/official.md)

## Retrieval and Networking

1. **Discover Stitch MCP prefix**: inspect tools to find the Stitch namespace.
2. **Resolve projectId and screenId**:
   - If the user supplied a Stitch URL, parse both IDs directly
   - Otherwise use **stitch-mcp-list-projects** and **stitch-mcp-list-screens**
3. **Fetch screen metadata**: call **get_screen** to obtain design JSON, `htmlCode.downloadUrl`, `screenshot.downloadUrl`, dimensions, and device type.
4. **Download HTML reliably**:
   ```bash
   bash scripts/fetch-stitch.sh "<htmlCode.downloadUrl>" "temp/source.html"
   ```
5. **Use the screenshot as the visual source of truth** when the exported HTML is structurally noisy.

## Architectural Rules

- **Use `up-*` only** when a `uview-plus` component exists. Do not generate `u-*` tags in this skill.
- **Prefer modular output**: page shell, shared components, and extracted mock/static data instead of one large page file.
- **Prefer framework-native rebuilds** over literal HTML translation. Reconstruct the page with `up-*` semantics.
- **Prefer theme-aware styles**: use `var(--up-xxx)` and `setConfig({ color })` guidance instead of hardcoded colors when a theme token exists.
- **Prefer runtime-safe page shells**:
  - `up-navbar` for normal headers
  - `up-status-bar` for custom branded headers
  - `up-safe-bottom` for fixed bottom CTAs
- **Read these before drafting code**:
  - [references/component-index.md](references/component-index.md)
  - [references/contract.md](references/contract.md)
  - [references/stitch-html-patterns.md](references/stitch-html-patterns.md)
  - [references/tailwind-to-uview-plus.md](references/tailwind-to-uview-plus.md)

## Execution Steps

1. **Environment**
   - ensure `uview-plus` is installed
   - ensure Vue 3 project wiring is valid
   - ensure `App.vue`, `main.js`, and `uni.scss` follow current `uview-plus` guidance
2. **Data layer**
   - extract repeated text, options, tabs, and upload/demo lists into data modules or page state
3. **Page drafting**
   - start from [resources/page-template.vue](resources/page-template.vue)
   - keep the page shell theme-aware and safe-area-aware
4. **Component selection**
   - use `up-tabs` or `up-subsection` for switching UI
   - use `up-picker` / `up-popup` instead of raw `select`
   - use `up-upload` instead of raw upload boxes
   - use `up-tabbar` for bottom nav
   - use `up-empty` for empty states
5. **Quality check**
   - verify against [resources/architecture-checklist.md](resources/architecture-checklist.md)
   - make sure the final output is clearly stronger and more framework-native than a raw HTML rewrite

## Official API alignment and common Stitch corrections

When converting Stitch HTML, verify against [references/contract.md](references/contract.md) and the official `uview-plus` docs. Common corrections:

| Design element | Wrong from Stitch / generic UI | Correct for uview-plus |
|---|---|---|
| Top tabs | custom `<view>` pills or button row | **`<up-tabs :list="..." :current="current" @change="...">`** or `v-model:current` |
| Segmented filters | custom capsule buttons | **`<up-subsection :list="..." :current="..." @change="...">`** |
| Picker/select | native `<select>` or raw popup list | **`<up-picker v-model:show="show" :columns="columns" @confirm="...">`** |
| Popup/sheet | fixed custom overlay + absolute panel | **`<up-popup v-model:show="show" mode="bottom">`** |
| Upload | dashed custom upload box + hidden file input | **`<up-upload :fileList="..." @afterRead="...">`** |
| Bottom navigation | fixed footer buttons manually styled as nav | **`<up-tabbar :value="value" @change="...">`** |
| Empty state | plain text "No data" | **`<up-empty text="No data">`** |
| Divider / spacing | manual border and margin blocks | **`<up-line>`**, **`<up-divider>`**, **`<up-gap>`** |
| Safe area | fixed bottom CTA without inset handling | **`<up-safe-bottom>`** wrapper |
| Custom header | hardcoded spacer height | **`<up-status-bar>`** when not using `up-navbar` |
| Theme | hex colors everywhere | `var(--up-*)`, theme tokens, and runtime color config |

## Engineering guidance specific to uview-plus

- `uview-plus` current docs favor **`up-*`** naming in examples. This skill should output that convention by default.
- For `.vue` / `.uvue` pages, prefer CSS variables such as `var(--up-primary)` and `var(--up-bg-color)`.
- For runtime theme customization, use `setConfig({ color })` guidance when the page needs explicit theme sync.
- Keep `@import 'uview-plus/theme.scss';` semantics in mind when describing project wiring.
- If the project uses the **Root bridge**, global calls like `uni.$u.toast()` can replace manually placing `up-toast` in every page.

## Testing trigger

Testing is command-triggered by the user, not by directly calling MCP for no reason.

- **Example test command**:
  ```text
  Use the Stitch skill to convert https://stitch.withgoogle.com/projects/3492931393329678076?node-id=375b1aadc9cb45209bee8ad4f69af450 into a uview-plus page
  ```
- **Expected result**:
  - parse `projectId` and `screenId`
  - call Stitch MCP `get_screen`
  - fetch the HTML
  - output a `uni-app + Vue 3 + uview-plus` page using `up-*` components, safe-area-aware structure, and current theme guidance

## Keywords

**English:** Stitch, uview-plus, up-button, up-tabs, up-tabbar, up-popup, up-upload, uni-app, Vue 3.  
**中文关键词：** Stitch、uview-plus、up 组件、uni-app、Vue3、页面转换。

## References

- [examples/usage.md](examples/usage.md)
- [references/official.md](references/official.md)
- [references/contract.md](references/contract.md)
- [references/component-index.md](references/component-index.md)
- [references/stitch-html-patterns.md](references/stitch-html-patterns.md)
- [references/tailwind-to-uview-plus.md](references/tailwind-to-uview-plus.md)
- [resources/architecture-checklist.md](resources/architecture-checklist.md)
- [resources/page-template.vue](resources/page-template.vue)
- [api/component-api.md](api/component-api.md)
- [scripts/fetch-stitch.sh](scripts/fetch-stitch.sh)
- [Stitch API / MCP](https://stitch.withgoogle.com/docs/mcp/guide/)

<!-- QUALITY_BASELINE_V1 -->
## When to use（什么时候使用）

当用户需要 **为当前请求选择并执行可验证、可恢复的专业工作流** 时加载本技能。先从请求中提取目标、输入、约束、交付格式和验收标准；描述摘要为："Convert Stitch designs into uni-app + Vue 3 + uview-plus pages and components. Use when the user mentions Stitch, uview-plus, up- components, or uni-app Vue 3 conversion targeting uview-plus. Retrieves screen HTML via Stitch MCP get_screen, rewrites Tailwind structure into up-* components, and enforces stronger setup, theme, safe-area, tabbar, popup, upload, and dark-mode rules than the generic uView Pro conversion skill."。

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
