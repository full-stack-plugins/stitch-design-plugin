---
name: stitch-design-spec
description: 当用户要为 Stitch 将 PRD 或功能设计转成逐页规格、编写模块设计提示词、把已有规格转成提示词或润色模糊 UI 想法时使用；统一产出页面合同、导航与状态流程、三段提示词、覆盖矩阵和验收任务，仅编制本地文档。
license: Apache-2.0
---

# Stitch 设计规格与提示词

本技能统一替代 `stitch-ui-design-spec-generator` 与 `stitch-ui-prompt-architect` 的内容规则。面向产品、设计、前端与 Agent 编排人员；新任务直接使用本入口。

> 提示词增强与词汇库改编自 Google LLC 及贡献者的 [google-labs-code/stitch-skills 固定快照](https://github.com/google-labs-code/stitch-skills/tree/0337446dadde6f8c94210444e2aa9d546126480f)，Apache-2.0，见 [LICENSE.txt](LICENSE.txt)。该上游不是 Google 官方支持产品。来源及本地整合记录见 [来源与边界](references/sources-and-boundaries.md)。

## When to use

- “把这份 PRD 整理成一套可交给 Stitch 的逐页设计规格和提示词。”
- “在 full-stack-doc 的模块目录中编写实例中心 Stitch 设计提示词。”
- “把已有页面合同转成提示词；沿用应用中的设计系统。”
- “润色‘做一个预约页’，先给草案。” / “只修改现有页面搜索框。”

## 输入与路径

| 输入 | 工作路径 | 交付视图 |
| --- | --- | --- |
| PRD / 功能设计包 / 多页面需求 | 盘点来源→逐页合同→编译提示→覆盖与任务 | 完整包 |
| 只要规格（spec-only） | 仅整理规格合同和缺口，不编译提示 | README/设计总览/逐页合同或等价单文件 |
| 已有规格 | 保留原 ID 和业务规则，补缺项→编译提示 | 完整包或模块文档 |
| full-stack-doc 模块 | 沿用其文档目录、模块名和版本，只编写 Stitch 内容 | 模块单文件 |
| 模糊想法 | 将模糊词转成组件、真实文案和状态，标记假设 | prompt-only 草案 |
| 精确局部修改 | 明确目标页面、区域、修改差值 | prompt-only 编辑 |

先区分产品范围与输出视图。小提示词任务不要求补齐全产品 PRD。缺失平台、品牌或数据只作明确建议；涉及业务权限、危险操作或页面职责的冲突列为待确认，不自作主张改已确认需求。

## Workflow

### Step 1：核对来源

读用户指定 PRD、功能清单、NAVIGATION、UI-STRUCTURE、USER-FLOWS、MASTER-PLAN、模块 UI、DESIGN.md；只读相关材料，记录来源路径/版本/章节及“已确认、建议、待确认”。先检查已有产物，增量更新，不生成第二套事实源。
### Step 2：定义合同

按 [产物合同](references/output-contract.md) 固定字段整理页面职责、入口/返回、外壳/业务区/Agent 侧栏、数据与动作、权限、状态、恢复、响应式、无障碍和验收。页面不等于弹窗、侧栏或状态变体。沿用原页面/功能/流程 ID。
### Step 3：串联流程

画导航和关键操作 Mermaid；每条路径写触发、前置条件、动作、反馈、下一步、取消/失败/恢复。共享外壳只定义一次，逐页写差异。不能用几张好看的主态页面替代完整覆盖。
### Step 4：编译提示

按 [编译规则](references/prompt-rules.md) 选择 inline / applied-system / targeted-edit；每份提示严格使用 `[Context]` → `[Layout]` → `[Components]`，布局编号、控件有实际标签、状态和行为。一次提示绑定一页及指定状态，相关变体可成组，但要逐项可追踪。
### Step 5：拆分任务

页面/状态→提示→任务双向关联；任务包含前置依赖、输入、产物、验收和证据，复用现有 OpenSpec/Spec Kit 任务，不自建冲突的计划。按共享结构→主路径→异常恢复→跨端核对推进。
### Step 6：验证交接

按 [验收表](references/validation.md) 检查覆盖、链接、模式与业务语义；完整包运行本技能 `scripts/validate_package.py`。报告结构校验、语义审阅、实际生成三个层级；文档完成不等于远程设计或运行验收完成。

默认视口：Mobile 390×884、Tablet 768×1024、Desktop 1280×1024。用户明确指定时遵从并记录覆盖理由。视口是设计目标，不是 MCP `deviceType` 枚举或服务端保证。

## 固定输出

- 完整包：`README.md`、`DESIGN-SPEC.md`、`pages/<page-id>.md`、`prompts/<prompt-id>.md`、`COVERAGE.md`、`MASTER-PLAN.md`、`manifest.json`。目录优先沿用已有位置，否则建议 `docs/stitch-design/`。
- 模块文档：使用 [模块模板](templates/module-stitch.md)，包含同样的语义栏目，只维护一份内容；不用同时写一套重复文件。
- prompt-only：元信息/假设在提示代码块之外，代码块内只有三段正文；可按用户要求保存为 `next-prompt.md`，兼容 stitch-ui-loop。
- JSON 输入也可归一化；JSON 输出需用户要求时提供，字段必须标为本地语义，不冻结模型、设备、字体等运行时枚举。

首次完整使用，先读 [实例中心端到端示例](examples/instance-center/README.md)；涉及 Agent 执行确认，读 [Agent Browser 转换示例](examples/agent-browser.md)；短请求和恢复见 [模式示例](examples/prompt-modes.md)。这些是教学材料，示例数据和历史完成状态不得带入目标项目。

## Rules 与不适用边界

- 全程无需凭据、联网或 Stitch MCP；本技能不创建项目、不应用设计系统、不生成屏幕、不上传数据、不实现业务代码。
- `DESIGN.md` 只证明本地有视觉定义，不能证明远程项目已应用系统。applied-system 模式必须由执行器提供当前项目匹配的应用证据。
- 不虚构 API、统计、角色权限、真实客户信息或成功回执。示例值标记为演示；不复制密钥、cookie、签名下载 URL 或机器绝对路径。
- 不覆盖已批准业务规则。来源冲突保留各方证据，影响该部分的输出保持草案；独立页面可以继续。
- 本地产物写失败时保留已有文件，重试前核对当前内容，不把部分写入标记完成。修订记录受影响 ID 与原因。

## 交接

- `full-stack-doc`：拥有文档分层、命名和放置规则；本技能只提供模块 Stitch 内容。上游功能设计负责功能范围和产品决策，不在这里复制重写。
- `stitch-design-md`：从已有资产提取视觉语言；本技能消费其结果。
- `stitch-ui-execute`：执行已授权的生成/编辑，接收规格、提示和独立的系统元信息；当前工具 schema 由它核对。
- `stitch-design-harness`：生成后的比较、批准、归档；本地 manifest 不是其 `.stitch/specs` 可执行 schema，不直接覆盖。
- 按需框架合同见编译规则。安装入口（仅说明，不自动执行）：`npx skills add full-stack-skills/stitch-skills --skill <skill-name>`。full-stack-doc 属于 document-skills：`npx skills add full-stack-skills/document-skills --skill full-stack-doc`。

## Gotchas 与 FAQ

**缺规格还能润色吗？** 可以。输出明确标为建议的 prompt-only 草案，不能把猜测权限/API写成事实。

**只读旧名称能继续吗？** 旧入口按名转交本技能；没有安装本技能时准确说明缺失依赖，不退回旧规则副本。

**框架与应用中的系统冲突怎么办？** 业务组件结构仍可沿用框架，视觉 tokens 单独交接；不要往 applied-system 提示中重复注入。

**校验通过就保证任意 LLM 输出一致吗？** 不能。固定合同、正反示例和失败门禁约束可检查部分；语义覆盖仍需审阅或模型评测，远程效果需实际生成验证。
