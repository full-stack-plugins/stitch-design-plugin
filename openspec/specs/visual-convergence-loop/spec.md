# visual-convergence-loop Specification

## Purpose
TBD - created by archiving change 2026-09-21-add-visual-convergence-loop. Update Purpose after archive.
## Requirements
### Requirement: Non-converged candidates SHALL be reworkable within budget
交付流程 MUST 在自动门禁未通过且轮次预算未耗尽时，允许候选稿回到美术增强重做，并使该回边成为状态机中真实存在的合法转移。

#### Scenario: Gates fail while budget remains
- **WHEN** 双图收敛门禁或其他自动门禁未通过，且交付轮次预算仍有剩余
- **THEN** 运行可以回到 `ART_ENHANCEMENT_APPROVED`，本轮轮次被计入，且此前各轮的 receipts 与产物全部保留

#### Scenario: Return edge bypasses no gate
- **WHEN** 运行经回边回到美术增强
- **THEN** 其后的业务断言、OCR、语义规范化、回灌与可编辑性探针整体重新执行，不得复用上一轮的通过结论

#### Scenario: Budget exhausted
- **WHEN** 轮次预算耗尽而仍未收敛
- **THEN** 运行进入 `BLOCKED`，保留全部证据并等待用户决定，且不得自行扩大预算

### Requirement: Delivery rounds SHALL be bounded and configurable
交付轮次 MUST 有上限，上限 MUST 可在页面规格中声明，且 MUST 有确定缺省值；轮次计数 MUST 与远程写入对账计数相互独立。

#### Scenario: Spec omits the ceiling
- **WHEN** 页面规格未声明轮次上限
- **THEN** 使用缺省上限 3

#### Scenario: Counter is not shared with reconciliation
- **WHEN** 运行经历了远程写入不确定的对账
- **THEN** 交付轮次计数不受对账次数影响，反之亦然

### Requirement: Re-comparison SHALL be scoped to the current round
视觉比较的覆盖保护 MUST 以本轮被接受的比较产物为界；产物变化时 MUST 允许重新比较，产物未变时 MUST 拒绝覆盖既有通过的比较结果。

#### Scenario: New artifacts after a rework round
- **WHEN** 回到美术增强重做后产生了新的美术稿或新的回灌产物
- **THEN** 比较环节可以再次执行，不会被此前的通过记录阻断

#### Scenario: Same artifacts are re-compared
- **WHEN** 请求比较的产物与已通过记录所绑定的产物完全一致
- **THEN** 比较以非零状态拒绝，既有结论不被覆盖

### Requirement: Incomplete scores SHALL fail the comparison step
比较环节 MUST 在评分不完整时立即失败，MUST NOT 产出可提交的不完整评分证据。

#### Scenario: Scores are missing
- **WHEN** 未提供评分或其内容缺少必需轴
- **THEN** 比较命令以非零状态失败并指出缺失项，且不生成可提交的 `visual-judge` 证据

#### Scenario: Success implies a satisfiable gate
- **WHEN** 比较命令返回成功
- **THEN** 其产出的评分证据已满足收敛门禁对分数完整性的要求

### Requirement: Convergence and stopping SHALL be decidable from round history
收敛判定 MUST 基于轮次历史；停滞 MUST 有可计算判据并导致结构性重做要求；停滞在结构性重做后仍持续时 MUST 停止并交回用户。

#### Scenario: Progress stalls
- **WHEN** 连续两轮的视觉总分未提升满 1 分，或裁判连续两轮指出同一 gap 标识
- **THEN** 运行被标记为停滞，且不得以递增微调继续消耗轮次

#### Scenario: Structural rework does not help
- **WHEN** 按停滞判据执行结构性重做后分数仍未提升
- **THEN** 流程停止并交回用户决定，不再自动继续

#### Scenario: Converged
- **WHEN** 全部自动门禁通过且未触发停滞判据
- **THEN** 判定为收敛并进入等待用户批准，且该判定不构成用户批准

#### Scenario: Convergence never replaces approval
- **WHEN** 收敛判定为真
- **THEN** 仍需用户明确批准才可 `approve` 或 `archive`

