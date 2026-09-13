# Stitch Design 0.6.0 真实 Smoke 验收

> 仓库准备：已完成
>
> Provider + asset 真实 smoke：未执行
>
> Harness 验收：未执行
>
> Release/Marketplace：未发布

[English](live-canary-acceptance.md) | [Harness 控制器](live-harness-controller.zh_CN.md) | [架构文档](Stitch-Design-Architecture.zh_CN.md)

本台账把两个外部门禁明确分开。手动 GitHub workflow 是有界 Google Stitch provider + 本地资产 smoke；它不是 Harness 验收，也不会伪造自动用户批准。完整 Delivery Harness 必须走本地交互式控制器路径。

## 已准备的 provider + asset smoke

`Live Provider and Asset Smoke` workflow（`live-canary.yml`）只有 `workflow_dispatch` 触发器，只从同名 Repository Secret 读取 `STITCH_API_KEY`，并创建唯一标题的临时项目。

```mermaid
flowchart LR
    Dispatch["手动触发"] --> Protocol["initialize · initialized · 分页 tools/list"]
    Protocol --> Catalog["15 个 provider + 2 个本地工具"]
    Catalog --> Project["唯一临时项目"]
    Project --> Screen["生成 · 读取 · 编辑 · 单一变体"]
    Screen --> System["创建 · 更新 · 列出 · 应用设计系统"]
    System --> Assets["上传 · 校验下载"]
    Assets --> Cleanup["always：单次删除 · 读取不存在性"]
```

真实 backend 要求 JSON-RPC ID 精确匹配、无 JSON-RPC error、`isError != true`、结构化工具内容以及逐工具输出合同。每个屏幕和资产结果都绑定私有状态中的精确项目、屏幕或设计系统身份。项目创建结果不明时，只读列出项目并且只接受唯一一个标题精确相等的结果；零个或多个匹配都不会写入项目身份。

Opaque ID 仅保存在 runner 内 `0600` 私有文件且不上传。公开 evidence 使用精确 schema，仅包含布尔值、验收所需正数计数、一个聚合 SHA-256 和 UTC 时间戳。schema 校验与 acceptance 校验相互独立：结构合法的部分 evidence 不等于 smoke 已验收。

最后一个 `always()` 步骤是唯一删除入口。如果尚未落盘 `project_name`，清理会使用私有唯一 `project_title`，以两秒退避最多执行三次只读对账。只有精确一个合法匹配才先落盘身份再执行一次删除；零个或多个匹配都保持 unknown 并失败关闭。删除尝试先落盘且不重放。无论删除成功、失败还是结果不明，都用有界的新 `list_projects` 探针证明精确项目资源不存在；无法证明时保留 `project_absent: false` 并让验收失败。

`actions/checkout@v4` 与 `actions/setup-python@v5` 仍是可移动 major-version 引用，因为本次仓库准备没有独立核验其不可变 commit SHA。checkout 已设置 `persist-credentials: false`；控制器应在把 action 来源作为发布证据前，将其固定到独立核验的 SHA。

## 独立 Harness 门禁

provider smoke 通过后，从已安装的 0.6.0 候选执行[本地 Harness 控制器](live-harness-controller.zh_CN.md)。该路径必须取得真实 Stitch、ImageGen、OCR/业务、roundtrip、editability、comparison、明确人工批准及 archive receipts。手动触发 workflow 或 provider smoke 通过都不等于用户明确批准 Harness 资产。

## 验收台账

| 门禁 | 当前结果 | 所需证据 |
|:---|:---|:---|
| 仅手动触发与 Secret 范围 | 已完成离线准备 | workflow 测试 + actionlint |
| MCP 生命周期与精确 17 工具目录 | recording fake 已准备 | 真实匹配响应 |
| Provider 生成/读取/编辑/单一变体 | 待真实 smoke | 一个同项目且不同于源屏幕身份的变体 |
| 设计系统创建/更新/列出/应用 | 待真实 smoke | 身份绑定结果；计数为正 |
| 本地上传/下载 | 待真实 smoke | 正数计数 + 下载清单哈希 |
| 删除并证明不存在 | 待真实 smoke | `delete_requested` 与 `project_absent` 均为 true |
| 完整 Delivery Harness | 待本地控制器 | 真实 receipts + 明确人工批准 + 已验证归档 |
| 0.6.0 标签/Release/Marketplace/安装 | 未发布 | 精确源码/远端/标签/Release/安装源等价性 |

所有适用门禁关闭前，0.6.0 仍是本地候选，v0.5.4 仍是已发布基线。
