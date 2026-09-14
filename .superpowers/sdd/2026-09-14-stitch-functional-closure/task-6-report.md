# Task 6 Repository Preparation Report

## 完成情况

- 对应规格：`docs/superpowers/specs/2026-09-14-stitch-functional-closure-design.md` 的 manual live workflow、安全证据与清理仓库准备。
- 当前真实边界：`.github/workflows/live-canary.yml` 是 **Stitch provider + local asset smoke**，不是完整 Delivery Harness acceptance，不生成或推导自动用户批准。
- 完整 Harness 使用中英文 `docs/live-harness-controller*.md` 本地交互式控制器，要求真实 Stitch、ImageGen、OCR/业务、roundtrip、editability、comparison、明确人工批准与 archive receipts。
- 0.6.0 仍是本地候选；v0.5.4 仍是已发布基线。

## Provider + asset smoke 实现

- Workflow 唯一触发器为 `workflow_dispatch`，权限为 `contents: read`，不在 push、pull request 或 schedule 上运行。
- `STITCH_API_KEY` Repository Secret 只注入凭据预检、smoke 主链和最终清理步骤；checkout 使用 `persist-credentials: false`。
- `actions/checkout@v4` 与 `actions/setup-python@v5` 未在本任务中独立核验 immutable commit SHA，因此保留 major ref 并在验收文档中明确记录其可移动性。
- `StitchBackend` 执行 `initialize` → `notifications/initialized` → cursor-aware `tools/list`，通过现有 `ToolCatalog` repair/validation 要求精确 15 个 provider 工具与两个 namespaced local 工具。
- 统一响应解析要求 JSON-RPC 版本正确、响应 ID 类型和值精确匹配、无 `error`、结果为对象；工具调用还要求 `isError != true`、`structuredContent` 为对象以及逐工具输出合同通过。
- Provider 主链覆盖 create/generate/read/edit/one variant、design-system create/update/list/apply、本地 upload/download。屏幕和设计系统结果绑定私有状态中的精确 project/screen/asset 身份；variant 必须精确一个、属于同项目且身份不同于源屏幕；upload screens 必须非空且属于同项目。
- Create 结果不明时不重试，以唯一私有标题读取对账；只有精确一个合法匹配才保存身份，零个或多个匹配保持 unknown。

## 最终清理语义

- `project_title` 从创建前即保存于 `0600` 私有 state。即使 `project_name` 尚未落盘，最终 `always()` 清理仍可使用该唯一标题做有界只读对账。
- 默认最多三次读取、每次退避一秒；workflow 显式配置三次、两秒。参数限制为 1–5 次、0–10 秒，避免无界等待。
- 精确一个合法标题匹配时，先原子落盘 `project_name/project_id`，再落盘 `delete_attempted`，随后调用一次 `delete_project`。Create 与 delete 均无自动重试。
- 标题匹配为零或多个时保持 unknown、禁止删除并失败关闭。
- 删除成功、明确失败或 `UnknownWriteResult` 后都执行有界的完整 `list_projects` 不存在性探针；无法证明目标资源不存在时，公开 evidence 保持 `project_absent: false` 并使 acceptance 失败。

## Evidence 合同

- Opaque project/screen/design-system ID 只进入 runner 私有 state，不进入公开日志。
- Schema validation 只验证字段白名单与类型；acceptance validation 额外要求所有 stages 为 true、所有观测计数为正、下载清单 SHA-256 与完成时间存在、`delete_requested/project_absent` 均为 true。
- 公开 evidence 仅包含固定版本/范围、布尔值、非负计数、一个聚合 SHA-256 与 UTC 时间戳，不包含凭据、opaque ID、签名 URL、HTML 或截图。

## TDD 与验证证据

- RED 覆盖：缺少 initialized notification/分页目录/session seam；mismatched ID、JSON-RPC error、`isError`；unknown create 唯一/重复标题对账；unknown/失败 delete 后不存在性读取；创建身份未落盘时按私有标题恢复；零匹配禁止删除；跨项目 edit、空 upload；variant 复用源身份；schema/acceptance 混淆；checkout credential persistence；Harness 边界文档失真。
- Recording fake session 覆盖真实 `StitchBackend` 的完整 provider/asset stage chain、两页 17 工具目录、精确参数、输出合同、未知 create/delete 与身份约束。
- `python -m unittest tests.test_live_canary -v`：22/22 PASS。
- `python -m unittest discover -s tests -q`：217/217 PASS。
- `python scripts/validate_distribution.py .`：43 Skills，compatibility distribution 0.6.0，PASS。
- `python scripts/validate_skills.py skills`、Markdown links、secret scan、compileall、两份 workflow actionlint、ShellCheck 与 `git diff --check`：PASS。

