# Task 5 Repository Change Report

## 完成情况

- 对应规格：`docs/superpowers/specs/2026-09-14-stitch-functional-closure-design.md` 的 Release 0.6.0 本地资产工具与可执行 Harness 要求。
- 版本状态：仓库清单与活跃版本面已升级为 `0.6.0` 本地候选；`v0.5.4` 仍明确标注为已发布基线。未 push、tag、创建 Release、升级 Marketplace 或执行真实远程写入。
- 本地 MCP 工具：新增 `stitch_local_upload_asset` 与 `stitch_local_download_assets`；工具名不覆盖 provider 工具，`tools/list` 暴露完整 schema/annotations，`tools/call` 在本地截获。
- 资产安全：上传要求绝对常规文件路径、支持的 HTML/图片类型、10 MiB 上限、官方 HTTPS origin、单次无重试写入与 ID-only 回执；下载要求绝对输出目录、contained subdir、Google HTTPS host allowlist、状态/Content-Type/单文件 25 MiB/总量 100 MiB 校验、私有临时文件、SHA-256 与原子目录发布，并导出 HTML、截图、可用 DESIGN.md 和 HTML 中允许的引用资源。
- Harness：新增 checked-in JSON Schema/starter template、`spec init` 非覆盖创建、六类类型化 evidence writer、隔离 Pillow `compare`、before/edited/restored HTML/render 六哈希 editability 门禁、显式 `RECONCILING`、三次未解上限、带原因的 `recover`，以及归档已发布但状态写入中断后的复验恢复。
- 既有安全门禁：保留 receipt step allowlist、链/hash 校验、显式用户批准、批准精确绑定、未知写不自动重试、凭据环境/受限配置链和官方 endpoint 限制。

## TDD 证据

- 第一轮 RED：`stitch_harness.assets` 与 `stitch_harness.evidence_writer` 不存在，9 项聚焦测试按预期失败；实现后 9/9 GREEN。
- 第二轮 RED：相对路径未被绝对路径规则拒绝、HTML 引用资产未导出、ImageGen writer 不接受尺寸参数；实现后 3/3 GREEN。
- 第三轮 RED：evidence writer 未拒绝带签名查询参数 URL；实现后 GREEN。
- 回归补充覆盖：代理本地工具发现/调用、SSE tool list、显式 reconciliation 状态、三次上限、恢复理由、compare 三图与布局 evidence、归档中断恢复。

## 测试和验证证据

- `python -m unittest discover -s tests -q`：162 tests，PASS。
- `python scripts/validate_distribution.py .`：43 Skills，compatibility distribution 0.6.0，PASS。
- `python scripts/validate_skills.py skills`：43 Skills，PASS。
- `python scripts/validate_markdown_links.py .`：PASS。
- `python scripts/scan_secrets.py .`：PASS。
- `python -m compileall -q scripts stitch_harness skills`：PASS。
- `python scripts/setup_harness_runtime.py check`：Pillow 12.3.0 isolated runtime ready。
- `python scripts/stitch_harness.py compare --help` 与 `python scripts/setup_harness_runtime.py run compare --help`：隔离入口及参数面 PASS。
- `git diff --check`：PASS。
- TRACE 自检：修改后的 `stitch-delivery-harness` 保留中文快速开始、三类能力边界、6 项主 FAQ、10 项深度 FAQ、10 项反模式、分层 references、隐私/授权/降级说明与可复制命令；T/R/A/C/E 各维均按 5.0 标准复核。

## 未完成与剩余风险

- 遵守任务“不得派生 subagent”约束，本任务未执行独立 subagent code review；需由控制器或独立审查者在最终候选合并前完成。
- 未执行真实 Stitch upload/download、真实 provider schema 变体、远端 CI、Windows/Linux 安装宿主或 live Canary；这些属于 Task 6。
- 下载器只追踪已下载 HTML 中的绝对 Google HTTPS `src`/`href`；相对 URL 无可靠远端基准，因此安全地不猜测、不下载。
- 0.6.0 仅是本地候选，不能据此宣称 GitHub Release、Marketplace 或安装来源已经更新。

## 当前规格状态

- Task 5 代码、单测、Skill 与本地分发候选：完成。
- 独立审查：待控制器。
- Task 6 live Canary、push/tag/Release/Marketplace/installed-source equality：未开始。

## Review Fix Round 1

- Critical 1：新增 `UnknownAssetWriteResult`。本地上传的 HTTP 408/5xx、断连、超时、截断、非 JSON/未知结构/重复 ID 均进入未知写入；MCP 转换为既有 `UnknownWriteResult`，stdio 返回 JSON-RPC `-32001`，notification 不返回响应。
- Critical 2：上传拒绝最终文件或任一祖先目录 symlink；支持 `dir_fd`/`O_NOFOLLOW` 的平台逐组件安全打开，否则先做完整 `lstat` 检查。文件只通过同一 descriptor 的 `fstat`/`read` 读取，限制 10 MiB 并检测读取期间大小变化。
- Critical 3：editability evidence 固定为 before/edited/restored HTML 与 before/edited/restored render 六个唯一 `semantic_role`，限定 MIME，result 哈希必须逐项等于已验证 artifact 哈希；edited 必须变化且 restored 必须与 before 完全相同。
- Critical 4：`compare` 不再接受 `--stitch`/`--art`。输入只从当前 run 已验证的 imagegen 与 stitch.roundtrip receipts 派生；visual evidence `source_artifacts` 和 visual receipt `inputs` 同时绑定两张源图。
- Important：新增 `reconcile --evidence`，支持三次上限前确认 `not_applied` 恢复原状态，或以完整 evidence 确认 `applied` 并推进门禁；local download 标记为本地写；所有 evidence 远程 URL 禁止 query/fragment；recovery/reconciliation reason 限长、单行并拒绝敏感内容；notification 成功/失败均静默；PageSpec 与 JSON Schema 对 additional properties、bool/int、非空 theme 及 archive 路径做差分对齐；archive 初次发布与中断恢复共用 source/published identity、spec、latest chain 和 approval-set verifier。
- Minor hardening：下载最多 100 screens/500 files，校验 PNG/JPEG/WEBP/SVG 内容魔数/结构；上传响应限制 JSON 与 100 results；三张 comparison 图片先写同文件系统私有 staging 目录，再整体原子发布。

### Review Fix TDD 与验证

- 第一批 RED 覆盖未知上传分类/`-32001`、symlink/safe-fd、本地写 annotations、图片魔数/数量上限和 notification；实现后 13/13 GREEN。
- 第二批 RED 覆盖六语义 editability、receipt-bound compare、reconciliation success、reason/URL、PageSpec/Schema、archive shared verifier 和 atomic comparison；实现后 13/13 GREEN。
- 完整回归：178 tests，PASS。
- 离线门禁：distribution 0.6.0、43 Skills、Markdown links、secret scan、compileall、Pillow 12.3.0 runtime、ShellCheck、actionlint、`git diff --check` 均 PASS。
- TRACE 复核：Trust 5.0、Reliability 5.0、Adaptability 5.0、Convention 5.0、Effectiveness 5.0；Skill 保持中文边界、安全/隐私、显式异常恢复、三层 references、6 项主 FAQ、10 项深度 FAQ、10 项反模式和可复制命令。
