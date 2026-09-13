# Task 4 Repository Change Report

## 完成情况

- 对应规格或变更：`docs/superpowers/specs/2026-09-14-stitch-functional-closure-design.md` 的 0.5.2 发布候选与 CI/platform truth 仓库部分。
- 已实现内容：manifest、分发校验器、Harness MCP clientInfo、根路由版本说明及中英文状态文档统一到 0.5.2；README 明确区分已发布 v0.5.1 与 0.5.2 候选；新增 Ubuntu/macOS Python 3.11/3.13 离线矩阵，以及 Windows Python 3.11/3.13 单元/分发/编译和 stdio 代理启动 smoke。
- TDD 证据：新增版本与 workflow 契约测试先以 2 个预期失败进入 RED；补依赖安装契约时再次以缺少 `requirements-harness.txt` 安装步骤进入 RED；实现后聚焦测试与完整套件转为 GREEN。
- 未完成内容：未执行 global MCP 删除、push、tag、GitHub Release、Marketplace 升级、旧安装清理、全新任务或安装源等价性/真实四步读取验证。这些均由控制器负责。

## 测试和验证证据

- Python 3.13 隔离环境：`python -m unittest discover -s tests -q`，130 tests，PASS。
- 当前默认 Python 3.14 隔离环境：同一完整套件，130 tests，PASS。
- `python scripts/validate_distribution.py .`：43 Skills，compatibility distribution 0.5.2，PASS。
- 43 个 Skill 逐一运行 `quick_validate.py`：PASS。
- 全部仓库 shell 脚本 ShellCheck：PASS。
- `python -m compileall -q scripts stitch_harness skills`：PASS。
- `actionlint .github/workflows/validate.yml`：PASS。
- stdio proxy malformed-input launch smoke：返回 JSON-RPC `-32700`，PASS。
- 本地 Markdown 相对链接检查与 `git diff --check`：PASS。

## 兼容性与剩余风险

- Windows job 尚未在真实 GitHub-hosted Windows runner 上执行；两个需要符号链接权限的归档测试在 Windows 明确跳过，其他单元测试仍运行。
- workflow 文件仅完成本地 actionlint 和契约验证，远端 Actions 结果必须在 push 后观察，文档保持 `remote run unverified`。
- “独立审查”未执行：本任务明确禁止派生子代理，需由控制器或另一个独立审查者完成后才能关闭该发布门禁。
- 0.5.2 当前仅为仓库发布候选，不代表 tag、Release、Marketplace 或安装验证完成。

## 当前规格状态

- Task 4 仓库变更：完成并提交。
- Task 4 外部发布、安装、远端/实机验证：待控制器执行。

## Review Round 1 修复

- `.mcp.json` 改为调用仓库内 `scripts/stitch_mcp_launcher.js`。启动器在 Windows 优先 `py -3.11`、缺失时回退到 `python`，在 Unix 依次尝试 `python3`、`python`；stdio、SIGINT/SIGTERM 与子进程退出状态均被转发，凭据不进入 argv。
- Windows CI smoke 从 `.mcp.json` 读取并执行真实 `command`、`args` 和 `cwd`，不再绕过插件清单直接调用 Python 代理。
- 新增仓库内 `validate_skills.py`、`validate_markdown_links.py`、`scan_secrets.py`；Ubuntu、macOS、Windows job 均显式运行。Skill 校验使用固定版本 PyYAML 完整解析 frontmatter；秘密扫描覆盖 Google、GitHub、AWS、Slack、Stripe 和私钥高置信格式，并有检出/放行夹具。
- workflow 契约测试改为解析 YAML 并按 job/step/命令断言；中英文发布候选图明确区分已发布 v0.5.1 与本地 0.5.2 候选；英文凭据状态图移除遗留 `system store` 文案。
- Review Round 1 TDD：启动器、三个校验器、秘密正反夹具、workflow 结构、文档真实性测试均先观察到目标失败；补充退出/信号码和 Windows Python 回退时也分别完成 RED → GREEN。
- 最新验证：Python 3.13 隔离环境完整套件 139 tests PASS；0.5.2 分发、43 Skills、Markdown 链接、秘密扫描、compileall、Node syntax、actionlint、ShellCheck、`git diff --check` 全部 PASS。
- 仍待外部证据：GitHub-hosted Windows/macOS/Ubuntu workflow 实跑、安装宿主 Node/Python launcher smoke、独立审查，以及所有 push/tag/Release/Marketplace/安装等价性门禁。