## 未完成内容与剩余风险

- 未使用真实 Secret，未运行 GitHub workflow，未创建、修改或删除真实 Stitch 项目。
- 未执行完整 Delivery Harness acceptance、全新安装宿主工具暴露、独立审查或 source/install equality。
- 未 push、tag、创建 GitHub Release、升级 Marketplace 或安装插件。
- 真实 provider 返回结构、最终一致性窗口与 GitHub-hosted runner 行为仍须由控制器执行 smoke 后证明。
- 完整 Harness 的用户批准必须在 `AWAITING_USER_APPROVAL` 状态针对精确资产集人工作出；workflow dispatch 或 provider smoke 成功不能替代。

## 当前规格状态

- Task 6 仓库准备与 Fix Round 2：完成，待本提交落库。
- Provider + asset 真实 smoke、交互式 Harness acceptance、独立审查、远端发布与安装等价性：待控制器。

## Post-push Windows CI 修复

- 失败来源：GitHub Actions run `34796729100` 的 Windows job 执行 `_atomic_private_json` 时进入 POSIX `os.fchmod`；该调用在 `os.fdopen` 接管 descriptor 前失败，旧 `finally` 只尝试 unlink，未先关闭原始 fd，Windows 还会因打开句柄阻止临时文件清理。
- 修复：仅在 `os.name != "nt"` 时调用 `fchmod(0600)`；移除原子替换后的冗余 `chmod`。原始 descriptor 在所有前置权限/`fdopen` 异常路径中先显式关闭，再清理临时文件；正常路径由 `with stream` 在 `os.replace` 前关闭句柄。
- 平台隐私合同：POSIX 继续断言目标文件 mode `0600`；Windows 不模拟 POSIX mode bits，依赖当前用户 runner temp/profile ACL，同时完整执行原子写入、JSON 读取和敏感值不输出测试，无功能 skip。
- TDD：Windows 分支先因调用 `fchmod` RED；权限失败注入先证明 fd 泄漏 RED。最小实现后两项转 GREEN，Task 6 聚焦测试 22/22、完整套件 217/217 PASS。
- 版本保持 0.6.0 本地候选；未 tag、release 或执行其他远端写入。

## Post-push Windows CI 修复 Round 2

- 失败来源：GitHub Actions run `34797126039`。第一轮测试通过修改全局 `os.name` 模拟 Windows；Python 3.11 的 `pathlib.Path` 会根据该全局值选择路径实现，从而在 POSIX runner 上错误分派到 `WindowsPath`。真实 Windows 的 `os` 还可能根本没有 `fchmod`，因此 patch 缺失属性本身也不可靠。
- 修复：`_atomic_private_json` 增加仅供单元测试使用的窄 seam：`enforce_posix_mode` 与 `mode_setter`。生产调用不传参数，始终以真实 `os.name != "nt"` 决定是否设置 POSIX mode；只有需要设置 mode 时才解析默认 `os.fchmod`。
- Windows-like 测试在任意平台通过 `enforce_posix_mode=False` 执行完整原子 JSON 写入，并注入“若被调用即失败”的 setter；不修改 `os.name`。真实 Windows 同一测试还使用生产默认参数再次写入并验证敏感值不输出，因此无需 patch 缺失的 POSIX API。
- 权限失败测试通过 `enforce_posix_mode=True` 和注入的 raising setter 触发前置失败，继续验证 descriptor 已关闭、临时文件已删除；测试不再包含平台 skip。
- 验证：Task 6 聚焦测试 22/22、完整套件 217/217 PASS；其余 distribution/Skills/links/secret/compile/actionlint/ShellCheck/diff 门禁继续通过。
- 版本仍为 0.6.0 本地候选；未 tag、release 或执行远端写入。
