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

## Review Fix Round 2

- Editability before binding：`before_html` 与 `before_render` 同时出现在六语义 artifacts 和 source artifacts，path/SHA/MIME 必须逐项等于已验证 `stitch.roundtrip` receipt 的 HTML/PNG outputs；editability receipt inputs 继续绑定这两项。
- Applied reconciliation crash consistency：新增原子多状态提交。完整 external evidence、真实 artifact、业务 gate 和三条 typed probes 均在持久化状态仍为 `RECONCILING` 时验证；随后追加 reconciliation/provider receipts，最后一次原子写入最终状态及 reconciliation metadata。若在 receipt 后崩溃，状态仍是 `RECONCILING`，重跑按当前 unknown→reconciliation→provider 相邻哈希链幂等提交，不重复 receipt。
- Typed read probes：`not_applied`/`applied` 均要求三个对象条目，工具精确为 `get_project`、`list_screens`、`get_screen`；每条包含带时区时间、唯一 response ID、枚举 status、result SHA 和唯一 run-local JSON artifact。artifact 必须存在、哈希相同、可解析且通过敏感检查，并写入 `reconciliation` receipt inputs/checks 后才允许恢复或推进。
- Sensitive recursion：所有 evidence dict/list 递归检查；键名包含 token/key/secret/password/credential/bearer/signature/sig 及既有 authorization/cookie/header/base64 均拒绝；文本包含 bearer/api-key/access_token/authorization 或任意嵌入 query/fragment URL 均拒绝。recover/reconciliation reason 使用同一 sanitizer，并额外限制单行和 500 字符。
- Retryable compare：仅 `EDITABILITY_VERIFIED` 且尚无已接受 visual receipt 时允许重跑。新三图先完整写入私有 staging，旧完整目录先原子备份；替换失败恢复旧目录。visual receipt 接受并推进状态后，CLI 在任何写入前拒绝覆盖。
- Round 2 TDD：首阶段 5 项 RED/GREEN 覆盖 editability receipt binding、敏感递归和 compare rollback；第二阶段 4 项 RED/GREEN 覆盖 typed probes、not_applied、applied 与 receipt 后崩溃；追加跨 unknown receipt 哈希绑定 RED/GREEN，防止误复用旧 reconciliation evidence。
- Round 2 完整验证：185 tests PASS；distribution 0.6.0、43 Skills、Markdown links、secret scan、compileall、Pillow 12.3.0 runtime、ShellCheck、actionlint 与 `git diff --check` 均 PASS。未执行远程写入或 Task 6 发布动作。

## Review Fix Round 3

- Probe artifact 逐字段绑定：每个 artifact 必须位于 run 内且路径组件无 symlink；同一份读取字节同时用于 SHA-256 与 UTF-8 JSON 解析。artifact 的 tool/invoked_at/response_id/status 必须精确等于声明，`result` 只能是布尔 `target_found`，`result_sha256` 必须等于其规范 JSON 哈希。
- 时序与结果互斥：三个 probe 时间都必须有时区且严格晚于当前最新 unknown-write receipt。`applied` 只接受三工具均 `found/true`；`not_applied` 只接受 project `found/true` 与 list/get screen `not_found/false`。陈旧、矛盾、重复、类型错误或未绑定证据均失败关闭。
- Receipt journal：append 先原子写 pending journal，再写 receipt，再更新 manifest，最后删除 journal。下一次 load 对 journal identity、receipt name/payload/hash、previous chain 做验证并完成提交。TDD 在 `pending-written`、`receipt-written`、`manifest-written` 三个边界注入崩溃，均恢复为单一有效 receipt 与有效链。
- 敏感词元：camelCase、snake_case、连字符和标点先规范化为独立词元；只匹配真实敏感 token/组合。`designTheme`、`keyboard_navigation`、`assignment`、`monkey` 允许；API key、access token、bearer、password、credential、signature 和带 query/fragment URL 拒绝。
- Compare receipt lock：CLI 在替换前检查通过的 `visual-judge` receipt；receipt 已写但状态提交中断时仍拒绝覆盖。未接受 receipt 时保留原子重试/回滚能力。
- CLI：probe tool/status 在集合操作前先完成类型校验；顶层捕获 `TypeError` 并返回 contract exit 2，不泄漏 traceback。
- Round 3 TDD：probe stale/exact/outcome/symlink/type、safe token normalization、journal 三边界、compare interrupted-state lock 均先观察 RED 后转 GREEN；完整回归当前为 191 tests PASS。

## Review Fix Round 4

- 原子 reconciliation 入口：首次 unknown write receipt 提交后，`RECONCILING`、`reconciliation_from`、`reconciliation_step` 与 `reconciliation_attempts=1` 通过同一次 manifest 原子替换持久化，不再存在状态已切换但恢复元数据缺失的窗口。
- 幂等中断恢复：若进程在 unknown receipt 已提交、reconciliation manifest 尚未提交时中断，重试会识别 manifest 当前链尾的同一步骤 unknown receipt，复用该 receipt 并完成原子状态提交，不重复写入 unknown receipt。
- crash/power-loss durability：所有关键 JSON 临时文件 rename 后 fsync 父目录；receipt journal 正常提交与恢复完成后的 unlink 也 fsync 父目录。覆盖 journal、receipt 与 manifest 三类转换。
- receipt sequence：pending journal 接受任意正整数序号，包括 `1000+`；后续追加从现有最大序号继续，receipt 遍历按数值序号排序，避免大序号恢复后回退或字典序破坏哈希链。
- Round 4 TDD：4 项新增用例先观察 RED，分别暴露缺失目录 fsync、1000 序号拒绝、reconciliation manifest 分裂提交和 unknown receipt 重复追加；实现后 4/4 GREEN。
- Round 4 验证：Task 5 state/orchestrator/v0.6.0 聚焦测试 45/45 PASS；完整回归 195/195 PASS；`python -m compileall -q stitch_harness tests` 与 `git diff --check` PASS。未执行远程写入或 Task 6 发布动作。
