## Context

参见 `proposal.md`。本变更要补齐的不是新想法：收敛环与轮次上限在 `docs/superpowers/specs/2026-09-13-stitch-delivery-harness-design.md` 已有定义，本变更是把它落成实现，并为 9.4 门禁补上缺失的评分产出者。

外部参考为 `achimala/dream-loop`（MIT，Copyright 2026 Anshu Chimala）的裁判协议与退出纪律。本变更只借鉴协议，不引入其依赖、不复制其正文、不采用其评分轴。

## Goals / Non-Goals

**Goals:**

- 让「未收敛就重做」成为状态机里真实存在、有预算、可审计的一条边。
- 让收敛与停止有明确判据，避免无限循环，也避免把「没收敛」当作「已完成」。
- 让视觉评分有明确的独立产出者，且证据如实标注真实来源。
- 保持 harness 纯确定性：无 LLM 依赖、无 API key、离线可测。

**Non-Goals:**

- 不引入 dream-loop 作为运行时依赖，不复制其文档正文，不采用其 3D 渲染评分轴（composition/lighting/materials/details）。
- 不新增像素级视觉门禁或图像内容理解能力。`compare_images()` 只能给出确定性布局分数，本变更不承诺度量「好不好看」。
- 不修改 `keep_stitch` 分支。该分支没有对照的美术稿，`store.required_comparison_artifacts()` 无法凑出比较对象，为其增加门禁属于新能力。
- 不修改 vendored 的 `stitch-delivery-harness` 与 `stitch-loop` 技能内容。
- 不改变批准语义：裁判分数、OCR 与任何自动门禁都不得替代用户明确批准。
- 不做后台自主运行、无限迭代或自动部署。

## Decisions

1. **回边落到 `ART_ENHANCEMENT_APPROVED`。** 与设计文档的 `未收敛 --> E` 一致。每轮消耗一次轮次预算，且必须产生新的 `imagegen` receipt。若失配出在回灌侧，允许复用同一美术稿（哈希不变），由执行者判断，状态机不为「只重灌」另开一条边——那会把状态空间翻倍，而 `ART_ACCEPTED -> SEMANTIC_NORMALIZED -> ROUNDTRIPPED` 已经能表达重灌本身。

2. **轮次计数器与 `reconciliation_attempts` 分开。** 后者表达「远程写入结果不确定」，本变更是「视觉未收敛」，两者的语义、上限、耗尽后果都不同，复用同一个计数器会让对账语义被交付轮次污染。新增独立的 manifest 字段表达交付轮次。

3. **轮次上限放在 `comparison` 内，作为可选字段，缺省 3。** `comparison` 已经是「比较与收敛阈值」的容器（现有三个字段都是这块的门禁阈值），把上限放在这里无需新增顶层字段。字段可选并带默认值，既有 spec 无需迁移，`schema_version` 保持 1。

4. **重新比较的保护改为按本轮产物绑定。** 现有实现扫描整个 run 的 `visual-judge` receipt，意图是「同一组比较产物不得被重复覆盖」，但副作用是第二圈永久不可比较（实测退出码 2）。改为绑定本轮被接受的 art 与 roundtrip 产物哈希：产物变了就允许重新比较，产物没变则继续拒绝覆盖。这既修掉了死角，也保留了原本的保护意图。

5. **评分产出者是一个插件本地技能，而不是 harness 内的 LLM 调用。** harness 的既有约束是纯确定性、无密钥、离线可测（`requirements-harness.txt` 仅含 Pillow）。因此裁判以外部工具身份运行、产出 `scores.json`，再由 harness 作为外部 evidence 接收。这样既不破坏离线可测性，也天然满足「裁判必须独立于执行者」。

6. **保留既有五轴，不采用 dream-loop 的轴。** 五轴（层级、密度、色彩、组件质感、完成度）已是 UI 交付语义且已被 `comparison.visual_quality_score_min` 门禁强制；dream-loop 的四轴是 3D 渲染画面语义（反射、材质、湿润感、镜头），搬到 UI 会引入不可度量指标。移植的是裁判协议：新鲜上下文、可执行的 gap 清单、反棘轮、与上轮裁决保持一致但不受其约束。

