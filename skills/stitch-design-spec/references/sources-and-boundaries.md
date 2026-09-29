# 来源与职责

此技能整合原 `stitch-ui-design-spec-generator` 的本地设计决策和 `stitch-ui-prompt-architect` 的模糊输入/规格编译能力。整合前仓库提交：3295d9d5fb164dfe7540f54b50e1a3f7120e1cb0；旧资源保留迁移说明，内容规则只在本技能维护。

提示词增强和 KEYWORDS 保留 Google LLC 及贡献者 Apache-2.0 归属，上游固定提交 0337446dadde6f8c94210444e2aa9d546126480f；这是社区来源，不宣称官方支持或当前线上验证。

模块输入与实例中心案例改写自 full-stack-doc v3.0.2 的 `templates/module/模块-Stitch设计提示词.md`，文档边界参考其 `references/document-boundaries.md`。原文的模板占位符、示例数量/引擎、微软雅黑/颜色及历史“已完成”都不是目标项目事实。此处实例中心案例以演示产品和明确教学补充呈现，不能据此推出线上存在这些能力。

Agent Browser 教学案例改写自其 `docs/functional-design/USER-FLOWS.md` F04/F05 与页面体系。保留 J03→G03→P11/P12 的关联及“结果未知先核对”语义；新增排版建议与原业务要求分开标记。示例在本包内可独立阅读，不依赖作者本机目录。

| 所有者 | 保留职责 |
| --- | --- |
| 产品/功能设计 | 功能清单、页面职责、业务状态与权限、产品验收 |
| full-stack-doc | 文档层级、命名、根/版本/模块/交付组织 |
| stitch-design-spec | 页面设计合同、状态/流程投影、提示编译、覆盖和任务交接 |
| stitch-design-md | 从资产提取视觉语言 |
| 框架合同技能 | 框架组件约束与选择器内容 |
| stitch-ui-execute / delivery-harness | 实际执行、运行时 schema、图像验收与归档 |

本技能不将上游文档改写成另一套正式 PRD，也不把所有设计技能合并为单体入口。
