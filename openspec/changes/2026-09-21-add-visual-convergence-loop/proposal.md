## Why

`docs/superpowers/specs/2026-09-13-stitch-delivery-harness-design.md` 已经定义了收敛环：`J{收敛门禁}` 的 `未收敛 --> E` 回到 ImageGen 美术增强（第 76-78 行），「默认最多三轮美术增强与回灌」并在耗尽后进入 `BLOCKED`（第 83 行），以及 `ART_GENERATED --> BLOCKED: 美术门禁失败且无剩余轮次`（第 144-146 行）。

实现里这条环不存在，导致双图收敛门禁退化为一次性的单向检查：

- `stitch_harness/state.py:45` 的 `ART_ENHANCEMENT_APPROVED` 只允许去往 `ART_GENERATED`/`RECONCILING`/`BLOCKED`，全图没有任何回边指向美术增强。
- `stitch_harness/orchestrator.py:267` 的 `_target_states[ART_ENHANCEMENT_APPROVED]` 固定为 `(ART_GENERATED,)`，且它是唯一的状态推进授权（只被 `_commit_evidence` 调用）。
- 全仓不存在轮次计数器：唯一的计数是 `reconciliation_attempts`，服务于远程写入不确定的对账，与交付轮次无关。
- 全图唯一一条后退边是 `state.py:53` 的 `AWAITING_USER_APPROVAL -> ART_GENERATED`（用户否决候选稿）。实测该边无法完成第二圈：第一轮 `visual-judge` receipt 通过后，`cli.py:101` 的 `has_accepted_receipt()`（`storage.py:436`，扫描整个 run 的 receipt，只匹配 step 与 passed）会永久锁死该步骤，第二轮在 `EDITABILITY_VERIFIED` 调用 `compare` 时以退出码 2 失败，报 `compare cannot overwrite an accepted visual-judge receipt`。

同时，9.4 收敛门禁的评分生产者从未存在：

- `stitch_harness/visual_gate.py:93` 的 `validate_visual_scores()` 是评分**消费者**（校验 `hierarchy`/`density`/`color`/`component_quality`/`completion` 五轴、每轴 1-5 分、须不低于 `comparison.visual_quality_score_min`），但没有任何模块产出这些分数。
- `stitch-delivery-harness` 技能第 30 行把「视觉评估工具」列为必需素材，插件并不随附该工具；`imagegen` 同样只有 `NextAction` 与 evidence 步骤名，没有实现。
- `stitch_harness/cli.py:31` 的 `--scores` 是可选参数，缺省时 `cli.py:110` 写入 `scores: {}` 并返回退出码 0，失败被推迟到下一步 `resume` 才暴露。
- `stitch_harness/evidence_writer.py:145` 的 `visual_review()` 沿用 `_write()` 的默认值，把该步证据记为 `{"name": "local-harness", "tool": "compare", "model": "deterministic"}`，而五轴分数实际是从外部 `--scores` 文件逐字读入的，即 receipt 链把外部判断记录成了确定性本地工具的输出。

结果是：交付流程既不能迭代收敛，也没有可用的收敛判据，且现有证据出处与真实产出者不符。

## What Changes

- 恢复设计已定义但未实现的收敛回边，并引入受上限约束的交付轮次计数：未收敛且仍有预算时可回到美术增强重做，预算耗尽仍未收敛则进入 `BLOCKED` 并等待用户决定。
- 把重新比较的保护范围从「整个 run 的 `visual-judge` 步骤」收窄为「本轮被接受的产物」，使第二圈及以后可以合法地重新比较，同时继续阻止同一组产物被重复覆盖。
- 让评分证据必须完整才可提交：比较环节缺分即失败，不再产出可提交的空评分证据。
- 新增插件本地裁判技能，产出五轴分数与带稳定标识的可执行 gap 清单；harness 保持纯确定性、无 LLM 依赖、离线可测，评分仍以外部 evidence 形式进入。
- 让视觉证据如实标注产出者：外部裁判分数不得再被记为本地确定性工具输出，确定性布局分数单独标注算法与版本。
- 定义收敛判据：stall（连续两轮无实质提升，或裁判连续两轮指出同一 gap）要求结构性重做；结构性重做无效即停止并交回用户；门禁通过即收敛，但永不替代用户批准。
- 将轮次上限做成页面规格中的可选配置，缺省为 3，并同步契约层、schema、模板与测试。

## Capabilities

### New Capabilities

- `visual-convergence-loop`: 约束交付轮次、未收敛回边、重新比较边界、评分证据完整性与收敛/停止判据的可观察契约。
- `independent-visual-judge`: 约束视觉评分的产出者独立性、评分契约、可执行 gap 清单、反棘轮规则与证据出处如实性。

### Modified Capabilities

无。既有 `cross-host-plugin-identity`、`host-runtime-loading`、`immutable-skill-supply-chain` 三个能力的契约不变；本变更不触碰受管技能、供应链与宿主身份语义。

## Impact

影响 `stitch_harness/state.py`、`orchestrator.py`、`cli.py`、`storage.py`、`evidence_writer.py`、`contracts.py`、`spec.schema.json`、`spec-template.json`，新增一个插件本地技能（须登记进 `plugin-local-skills.json`），以及 `tests/` 中状态机、视觉门禁与分发相关用例。

`stitch-delivery-harness` 与 `stitch-loop` 为 vendored 技能（锁摘要 + 在线校验双重冻结），本变更不修改其内容；与之相关的文字对齐需要在上游 `full-stack-skills/stitch-skills` 另开变更并发版，本变更记录该依赖但不阻塞于此。

`imagegen` 与真实 Stitch 调用仍由宿主或外部工具提供，本变更不改变其边界，也不新增任何图像内容理解能力。