7. **gap 需要稳定标识。** 「裁判连续两轮指出同一个 gap」这一 stall 判据要求 gap 可比较，因此评分契约除分数外必须包含带稳定 id 的 gap 列表。这是 stall 检测可计算的前提，不是可选的附加信息。

8. **stall 的量化口径。** stall = 连续两轮五轴总分未提升满 1 分，或裁判连续两轮给出同一 gap id。该口径直接取自 dream-loop 的退出条件，但落到本仓可计算的形式（总分与 gap id 都在评分契约里）。判定为 stall 后禁止小修小补，要求结构性重做；结构性重做后仍无提升即停止并交回用户，不再消耗轮次。

9. **收敛不等于批准。** 「收敛」= 全部自动门禁通过且未触发 stall；它只决定是否继续迭代，进入用户批准仍是既有语义。dream-loop 的「完成」概念在此被刻意弱化，以免与 approvals 冲突。

10. **证据出处如实化的最小改法。** 不为视觉环节新增 receipt step（那会牵动 `RECEIPT_STEPS`、`EXPECTED_RECEIPT_STEP` 与批准产物集合），而是在既有 `visual-judge` evidence 内区分来源：该步的执行者记为真实裁判（provider/model 必填），确定性布局分数在 `result` 内单独标注算法与版本。读取侧对旧 evidence 保持容忍，只读不重写。

11. **缺分即失败。** 比较环节在评分不完整时以非零状态失败，不再写出 `scores: {}` 的可提交证据。这消除「命令成功但门禁必然失败」的假成功。

## Risks / Trade-offs

- [回边引入无限循环] → 轮次上限是硬约束，耗尽即 `BLOCKED`；文档与测试同时禁止自行扩轮。
- [裁判与执行者同体，自评导致分数漂移] → 裁判必须新鲜上下文、不得兼任执行者，且不接收执行者自己的诊断；反棘轮规则禁止因压力涨分，回归必须给出更低分。
- [改锁会削弱第一轮既有保护] → 保护意图保留为「同一组产物不得被重复覆盖」，并补齐当前完全缺失的回归测试（现有 `tests/` 中没有任何用例覆盖该锁）。
- [新增契约字段破坏已发布 spec] → 可选 + 默认值 + `schema_version` 保持 1；`contracts.py` 允许键、`spec.schema.json`、`spec-template.json` 与 `tests/test_harness_contracts.py` 必须同批更新，因为 schema 两层都是 `additionalProperties: false`。
- [证据出处改必填破坏既有 evidence] → 既有 run 的 evidence 只读不重写；新证据必填；读取与校验对旧文件保持宽容。
- [轮次与重试让状态机测试面扩大] → `tests/test_harness_orchestrator.py`、`test_harness_v060.py`、`test_visual_gate.py` 中与状态推进和评分相关的断言需同步更新，并新增回边、上限耗尽、按轮次重比、stall 三类回归用例。
- [仓库强制发版] → 按 `AGENTS.md`，任何改动都要 bump 版本并同步市场仓；冻结技能的文字对齐只能走上游发版，本变更不等待它。

## Migration Plan

1. 状态机与契约：加入回边、交付轮次计数与上限、`comparison` 新增可选字段，同步 schema 与模板。
2. 比较边界：把 `visual-judge` 的保护改为按本轮产物绑定，并让缺分快速失败。
3. 裁判：新增插件本地裁判技能并登记进 `plugin-local-skills.json`；落地评分契约（五轴分数 + gap id + 上轮对比结论）。
4. 证据出处：`visual_review()` 记录真实产出者，确定性布局分数标注算法与版本。
5. 收敛判据：stall 判定、结构性重做要求、停止与交回用户的退出路径。
6. 验证：插件测试、分发校验、离线与在线技能完整性检查、strict OpenSpec 校验。
7. 发布：bump 版本、提交并确认 CI、创建不可变 tag 与 Release、同步市场目录。
8. 上游：在 `full-stack-skills/stitch-skills` 另开变更，把收敛环与裁判协议落到两个冻结技能的文字中并发布新版本，随后按既有同步流程更新锁文件与摘要。此步独立于本变更的落地，不阻塞第 1-7 步。
