# Task 6 Repository Preparation Report

## 完成情况

- 对应规格：`docs/superpowers/specs/2026-09-14-stitch-functional-closure-design.md` 的 CI/platform truth 与 controlled live acceptance 仓库准备部分。
- 已新增 `.github/workflows/live-canary.yml`：唯一触发器为 `workflow_dispatch`，权限仅 `contents: read`，不在 push、pull request 或 schedule 上运行。
- Repository Secret `STITCH_API_KEY` 只注入凭据预检、Canary 主链和最终清理三个必要步骤；checkout、Python setup、依赖安装与 evidence 静态验证不继承 Secret。
- 已新增 `scripts/live_canary.py`：创建 UTC + 随机 nonce 命名的唯一临时项目；按生成、读取、编辑、单一变体、设计系统创建/更新/列出/应用、本地上传/下载、Harness `compare_images` 对比和私有 Canary 归档顺序执行；非幂等写入不在脚本内自动重试。
- Opaque 项目/屏幕/设计系统 ID 仅保存到 runner 内 `0600` 私有 state；公开 evidence 使用精确字段白名单，只包含状态布尔值、非负计数、SHA-256 与 UTC 时间戳。
- workflow 的最后一个步骤固定为 `if: ${{ always() }}` 清理。删除前原子持久化 `delete_attempted`，只调用一次 `delete_project`，随后完整读取 `list_projects` 并按精确资源名证明不存在；返回不完整或目标仍存在时失败关闭。
- 已新增中英文 `docs/live-canary-acceptance*.md` 验收台账，并同步 README、架构和技术方案。所有公开文档继续声明 0.6.0 为本地候选、v0.5.4 为已发布基线。

## TDD 证据

- 第一轮 RED：新增 4 项测试时，`live-canary.yml` 与 `live_canary.py` 尚不存在，4 项按预期报错失败；实现后转为 GREEN。
- 文档 RED：中英文验收台账不存在，候选/未执行/未发布真实性测试按预期失败；补文档后转为 GREEN。
- Secret 最小暴露 RED：测试指出 job 级 Secret 会被无关 actions 继承；改为三个必要 step 局部注入后转为 GREEN。
- evidence 白名单 RED：在 `stages` 中注入 `project_id` 时旧校验错误放行；改为嵌套字段精确白名单后转为 GREEN。
- fake backend 覆盖完整顺序、唯一项目名、私有 state 权限、去标识化 evidence、单次删除与只读不存在性确认；未连接真实 Stitch，也未读取真实 Secret。

## 测试和验证证据

- `python -m unittest tests.test_live_canary -v`：6/6 PASS。
- `python -m unittest discover -s tests -v`：201/201 PASS。
- `actionlint .github/workflows/live-canary.yml .github/workflows/validate.yml`：PASS。
- `python scripts/validate_distribution.py .`：43 Skills，compatibility distribution 0.6.0，PASS。
- `python scripts/validate_skills.py skills`：43 Skills，PASS。
- `python scripts/validate_markdown_links.py .`：PASS。
- `python scripts/scan_secrets.py .`：PASS。
- `python -m compileall -q scripts stitch_harness tests`：PASS。
- `git diff --check`：PASS。

## 未完成内容

- 未运行 GitHub Actions live Canary、未使用真实 Secret、未创建或删除真实远端项目。
- 未执行本地 0.6.0 Marketplace 安装或全新 Codex task 工具暴露检查。
- workflow 仓库准备验证了 Harness 的真实 `compare_images` 引擎与私有 Canary archive 路径；它不是完整 Delivery Harness 状态机的 ImageGen/OCR/显式人工批准闭环。控制器仍须在真实安装宿主完成规格要求的完整 Harness acceptance，不能用本报告替代。
- 未执行独立审查（任务禁止派生 subagent）；由控制器或独立审查者完成。
- 未 push、tag、创建 GitHub Release、升级 Marketplace、安装插件或验证 source/remote/tag/release/install SHA 等价性。

## 兼容性与剩余风险

- 真实 Stitch 返回结构与当前已验证 tool contract 一致性只能由 live run 证明；workflow 对畸形响应、未知写入、下载无有效资产、无法找到两张同尺寸 render 等情况均失败关闭。
- `generate_variants` 当前 live schema 不暴露 `variantCount`；脚本要求供应商结果精确返回一个 variant，否则失败，避免把多个变体误记为单一变体验收。
- 清理删除响应不明时不会自动重发。若 `delete_attempted=true` 且只读确认仍发现目标，workflow 失败，需要维护者按私有 state/远端账号人工核查。
- Windows 仍是代码路径；本次 live workflow 只配置 Ubuntu runner，不改变 Windows 实机未验收状态。

## 当前规格状态

- Task 6 仓库准备：完成，待本提交落库。
- Task 6 live Canary、完整安装宿主/Harness 验收、独立审查、远端 CI 与 0.6.0 发布：待控制器。
