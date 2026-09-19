---
name: stitch-shadcn-ui
description: 为 Stitch 来源的 React 页面选择、迁移和验证 shadcn/ui 原语、主题和 registry 内容时触发。首次通用 HTML 转 React 用 stitch-react-components；不自动迁移无关工程。
license: Apache-2.0
---

# Stitch 的 shadcn/ui 迁移

## 快速开始

1. “把预约表单迁为 shadcn Input/Button；先给本地可审阅结果。”
2. “迁移订单详情 Dialog 并保留键盘行为；保留已有范围与来源。”
3. “比较 registry 源码与现有主题 tokens；标出缺少的输入和验证状态。”

面向设计师、前端开发者和维护此流程的团队。设计师提供意图与素材，开发者提供工程/工具，团队在交接中保留来源和验收状态。

## 能力边界说明

### ✅ 擅长处理

- 把预约表单迁为 shadcn Input/Button。
- 迁移订单详情 Dialog 并保留键盘行为。
- 比较 registry 源码与现有主题 tokens。

### ⚠️ 需要素材

- 目标工程与 components.json。
- Stitch 资产及当前组件行为。
- Tailwind/React 版本和待迁移范围。

### ❌ 不适用场景及交接

- 通用 React 页面转换 → stitch-react-components。
- 原生 App → stitch-react-native。
- 业务登录或支付服务 → 项目接口流程，提交表单行为契约。

## 工作流程

1. 读取当前工程版本和 Stitch HTML/截图，明确只迁移的组件。
2. 先读 migration-guide，核对原 Props、状态、键盘与主题。
3. 检索当前可用 registry 工具和组件源，审查依赖与变更再应用。
4. 按现有 cn/cva/主题约定迁移一个组件并保留可访问性，验证后再处理下一个。
5. 运行目标类型/lint/build 与键盘/主题检查；verify-setup.sh 仅是 Tailwind3 启发式，不代表 Tailwind4 或全部通过。

按依赖排序：来源核对 → 本地产物 → 已授权外部操作 → 验证交接。多任务先做当前主路径；缺信息先输出假设草案，再精确列明缺少什么以及用途，不使用“请提供更多背景”的空泛提示。

## 安全与结果验证

不读取无关账号配置，不收集用户密码；凭据只由环境或已授权连接器提供。示例只用演示数据；上传前将客户姓名、电话、订单号替换为演示值，并检查 HTML、截图和文件元数据。禁止将密钥、会话 cookie、base64 全文或签名下载 URL 写入报告/版本库。未经验证的参数、视觉效果、业务数字不得编造；输出注明来源、决策依据、实际执行与尚未验证部分。

- 保留 Dialog 焦点恢复与键盘关闭。
- registry 源和依赖实际审查。
- 浅/深主题及焦点可见性经验证。

可定制：registry、原语、主题、variant、目标组件和迁移顺序。增值检查：逐组件迁移；版本分流；可访问性回归清单。

## FAQ

**Q1：交付的主要结果是什么？** 预约表单 label htmlFor="phone" + Input id="phone"；保留错误 aria-describedby；不把电话号码写入示例。

**Q2：什么时候应换用其他入口？** 通用 React 页面转换 → stitch-react-components；原生 App → stitch-react-native；业务登录或支付服务 → 项目接口流程，提交表单行为契约。

**Q3：缺少输入会怎样？** 先给明确标记的本地假设草案，并列出“需要补充：目标工程与 components.json；Stitch 资产及当前组件行为；Tailwind/React 版本和待迁移范围”。依赖这些输入的写操作不执行。

**Q4：怎样判断完成？** 保留 Dialog 焦点恢复与键盘关闭；registry 源和依赖实际审查；浅/深主题及焦点可见性经验证。

**Q5：怎样定制？** registry、原语、主题、variant、目标组件和迁移顺序；未提供时沿用现有项目值并标明假设。

**Q6：是否自动上传、安装或上线？** 只执行当前请求与已有授权覆盖的动作；没有远程回执不称上传成功，没有运行验证不称上线。额外安装或扩大范围需先说明具体影响。

## 按需参考

- 执行详细映射、API 或模板时读 [扩展流程](references/workflow.md)。
- 遇到失败/异常输入时读 [反模式与 Gotchas](references/anti-patterns.md)。
- 涉及边缘场景、兼容性、定制和授权时读 [深度 FAQ](references/faq-deep.md)。
- 需要完整输入输出及验证场景时读 [本地应用示例](examples/local-validation.md)。
- 本地实现依据为当前技能伴随源码及 [固定上游快照](https://github.com/google-labs-code/stitch-skills/tree/0337446dadde6f8c94210444e2aa9d546126480f)；结构遵循 [Agent Skills 规范](https://agentskills.io/specification)。工具当前行为以实际 schema 为准，未连接时不声称已核验线上行为。

<!-- QUALITY_BASELINE_V1 -->
## When to use（什么时候使用）

当用户需要 **为当前请求选择并执行可验证、可恢复的专业工作流** 时加载本技能。先从请求中提取目标、输入、约束、交付格式和验收标准；描述摘要为：为 Stitch 来源的 React 页面选择、迁移和验证 shadcn/ui 原语、主题和 registry 内容时触发。首次通用 HTML 转 React 用 stitch-react-components；不自动迁移无关工程。。

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
