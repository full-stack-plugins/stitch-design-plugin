## ADDED Requirements

### Requirement: Visual scores SHALL be produced by an independent judge
视觉评分 MUST 由独立于执行者的产出者提供，且 MUST 以新鲜上下文运行；执行者 MUST NOT 兼任自身候选稿的裁判。

#### Scenario: Fresh-context judging
- **WHEN** 一轮候选稿需要评分
- **THEN** 裁判在全新上下文中运行，只接收目标参考、三张比较图与上一轮裁决，不接收执行者自己的诊断

#### Scenario: Executor cannot judge itself
- **WHEN** 执行者试图以自评结果充当本轮视觉评分
- **THEN** 该评分不被接受为视觉证据

### Requirement: The harness SHALL stay deterministic and offline-testable
交付 harness MUST 保持无大模型依赖、无密钥、可离线测试；视觉评分 MUST 以外部证据形式进入，MUST NOT 由 harness 内嵌调用模型产生。

#### Scenario: Offline harness run
- **WHEN** 在没有网络与密钥的环境中运行插件测试与 harness 命令
- **THEN** 确定性门禁、状态机与分发校验全部可用

#### Scenario: Scores arrive as external evidence
- **WHEN** 视觉评分被提交
- **THEN** 它以外部 evidence 的形式被校验与记录，而不是由 harness 内部生成

### Requirement: The scoring contract SHALL carry actionable gaps
视觉评分除各轴分数外 MUST 包含带稳定标识的 gap 清单，每个 gap MUST 可归因并可执行。

#### Scenario: Comprehensive verdict
- **WHEN** 候选稿与目标参考存在多处差距
- **THEN** 裁决列出每个 gap 的稳定标识、造成该观感的具体成因与修复方向，使另一执行者据此可实质改进

#### Scenario: Non-actionable feedback is rejected
- **WHEN** 裁决出现无法定位、无法执行的笼统描述
- **THEN** 契约校验失败，该裁决不被接受

#### Scenario: Stable ids enable comparison across rounds
- **WHEN** 连续两轮的裁决被比较
- **THEN** 相同的 gap 标识可被识别为同一个未解决问题

### Requirement: The judge SHALL NOT be pressured to raise scores
评分仲裁 MUST 采用反棘轮规则：裁判 MUST NOT 因一致性压力而提高分数，且 MUST 在候选稿回归时给出不低于前一轮的惩罚。

#### Scenario: Regression is scored lower
- **WHEN** 本轮候选稿相比前一轮出现视觉退化
- **THEN** 裁判给出更低的总分，而不是维持或提高分数

#### Scenario: Consistency without obligation
- **WHEN** 提供了上一轮裁决与截图
- **THEN** 裁判保持判断口径一致，但不受「必须不低于上一轮」的约束

### Requirement: Visual evidence SHALL record its true producer
视觉证据 MUST 如实标注产出者；外部裁判产生的分数 MUST NOT 被记录为确定性本地工具的输出；确定性布局分数 MUST 单独标注其算法与版本。

#### Scenario: Provenance of judge scores
- **WHEN** 检查包含外部评分的视觉证据
- **THEN** 其产出者字段指向真实裁判来源，而不是本地确定性工具

#### Scenario: Deterministic score is distinguished
- **WHEN** 视觉证据同时包含确定性布局分数与裁判分数
- **THEN** 两类分数的来源被分别标明，且布局分数携带算法名与版本

#### Scenario: Historical evidence stays readable
- **WHEN** 校验在本次变更之前生成的证据
- **THEN** 历史证据只读可审阅，不被重写或追溯篡改
