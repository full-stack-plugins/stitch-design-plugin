---
name: stitch-ued-guide
license: Apache-2.0
description: UED guidelines, visual vocabulary, and prompt structure for Stitch. Use when the user asks about layout/style terms, device constraints, or when structuring/improving Stitch prompts; combine with stitch-ui-prompt-architect for vague→concrete prompts.
---
# Stitch UED Guidelines

This skill serves as a reference for User Experience Design (UED) guidelines when working with Stitch. It includes interaction principles, visual vocabulary, and prompt engineering strategies.

## When to use this skill

Use this skill when:

*   The user asks about **layout or style terms** (e.g. Masonry, Glassmorphism, Sidebar) or **device constraints** (mobile vs desktop width, touch targets).
*   You need to **structure or improve a Stitch prompt** (Context → Layout → Component → Content) or ensure consistent UED wording.
*   You are coordinating with **stitch-ui-designer** and need UED/accessibility/design-system alignment alongside Stitch generation.

For **transforming vague ideas into a full Stitch prompt**, use **stitch-ui-prompt-architect**; combine both when you want structure + vocabulary (this skill) and concrete prompt output (prompt-architect).

## Design Modes (Model Selection)

Stitch operates in two distinct modes, which you should choose based on the user's need for speed vs. fidelity:

*   **Standard Mode (Gemini 2.5 Flash)**
    *   **Best for**: Rapid iteration, wireframing, exploring multiple layout ideas quickly.
    *   **Features**: Fast generation, Text-to-UI, Theme editing.
    *   **Use Case**: "Show me 3 different layout options for a login screen."

*   **Experimental Mode (Gemini 2.5 Pro)**
    *   **Best for**: High-fidelity design, complex logic, visual references.
    *   **Features**: Image-to-UI (Sketch/Screenshot upload), richer details, smarter component logic.
    *   **Use Case**: "Turn this napkin sketch into a production-ready dashboard."

## Prompt Engineering Strategy

A perfect Stitch prompt follows this structure:
`[Context & Style]` + `[Layout Structure]` + `[Component Details]` + `[Content & Data]`

### 1. Context & Style
*   **Context**: "Mobile fitness app for gym goers."
*   **Style**: "Dark mode with neon green accents (Cyberpunk). Rounded corners."
*   **Reference**: "Similar to Spotify's dark theme but for fitness."

### 2. Layout Structure
*   **Mobile**: "Bottom navigation bar, scrollable feed."
*   **Desktop**: "Left sidebar navigation, top header, main content area with data grid."
*   **Grid**: "3-column card grid with responsive behavior."

### 3. Component Details
*   **Don't say**: "A list."
*   **Do say**: "A vertical list of 'Workout Cards', each containing a map thumbnail, duration (e.g., '30 min'), and a 'Start' button."

### 4. Content & Data
*   **Realism**: Ask for realistic data. "User 'Alice', 'Morning Yoga', '300 kcal'."
*   **State**: "Active state for the 'Home' tab."

**Quick checklist (before calling generate_screen_from_text):**

*   [ ] **Context & style** defined? (device, app type, theme)
*   [ ] **Layout** defined? (nav position, main area structure)
*   [ ] **Key components** specific? (avoid "a list"; use e.g. "Workout Cards with map thumbnail, duration, Start button")
*   [ ] **Sample content / state** included? (real copy, active state)

## Visual Vocabulary

Use these terms to control the look and feel:

### Layout Patterns
*   **Hero Section**: Top area with main headline/image.
*   **Split Screen**: Left/Right division (common in Desktop Auth).
*   **Masonry**: Waterfall layout (Pinterest style).
*   **Sidebar Navigation**: Vertical nav on the left (SaaS standard).

### Style Modifiers
*   **Flat**: No shadows, high saturation.
*   **Material**: Shadows, layers, paper metaphor.
*   **Neomorphism**: Soft shadows, extruded shapes.
*   **Glassmorphism**: Blurred transparency, frosted glass.
*   **Brutalism**: Raw, bold, high contrast, large typography.

## Color & Theme Prompts

