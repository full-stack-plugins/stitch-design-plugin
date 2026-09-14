# 本地 Harness 验收控制器

[English](live-harness-controller.md) | [真实 smoke 台账](live-canary-acceptance.zh_CN.md)

这是完整 Delivery Harness 真实验收的独立交互式控制器路径。它不属于 GitHub provider + asset smoke，因为 workflow 手动触发不能替代用户对精确资产的明确人工批准。

## 前置条件

- 在新 Codex task 中使用全新安装的 0.6.1 候选，并证明 15 个 provider 工具与两个 namespaced 本地工具可见。
- 使用已批准范围内的临时 Stitch 项目，或创建带清理方案的唯一项目。
- 检查隔离 Harness runtime，凭据不得进入 argv：

```bash
python scripts/setup_harness_runtime.py check
```

## 交互式主链

1. 创建真实且不覆盖已有文件的页面规格：

```bash
python scripts/stitch_harness.py spec init --project /绝对路径/业务项目 --page-id live-canary
```

2. 启动 run，并按每次返回的 `next_action` 继续。Stitch generation、ImageGen、OCR/业务、roundtrip、editability 与视觉对比必须各自产生 run 目录下的真实 typed evidence；只能提交当前状态要求的 evidence：

```bash
python scripts/stitch_harness.py start --project /绝对路径/业务项目 --spec live-canary
python scripts/stitch_harness.py resume --project /绝对路径/业务项目 --run RUN_ID --evidence /绝对路径/run/evidence/STEP.json
python scripts/setup_harness_runtime.py run compare --project /绝对路径/业务项目 --run RUN_ID
```

3. 状态到达 `AWAITING_USER_APPROVAL` 后，向用户展示被接受的 HTML、render 与 comparison 精确资产哈希。只有用户此时明确人工批准后才能创建 confirmation；不得从 workflow dispatch、模型评分或 provider 成功状态推导批准：

```bash
python scripts/stitch_harness.py approve --project /绝对路径/业务项目 --run RUN_ID --confirmation /绝对路径/私有/approval.json
```

4. 只有状态为 `APPROVED` 才能 archive。验证返回归档后，再执行单独授权的远端项目清理：

```bash
python scripts/stitch_harness.py archive --project /绝对路径/业务项目 --run RUN_ID
python scripts/stitch_harness.py status --project /绝对路径/业务项目 --run RUN_ID
```

控制器私有记录必须保存候选 SHA、安装源等价性、run ID、receipt 链验证、精确批准资产集、归档哈希与清理证明。公共 Release Notes 只能包含脱敏布尔值、计数、哈希和时间戳。
