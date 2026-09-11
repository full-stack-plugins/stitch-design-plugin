# Stitch Design for Codex

`stitch-design` v0.3.0 封装 Google Stitch 远程 MCP 与 39 个设计、设计系统、代码导入和设计转前端 Skills。Codex 展示名称为 **Stitch Design**。插件仓库：[partme-ai/codex-stitch-plugin](https://github.com/partme-ai/codex-stitch-plugin)；技能主干来源：[Full Stack Skills / PartMe.AI](https://github.com/full-stack-skills/stitch-skills)。

## 从 GitHub 安装

将仓库 marketplace 添加到 Codex，然后安装插件：

```bash
codex plugin marketplace add partme-ai/codex-stitch-plugin --ref main
codex plugin add stitch-design@partme-ai-stitch
```

升级仓库 marketplace 后重新安装插件，并在新的 Codex 任务中验证：

```bash
codex plugin marketplace upgrade partme-ai-stitch
codex plugin add stitch-design@partme-ai-stitch
```

仓库发布版使用稳定 SemVer。个人 marketplace 开发时产生的 `+codex.<cachebuster>` 仅用于刷新本地安装缓存，不属于 GitHub 发布版本。

## 凭据与启动

1. 登录 [Stitch](https://stitch.withgoogle.com)，在 Stitch Settings 中创建 API key。密钥泄露或不再使用时，在同一设置页面吊销；轮换时创建新密钥、更新运行环境，再吊销旧密钥。
2. 通过本机凭据管理器或启动环境设置 `STITCH_API_KEY`。不要把真实值写入插件、配置文件、命令行参数、聊天或日志。交互式 zsh 可使用隐藏输入，避免把值写进 shell 历史：

   ```zsh
   read -rs 'STITCH_API_KEY?Stitch API key (hidden): '
   export STITCH_API_KEY
   ```

3. 确保实际启动 Codex 的进程继承该环境变量；在终端设置变量不会自动更新已运行的桌面应用环境。安装或更新插件后，重启 Codex 并新建任务加载配置和 Skills。
4. 在新任务中先执行只读验证：要求列出当前账号的 Stitch 项目（`list_projects`）。记录实际工具名和成功/失败状态，不打印请求头、凭据或完整私人项目数据。成功响应可能为空项目列表，不应为测试创建项目。

`.mcp.json` 把 `X-Goog-Api-Key` 映射到环境变量名 `STITCH_API_KEY`，远程地址为 `https://stitch.googleapis.com/mcp`。不得替换为携带真实密钥的 `http_headers`。静态插件验证不等于安装后 MCP 加载或连接成功；必须在目标 Codex 新任务中验证。

## 使用与恢复

可尝试“在 Stitch 中生成响应式产品页面”“保留设计系统，仅编辑当前屏幕”“把 Stitch 设计转换为前端组件”。生成、编辑、上传属于远程写操作，应先确认目标项目、素材和当前授权范围。

写操作超时或返回结果不明确时，先用只读查询检查项目、屏幕或操作状态；不要直接重试写操作，否则可能重复创建或覆盖。无法确认时保留请求范围与非敏感标识，停止后续写入并报告未确认状态。先完成本地设计说明、代码或素材准备，不把远程未完成标为完成。

## 不回显密钥的排查

在实际启动 Codex 的环境中检查变量是否设置：

```bash
test -n "$STITCH_API_KEY" && echo "STITCH_API_KEY is set" || echo "STITCH_API_KEY is not set"
```

不要运行 `env`、`printenv STITCH_API_KEY`、`echo "$STITCH_API_KEY"` 或打印认证配置；不要扫描其他客户端配置寻找密钥。

- 未发现 MCP 工具：检查插件是否启用，并重启 Codex/新建任务；核对当前客户端是否加载 `.mcp.json` 的 `env_http_headers`。不要仅凭插件静态校验通过判断支持。
- 认证失败：在 Stitch Settings 确认密钥有效及所属账号；通过凭据管理器更新环境并重启。不要将密钥粘贴到问题报告。
- 权限错误：确认目标项目属于当前账号或已获得访问权限。
- 网络错误：检查到上述 HTTPS 端点的网络访问；报告脱敏的错误类型，不输出带密钥的请求头或私密链接。
- 资源或工具缺失：按相应 Skill 的前置条件检查依赖；不静默安装，保留本地成果并说明未执行环节。

## 快照、来源与许可

`skills/` 是 39 个独立 Skill 目录的普通文件快照，不依赖符号链接。来源为 `full-stack-skills/stitch-skills` 已验证工作树，快照基准提交 `62ef81825ad6ddc85bb6b8426e65b1a9d07d109b`。本轮快照含静态 HTML 提取的 SSRF、日志脱敏、上下文转义与项目依赖解析修复；源码离线测试 28 项通过，未运行浏览器或调用远程 Stitch。技能仓库后续变更不会自动更新本插件，应重新复制、验证并完成插件更新流程。

上游官方来源：[google-labs-code/stitch-skills](https://github.com/google-labs-code/stitch-skills/tree/0337446dadde6f8c94210444e2aa9d546126480f)，固定 SHA：`0337446dadde6f8c94210444e2aa9d546126480f`。本插件含官方适配内容及 Full Stack Skills / PartMe.AI 补充技能，并非 Google 官方发布插件。

完整 Apache 2.0 主许可见 [LICENSE](LICENSE)，归属说明见 [NOTICE](NOTICE)。原有第三方通知与许可正文完整保留于 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)，相关组件仍遵循各自许可。这三份文件均来自同一技能仓库快照。共享插件前检查文件内没有凭据、账号数据、私密素材或临时缓存；远程服务可用性和权限仍取决于接收者自己的 Stitch 账号与运行环境。

本插件仍采用 OpenAI 支持的 Codex compatibility layout。由于 Agent Plugins 1.0 不允许远程 header 环境变量展开，当前不会启用可能破坏 `STITCH_API_KEY` 鉴权的根级 portable manifests。迁移门禁见 [Portable Agent Plugin migration](docs/portable-migration.md)。隐私说明见 [PRIVACY.md](PRIVACY.md)，使用条款见 [TERMS.md](TERMS.md)。
