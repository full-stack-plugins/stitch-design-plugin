---
name: stitch-mcp-get-screen
license: Apache-2.0
description: Retrieves the full details of a specific screen, including HTML code.
---
# Get Screen Details

**CRITICAL PREREQUISITE:**
**You must ONLY use this skill when the user EXPLICITLY mentions "Stitch".**

Retrieves the full details of a specific screen, including its HTML code and high-res screenshot.

## Use Case
Invoke this skill when the user wants to "export" the code, view the full design details, or when the Agent needs to analyze the generated HTML structure.

## Input Parameters

The skill expects you to extract the following information from the user request:
*   `name` (required): Full resource name `projects/{project}/screens/{screen}`.

**CRITICAL:** When both ID segments are available, construct the full `name` and call this read directly. Do not call `stitch-mcp-get-project` first.

## Resource Path Parsing

If the user provides a resource path or URL, use the following rules to extract `projectId` and `screenId`:

1.  **Format**: `web application/stitch/projects/{projectId}/screens/{screenId}`
    *   **Logic**: Extract `projectId` and `screenId` directly from the path segments.
    *   **Example**: `web application/stitch/projects/3492931393329678076/screens/2e22a9fb99ba49ddb6ce8907a1e74d60` -> `projectId="3492931393329678076"`, `screenId="2e22a9fb99ba49ddb6ce8907a1e74d60"`.

2.  **Format**: `projects/{projectId}/screens/{screenId}`
    *   **Logic**: Extract `projectId` and `screenId` from the path segments.

**Agent flow:**
1.  Recognize the user input matches one of the above formats.
2.  Extract both ID segments as strings and construct the canonical resource name.
3.  Call `get_screen` with `{"name": "projects/{project}/screens/{screen}"}`.
4.  Use the returned `htmlCode.downloadUrl`, `screenshot.downloadUrl`, and metadata for design-to-code (e.g. stitch-design-md or a framework conversion skill).

## Output Schema

Returns a `Screen` object:
*   **`htmlCode`**: The actual HTML/CSS code of the UI.
*   **`screenshot`**: High-resolution image URL.
*   **`figmaExport`**: Figma file asset.
*   `width`, `height`, `deviceType`.

## Intent Recognition & Framework Conversion

After retrieving the screen details (HTML code), check if the user's request implies converting the design to a specific frontend framework.

