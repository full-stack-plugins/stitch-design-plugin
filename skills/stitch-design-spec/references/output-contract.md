# 固定产物合同

## 事实源与裁剪

已确认的功能设计包拥有功能范围、页面 ID、导航、交互和实施决策。本技能从中投影 Stitch 页面规格，引用章节，不重新发明页面编号。没有上游包时，对源 PRD 建立最小页面清单并标明设计建议。稳定 ID 跨修订保留；删除必须记录理由与受影响提示/任务。

完整包必须使用以下结构，已有项目可保留其根目录：

| 文件 | 必须包含 |
| --- | --- |
| README.md | 产品/版本/模块、输入清单、范围/非范围、当前状态、阅读顺序、待确认项 |
| DESIGN-SPEC.md | 页面职责清单、入口/退出/权限、导航 Mermaid、共享外壳/业务区/可选侧栏、视觉来源、响应式与无障碍、关键流程 Mermaid 与异常恢复 |
| pages/<ID>.md | 逐页合同，按页面模板的栏目，标明来源；无独立路由的弹窗归属宿主页或全局面 |
| prompts/<ID>.md | 单个三段提示正文；项目 ID、模式、来源、系统证据放 manifest，不混进正文 |
| COVERAGE.md | 功能/页面/状态/流程→提示→任务的覆盖表；不适用和延期逐项给理由 |
| MASTER-PLAN.md | 有依赖顺序的任务；输入、产物、验收、证据状态及上游任务引用 |
| manifest.json | 可验证的页面/提示/任务映射，供本地脚本检查，不是 MCP 请求体 |

页面合同的状态至少审查 normal/loading/empty/error/permission-denied/offline/partial-data；不适用要给业务理由。危险操作涉及 confirmation/pending/unknown/recovery 时不得遗漏。只描述本项目有依据的操作，不能为了填表添加删除、提交或重启权限。

流程必须完整到可观察结果：入口→前置检查→准备/编辑→确认（需要时）→执行→核验→成功/结果未知→恢复。普通读取和筛选不要机械增加批准门。

## Manifest v1

```json
{
  "version": "stitch-design-spec/v1",
  "sources": [{"id": "S1", "ref": "产品PRD.md#模块", "status": "confirmed"}],
  "pages": [{"id": "P01", "file": "pages/P01.md", "source_ids": ["S1"], "states": ["normal", "error"]}],
  "prompts": [{"id": "Q01", "file": "prompts/Q01.md", "page_id": "P01", "states": ["normal", "error"], "mode": "inline"}],
  "deferrals": [],
  "tasks": [{"id": "T01", "page_ids": ["P01"], "prompt_ids": ["Q01"], "depends_on": [], "acceptance": "错误重试保留筛选条件；返回列表保留位置"}]
}
```

所有 page states 必须被提示覆盖，或在 deferrals 中以 `page_id`、`state`、`reason` 逐项解释；延期不是完成。每页与每个提示须有任务。sources.ref 允许项目相对路径或正式 URL，不要求下载或打包全部上游文档。

applied-system 提示条目额外包含 `system: {project_id, id, evidence}`；执行器提供的证据不足时改为 inline 草案，不能填假 ID。targeted-edit 额外包含 `target` 和 `delta`。这些字段只说明设计交接，不自动成为远程参数。

## spec-only、模块单文件与 prompt-only

只要求规格时，交付 README、DESIGN-SPEC 与逐页合同（或同等内容单文件），并列明未进入提示编译阶段；不填空 prompt 冒充完整包。spec-only 不运行完整包校验器，按语义检查表验收。

full-stack-doc 模块文档沿用 `templates/module-stitch.md`：页面合同、导航/流程、提示、覆盖、任务都在同一文件，可引用已有模块 PRD/UI，避免再写整份产品需求。仅完整多文件包运行 manifest 脚本；模块和 prompt-only 走语义检查表，不伪称脚本验收。

prompt-only 输出元信息（目标/模式/来源/假设/未验证项）及一个三段提示。已有 spec 内容不足时保留原内容并列缺口，不把编辑请求扩成多页交付。