When describing **Context & Style**, use a clear color structure so Stitch produces consistent palettes. A strong pattern (inspired by [AI配色提示词-UI配色指南](https://mp.weixin.qq.com/s/1SDFd7ZOPkbhpvHsmTJQjQ)):

**Structure**: `[App type]` + `[Background hex]` + `[Primary hex]` + `[Secondary hex]` + `[Accent hex]` + `[Design system]` + `[Mood]`. Optionally add **semantic colors**: success green, alert red, warning yellow.

**Example — Dark productivity:**
> Modern productivity app dark theme, charcoal grey background #1a1a1a, primary blue #4A90E2, secondary teal #26D0CE, neutral greys #2d2d2d to #f5f5f5, accent orange #FF6B35 for CTAs, Material Design 3 inspired, high contrast for readability, professional and focused atmosphere.

**Example — Bright desktop tool:**
> Project management app bright theme, clean white background #FFFFFF, primary royal blue #2563EB, secondary purple #7C3AED, soft grey cards #F9FAFB, green success #22C55E, red alerts #DC2626, yellow warnings #F59E0B, minimal design with subtle shadows, organized and efficient visual hierarchy.

**Quick color checklist**: Background defined? Primary/secondary/accent with hex? Semantic colors (success/alert/warning) if needed? Design system (Material 3, Fluent) or style (glassmorphism, minimal) mentioned?

More ready-to-use prompts: see [`docs/color-prompt-guide.md`](https://github.com/full-stack-skills/stitch-skills/blob/main/docs/color-prompt-guide.md) in this repo, or the [original article](https://mp.weixin.qq.com/s/1SDFd7ZOPkbhpvHsmTJQjQ) for 20 curated prompts.

## Device Guidelines

*   **Mobile**: ~375px width. Focus on thumb-friendly bottom navigation. Vertical scrolling is expected.
*   **Desktop/Web**: ~1440px width. Use horizontal space. Multi-column layouts.
*   **Tablet**: Hybrid. Often resembles desktop but with touch targets.

## Accessibility & Inclusive Design

*   **Contrast & readability**: Prefer sufficient contrast (dark/light); avoid low-contrast text. In prompts, you can add "high contrast" or "clear text hierarchy."
*   **Touch targets**: For mobile/tablet, ask for touch-friendly controls (e.g. "buttons at least 44px tap area"). In Context or Component details, add "touch-friendly" when relevant.
*   **Focus & keyboard**: For desktop, mention "clear focus states" or "keyboard-navigable" when the design should support accessibility.
*   **In prompts**: Add phrases like "high contrast," "clear focus states," "touch-friendly buttons" in Context/Style or Component Details when UED or accessibility alignment is needed.

## Controls & Variants

*   **Variants**: Stitch generates multiple options. You can ask to "Generate variants for the hero section" to A/B test designs.
*   **Controls**: Use the **Interactive Chat** to refine designs ("Make the button blue", "Move the logo to the center").

## Related resources

- **Stitch Effective Prompting Guide**: https://stitch.withgoogle.com/docs/learn/prompting/ — official best practices; consult for up-to-date recommendations.
- **Division of labor**: **stitch-ued-guide** = structure and vocabulary (how to phrase, what terms to use). **stitch-ui-prompt-architect** = transform vague ideas into a full, executable Stitch prompt (with DESIGN.md, framework contracts). Use both when you need consistent UED wording and concrete prompt output.
- **Vague → enhanced prompt**: Use **stitch-ui-prompt-architect** (Path A: enhance vague UI ideas with specificity, UI/UX keywords, DESIGN.md context). Use with **stitch-design-md** for DESIGN.md and **stitch-ui-design-spec-generator** for full flow.
- **Stitch skills in this repo** (prefer these over official): design-md → **stitch-design-md**; enhance-prompt → **stitch-ui-prompt-architect** (two paths + framework contracts); react-components → **stitch-react-components**; stitch-loop → **stitch-loop**; remotion → **stitch-remotion**; shadcn-ui → **stitch-shadcn-ui**. Plus **stitch-mcp-*** (one skill per MCP tool: create-project, get-project, list-projects, generate-screen-from-text, get-screen, list-screens), **stitch-ui-design-spec-*** (Bootstrap, Element Plus, Layui, uView, uView Pro, Vant), **stitch-ui-designer** (orchestrator), and six Stitch→framework conversion skills (Vue + Element/Bootstrap/Layui/Vant, uni-app + uView/uView Pro). These skills reference each other and the same MCP; use stitch-mcp-<tool> names (e.g. get_screen → stitch-mcp-get-screen).

## References

- [Examples](examples/usage.md)

<!-- QUALITY_BASELINE_V1 -->
## When to use（什么时候使用）

当用户需要 **为当前请求选择并执行可验证、可恢复的专业工作流** 时加载本技能。先从请求中提取目标、输入、约束、交付格式和验收标准；描述摘要为：UED guidelines, visual vocabulary, and prompt structure for Stitch. Use when the user asks about layout/style terms, device constraints, or when structuring/improving Stitch prompts; combine with stitch-ui-prompt-architect for vague→concrete prompts.。

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
