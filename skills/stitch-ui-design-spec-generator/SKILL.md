---
name: stitch-ui-design-spec-generator
description: 仅在用户或旧工作流明确调用 stitch-ui-design-spec-generator 时使用的兼容入口；按名称转交 stitch-design-spec，保留原输入与输出范围，不维护独立设计或提示词规则。
license: Apache-2.0
---

# 兼容入口：stitch-ui-design-spec-generator

## When to use

本名称仅在既有调用者指定旧名称时加载；通用新请求不适用此适配器。

本名称为旧调用保留。唯一规则所有者为 **stitch-design-spec**；新任务直接使用新入口。

## Workflow

### Step 1：保存交接输入

保留用户请求、PRD/已有规格、页面/流程 ID、框架、设计系统证据、编辑目标与交付位置；不扩张用户范围。
### Step 2：加载统一入口

加载已安装的 `stitch-design-spec`，传递原输入以及输出意图：**spec-only：需求/PRD→页面规格；仅当用户也要求提示词时继续编译**。spec-only 是完整合同的规格裁剪视图，不要求先生成提示。
### Step 3：交回结果

由新入口执行其现行规则；原样交回产物、假设、验证结果与未完成项。转交本身不等于交付完成。
### Step 4：缺失依赖恢复

若新入口缺失，明确报告依赖未安装并保留上下文。安装说明：`npx skills add full-stack-skills/stitch-skills --skill stitch-design-spec`。不自动安装，也不恢复旧规则副本。

## Rules 与不适用边界

不收集凭据，不向下游发送密钥或无关账号信息。此适配器不适用于直接执行远程生成。

## Validation

此入口不调用 Stitch、不需要认证、不自行创建页面、系统或屏幕。既有 DESIGN.md 不能被升级为远程应用证据。不得把示例、旧回执或 token 当作事实传递。检查目标技能已加载、范围一致、实际结果和未验证项已返回。

兼容示例：旧名收到“只生成页面规格”时传递 spec-only；收到“只改搜索框”时传递局部编辑目标，不能扩为全套页面。缺依赖的恢复方式为说明缺失后等待用户安装或使用已有可用入口，不静默调用远程工具。

## Gotchas

- 旧名称是发现入口，不是 Python/CLI/MCP 工具；不要把技能名当作远程工具调用。
- 用户同时给了旧名和完整设计规格时直接传递规格，避免重新推导并改变原页面 ID。
- 下游返回部分结果或待确认项时，兼容入口保留这些状态，不能改写成“全部完成”。
- 若调用链从 canonical 又回到本适配器，停止循环，回到 canonical 的当前阶段。

## 来源与迁移

原提示词增强包含 Google LLC 及贡献者的 Apache-2.0 内容，已迁入 stitch-design-spec；原许可保留于 [LICENSE.txt](LICENSE.txt)。上游 [固定快照](https://github.com/google-labs-code/stitch-skills/tree/0337446dadde6f8c94210444e2aa9d546126480f) 为社区来源，非官方支持产品。
