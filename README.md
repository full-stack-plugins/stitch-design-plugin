# Stitch Design for Codex

`stitch-design` v0.4.0 封装 Google Stitch 远程 MCP 与 40 个设计、首次设置、设计系统、代码导入和设计转前端 Skills。Codex 展示名称为 **Stitch Design**。插件仓库：[partme-ai/codex-stitch-plugin](https://github.com/partme-ai/codex-stitch-plugin)；技能主干来源：[Full Stack Skills / PartMe.AI](https://github.com/full-stack-skills/stitch-skills)。

## 选择使用环境

| 环境 | MCP 配置 | 是否需要 key | 当前状态 |
|---|---|---|---|
| Codex CLI | 安装插件时自动加载 `.mcp.json` | 需要本机 `STITCH_API_KEY` | 推荐 |
| 本地桌面端 | 安装插件时自动加载 `.mcp.json` | 需要启动进程继承 `STITCH_API_KEY` | 兼容模式 |
| ChatGPT 网页版 | 点击连接授权 | 用户不应填写 key | 实验性，`list_projects` 尚未通过 |

第一次使用请阅读 [Stitch Design 使用指南](docs/getting-started.zh-CN.md)。`stitch-local-setup` Skill 会在缺少凭据时打开极简三步页面；Windows、macOS、Linux 均使用同一 `stitch_setup.py ui` 入口。凭据保存在当前用户的受限配置目录，启动时只注入目标子进程。

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

安装插件时会自动加载 `.mcp.json`，无需再次配置 MCP URL。API key 是 Stitch 的用户凭据，不是 MCP 配置的一部分。

1. 登录 [Stitch](https://stitch.withgoogle.com)，在 Stitch Settings 中创建 API key。密钥泄露或不再使用时，在同一设置页面吊销；轮换时创建新密钥、更新运行环境，再吊销旧密钥。
2. 使用 `stitch_setup.py ui` 打开三步设置页面，在本地密码输入框保存 key。配置器不会修改 shell profile、系统环境或插件文件；其用户凭据文件不是系统密钥库。不要把真实值写入聊天、命令参数或日志。

3. 使用 `stitch_setup.py cli` 或 `run -- <command>` 启动目标客户端，使新进程继承该环境变量。安装或更新插件后，新建任务加载配置和 Skills。
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

`skills/` 包含 39 个上游 Skill 快照和 1 个插件本地首次设置 Skill，均为普通文件目录，不依赖符号链接。上游来源为 `full-stack-skills/stitch-skills` 已验证工作树，快照基准提交 `62ef81825ad6ddc85bb6b8426e65b1a9d07d109b`。本轮上游快照含静态 HTML 提取的 SSRF、日志脱敏、上下文转义与项目依赖解析修复；源码离线测试 28 项通过，未运行浏览器或调用远程 Stitch。技能仓库后续变更不会自动更新本插件，应重新复制、验证并完成插件更新流程。

上游官方来源：[google-labs-code/stitch-skills](https://github.com/google-labs-code/stitch-skills/tree/0337446dadde6f8c94210444e2aa9d546126480f)，固定 SHA：`0337446dadde6f8c94210444e2aa9d546126480f`。本插件含官方适配内容及 Full Stack Skills / PartMe.AI 补充技能，并非 Google 官方发布插件。

完整 Apache 2.0 主许可见 [LICENSE](LICENSE)，归属说明见 [NOTICE](NOTICE)。原有第三方通知与许可正文完整保留于 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)，相关组件仍遵循各自许可。这三份文件均来自同一技能仓库快照。共享插件前检查文件内没有凭据、账号数据、私密素材或临时缓存；远程服务可用性和权限仍取决于接收者自己的 Stitch 账号与运行环境。

本插件仍采用 OpenAI 支持的 Codex compatibility layout。由于 Agent Plugins 1.0 不允许远程 header 环境变量展开，当前不会启用可能破坏 `STITCH_API_KEY` 鉴权的根级 portable manifests。迁移门禁见 [Portable Agent Plugin migration](docs/portable-migration.md)。隐私说明见 [PRIVACY.md](PRIVACY.md)，使用条款见 [TERMS.md](TERMS.md)。