**Logic:**
1.  **Identify Framework**: Look for specific keywords in user input (e.g., "uView", "uViewPro", "Vue", "React", "Flutter").
2.  **Locate Skill**: Search for and read the corresponding skill definition file to understand the "Design Contract" or conversion rules.
    *   **uViewPro / uni-app**: If user mentions "uView", "uViewPro" or "UniApp", you **MUST** load and reference the complete context from the `stitch-uviewpro-components` skill to ensure accurate code generation.
        *   **References**: Read `skills/stitch-uviewpro-components/references/` (especially `contract.md` and `tailwind-to-uviewpro.md`) for core mapping rules.
        *   **API**: Read `skills/stitch-uviewpro-components/api/component-api.md` for component props and event definitions.
        *   **Examples**: Read `skills/stitch-uviewpro-components/examples/usage.md` for correct implementation patterns.
        *   **Resources**: Read `skills/stitch-uviewpro-components/resources/architecture-checklist.md` for design compliance.

    *   **uView (Standard)**: If user mentions "uView" (without "Pro") or "uView 2.0", load `stitch-uview-components`.
        *   **Context**: Read `references/` (contract, tailwind-to-uview), `api/component-api.md`, `examples/usage.md`, `resources/architecture-checklist.md` from `stitch-uview-components`.

    *   **Element Plus**: If user mentions "Element Plus", "Element", "Vue Desktop", load `stitch-vue-element-components`.
        *   **Context**: Read `references/` (contract, tailwind-to-element-plus), `api/component-api.md`, `examples/usage.md`, `resources/architecture-checklist.md` from `stitch-vue-element-components`.

    *   **Vant UI**: If user mentions "Vant", "Vue Mobile", load `stitch-vue-vant-components`.
        *   **Context**: Read `references/` (contract, tailwind-to-vant), `api/component-api.md`, `examples/usage.md`, `resources/architecture-checklist.md` from `stitch-vue-vant-components`.

    *   **Layui Vue**: If user mentions "Layui", load `stitch-vue-layui-components`.
        *   **Context**: Read `references/` (contract, tailwind-to-layui), `api/component-api.md`, `examples/usage.md`, `resources/architecture-checklist.md` from `stitch-vue-layui-components`.

    *   **Bootstrap Vue**: If user mentions "Bootstrap", load `stitch-vue-bootstrap-components`.
        *   **Context**: Read `references/` (contract, tailwind-to-bootstrap), `api/component-api.md`, `examples/usage.md`, `resources/architecture-checklist.md` from `stitch-vue-bootstrap-components`.

    *   **React / Tailwind**: If user mentions "React" (standard), load `stitch-react-components`.
        *   **Context**: Hand off to **`stitch-react-components`**. Install: `npx skills add full-stack-skills/stitch-skills --skill stitch-react-components`.

    *   **Shadcn UI**: If user mentions "Shadcn", "Next.js", "Radix", load `stitch-shadcn-ui`.
        *   **Context**: Hand off to **`stitch-shadcn-ui`**. Install: `npx skills add full-stack-skills/stitch-skills --skill stitch-shadcn-ui`.

    *   **Other Frameworks**: Search for matching `stitch-*-components` skills and load their respective `api`, `examples`, and `references` directories.
3.  **Apply Constraints**: Use the rules defined in that framework's skill (e.g., component mappings, slot usage, unit conversion) to transform the raw HTML from Stitch into the target framework code.

**Example Flow:**
*   User: "Get screen X and convert to uViewPro code."
*   Agent:
    1.  Call `get_screen` to get HTML.
    2.  Detect intent: "uViewPro".
    3.  **Load Context**: Read `contract.md`, `component-api.md`, `usage.md`, and `architecture-checklist.md` from `stitch-uviewpro-components`.
    4.  Generate code by applying uViewPro rules to the Stitch HTML.

## Usage Example

User Input: "Give me the code for the login screen we just made."

Agent Action:
1.  Identify target screen.
2.  Call `get_screen` with `{"name":"projects/37803.../screens/88805..."}`.

## References

- [Examples](examples/usage.md)

<!-- QUALITY_BASELINE_V1 -->
## When to use（什么时候使用）

当用户需要 **只读发现、检查或汇总当前资源状态** 时加载本技能。先从请求中提取目标、输入、约束、交付格式和验收标准；描述摘要为：Retrieves the full details of a specific screen, including HTML code.。

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

确认查询范围、身份上下文、分页上限和输出字段；任一关键条件未知时停止在只读阶段。
### Step 3：形成计划

列出将调用的工具、会改变的对象、成功标准以及失败后的安全退出方式。
### Step 4：执行动作

执行有界只读查询并保留来源标识；每个外部调用均保留可关联的状态或回执。
### Step 5：验证交付

返回资源标识、查询条件、分页状态和未验证项，并把事实、推断和未验证项分开陈述。

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

不创建、不修改、不删除资源；若后续需要写操作，先交给对应写入技能并重新确认。 如果请求需要别的技能，不复制其正文；按技能名称进行交接，并保留当前任务上下文。

## Progressive disclosure

- 需要确定输入/输出、状态和授权点时，读取 `references/workflow-contract.md`。
- 需要交付前自检时，读取 `references/validation-checklist.md`。
- 遇到超时、部分成功或恢复场景时，读取 `references/error-recovery.md`。
- 首次运行、拒绝越权和失败恢复分别参考 `examples/happy-path.md`、`examples/boundary-refusal.md`、`examples/failure-recovery.md`。
