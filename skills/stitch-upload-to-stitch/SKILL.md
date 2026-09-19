---
name: stitch-upload-to-stitch
description: 将已授权的本地图片或 HTML 安全上传到指定 Stitch 项目，并将 Markdown 路由到远程 upload_design_md；只生成本地文件、检索项目或部署网站时不触发。
license: Apache-2.0
---

# 上传本地资产到 Stitch

## 快速开始

1. “上传脱敏的门店预约页 HTML；先给本地可审阅结果。”
2. “上传品牌 DESIGN.md 供系统创建；保留已有范围与来源。”
3. “上传用户提供的演示稿 PNG；标出缺少的输入和验证状态。”

面向设计师、前端开发者和维护此流程的团队。设计师提供意图与素材，开发者提供工程/工具，团队在交接中保留来源和验收状态。

## 能力边界说明

### ✅ 擅长处理

- 上传脱敏的门店预约页 HTML。
- 将品牌 DESIGN.md 路由到 MCP `upload_design_md`。
- 上传用户提供的演示稿 PNG。

### ⚠️ 需要素材

- 真实 projectId。
- 支持格式的已审核本地文件。
- 通过 `platform_secret_provider()` 读取的凭据与上传授权。

### ❌ 不适用场景及交接

- 远程套用设计系统 → stitch-manage-design-system。
- 从代码生成上传文件 → stitch-code-to-design。
- 公开部署网站 → 目标部署流程，交付 HTML 资产包。

## 工作流程

1. 核对文件路径、大小、类型和目标项目，确保授权覆盖这些内容。
2. 图片/HTML 脚本通过 `platform_secret_provider()` 使用环境优先、用户配置兜底的凭据链；CLI 不接受密钥或服务根地址参数。
3. Markdown 不走私有 REST 脚本；读取文件后在进程内编码，并调用当前 MCP `upload_design_md`。
4. 私有 REST 固定到 `https://stitch.googleapis.com` 并单次发送；禁止重定向和自动重试。
5. 用 `get_project` 的项目资源名、`list_screens` 的纯项目 ID、`get_screen` 的 `name: projects/{project}/screens/{screen}` 对账。

按依赖排序：来源核对 → 本地产物 → 已授权外部操作 → 验证交接。多任务先做当前主路径；缺信息先输出假设草案，再精确列明缺少什么以及用途，不使用“请提供更多背景”的空泛提示。

## 安全与结果验证

不读取无关账号配置，不收集用户密码；凭据只由环境或已授权连接器提供。示例只用演示数据；上传前将客户姓名、电话、订单号替换为演示值，并检查 HTML、截图和文件元数据。禁止将密钥、会话 cookie、base64 全文或签名下载 URL 写入报告/版本库。未经验证的参数、视觉效果、业务数字不得编造；输出注明来源、决策依据、实际执行与尚未验证部分。

- argv/日志/报告不含密钥、base64 或完整响应。
- PNG/JPG/JPEG/WEBP 映射 screenshot，HTML/HTM 映射 htmlCode；Markdown 使用 `upload_design_md`。
- REST 只接受当前 `results[].screen` 响应并输出校验后的 screen name。

可定制：title、generated-by、文件路径。服务根地址不可定制。增值检查：配置凭据；小输出 ID 交接；无自动重试和重定向。

## FAQ

**Q1：交付的主要结果是什么？** 本地 HTML 请求使用 htmlCode、text/html 和 DOCUMENT；远程执行后只交付经过类型、格式与项目归属校验的 screen/instance 标识。完整离线输入、请求和模拟回执见本地应用示例；请求构造不代表上传成功。

**Q2：什么时候应换用其他入口？** 远程套用设计系统 → stitch-manage-design-system；从代码生成上传文件 → stitch-code-to-design；公开部署网站 → 目标部署流程，交付 HTML 资产包。

**Q3：缺少输入会怎样？** 先给明确标记的本地假设草案，并列出“需要补充：真实 projectId；支持格式的已审核本地文件；通过运行环境注入的 STITCH_API_KEY 与上传授权”。依赖这些输入的写操作不执行。

**Q4：怎样判断完成？** argv/日志/报告不含密钥、base64 或完整响应；本地 REST 和远程 Markdown 路径分离；返回的 screen name 已经只读对账。

**Q5：怎样定制？** title、generated-by、文件路径；服务根地址固定为 Google 官方 origin。

**Q6：是否自动上传、安装或上线？** 只执行当前请求与已有授权覆盖的动作；没有远程回执不称上传成功，没有运行验证不称上线。额外安装或扩大范围需先说明具体影响。

## 按需参考

- 执行详细映射、API 或模板时读 [扩展流程](references/workflow.md)。
- 遇到失败/异常输入时读 [反模式与 Gotchas](references/anti-patterns.md)。
- 涉及边缘场景、兼容性、定制和授权时读 [深度 FAQ](references/faq-deep.md)。
- 需要完整输入输出及验证场景时读 [本地应用示例](examples/local-validation.md)。
- 本地实现依据为当前技能伴随源码及 [固定上游快照](https://github.com/google-labs-code/stitch-skills/tree/0337446dadde6f8c94210444e2aa9d546126480f)；结构遵循 [Agent Skills 规范](https://agentskills.io/specification)。工具当前行为以实际 schema 为准，未连接时不声称已核验线上行为。

<!-- QUALITY_BASELINE_V1 -->
## When to use（什么时候使用）

当用户需要 **在明确输入、预算和交付约束后执行生成或写入操作** 时加载本技能。先从请求中提取目标、输入、约束、交付格式和验收标准；描述摘要为：将已授权的本地图片或 HTML 安全上传到指定 Stitch 项目，并将 Markdown 路由到远程 upload_design_md；只生成本地文件、检索项目或部署网站时不触发。。

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

校验输入、模型/工具能力、输出路径、预算上限和审批状态；任一关键条件未知时停止在只读阶段。
### Step 3：形成计划

列出将调用的工具、会改变的对象、成功标准以及失败后的安全退出方式。
### Step 4：执行动作

按一次批准执行并记录请求标识；模糊结果先查询而不是重提；每个外部调用均保留可关联的状态或回执。
### Step 5：验证交付

验证产物存在性、格式、哈希/标识、成本状态和质量门禁，并把事实、推断和未验证项分开陈述。

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

付费、发布、覆盖、上传或外部写入必须使用当前任务的显式授权；不自动扩大次数和预算。 如果请求需要别的技能，不复制其正文；按技能名称进行交接，并保留当前任务上下文。

## Progressive disclosure

- 需要确定输入/输出、状态和授权点时，读取 `references/workflow-contract.md`。
- 需要交付前自检时，读取 `references/validation-checklist.md`。
- 遇到超时、部分成功或恢复场景时，读取 `references/error-recovery.md`。
- 首次运行、拒绝越权和失败恢复分别参考 `examples/happy-path.md`、`examples/boundary-refusal.md`、`examples/failure-recovery.md`。
