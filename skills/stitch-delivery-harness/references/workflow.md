# Harness 工作流

## 固定顺序

页面规格 → Stitch 生成 → HTML/尺寸/文案验收 → ImageGen 美术增强 → OCR/业务门禁 → 回灌 Stitch → 可编辑性验证 → 双图对比 → 用户批准 → 正式归档。

## 执行协议

1. `preflight` 检查系统凭据、唯一插件来源和本地运行条件。
2. `start` 创建不可复用的 run，返回 `stitch.generate`。
3. 每次真实工具调用后，将文件放入当前 run 的 `artifacts/`，再创建 evidence JSON。
4. `resume` 校验文件哈希、门禁与状态，只返回一个下一动作。
5. Stitch 写操作结果未知时，保存 `result: "unknown"` 并进入 `RECONCILING`；随后只执行 `get_project`、`list_screens` 或 `get_screen`。每次未解对账递增 attempts，第三次转为 `BLOCKED`。
6. ImageGen 结果先过尺寸、OCR 和业务断言，不通过不回灌。
7. 回灌结果必须含重新下载的 HTML 和渲染图。探针编辑需保存 before/edited/restored 三份 HTML 与三张 render；edited 哈希必须变化，restored HTML/render 哈希必须分别与 before 完全相等。
8. 双图阶段生成 `side-by-side.png`、`overlay.png`、`diff-heatmap.png`；布局分数和五个视觉维度通过后进入 `AWAITING_USER_APPROVAL`。
9. 用户批准文件必须绑定本次所见 HTML、两张最终图和比较图哈希；文件变化会使批准失效。
10. `archive` 只接受 `APPROVED`。若移动对话中已经引用的图片，必须保留可读的相对软连接。
11. 若 archive 已完成原子发布、但 run 状态持久化中断，重新执行同一 `archive --run`；Harness 先复验已发布收据链、批准和哈希，再只补写 `ARCHIVED` 状态。

## 可执行命令

```bash
python scripts/stitch_harness.py spec init --project /absolute/project --page-id login
python scripts/stitch_harness.py status --project /absolute/project --run RUN_ID
python scripts/setup_harness_runtime.py run compare --project /absolute/project --run RUN_ID --stitch /absolute/stitch.png --art /absolute/art.png --scores /absolute/scores.json
python scripts/stitch_harness.py recover --project /absolute/project --run RUN_ID --reason "只读探针确认远程写入未生效"
python scripts/stitch_harness.py archive --project /absolute/project --run RUN_ID
```

## 状态语义

`passed` 表示对应机器门禁和 receipt 同时有效；`failed` 表示结果明确不合格；`RECONCILING` 表示远程写入结果不确定且只允许读探针；`BLOCKED` 表示三次未解或不能在现有授权内继续。禁止把后两者改写为成功。
