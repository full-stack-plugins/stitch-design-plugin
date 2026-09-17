# 跨平台本地凭据工作流

1. ADC 可用（gcloud `print-access-token` 实际铸出令牌）：优先使用，请求头为 `Authorization: Bearer` + `X-Goog-User-Project`；令牌由 gcloud 自动刷新。`STITCH_DISABLE_ADC=1` 关闭探测，`STITCH_AUTH_MODE=adc|stored_key` 强制来源。
2. ADC 不可用且环境变量存在：直接使用 key，不读配置文件。
3. 环境变量缺失、凭据文件有效：启动器读取后仅注入子进程。
4. 三者皆缺：本地 MCP 代理自动启动 `stitch_setup.py ui`，随后返回缺少凭据错误，不调用远程 Stitch。10 分钟内的重复请求不会重复打开窗口；自动启动失败时使用安装副本中的 `ui` 命令降级。页面顶部为“使用 Google 账号授权（推荐）”入口（`gcloud` 子命令），粘贴 key 为降级方式。
5. Windows 路径：`%APPDATA%\stitch-design\credentials.json`。
6. macOS/Linux 路径：`$XDG_CONFIG_HOME/stitch-design/credentials.json`，未设置时使用 `~/.config/stitch-design/credentials.json`。
7. `check` 只输出状态行：`Google Cloud ADC credential is available`、`STITCH_API_KEY is not configured`、`STITCH_API_KEY is available through the configured secret provider`、`Stitch MCP configuration is present` 或 `Stitch MCP configuration is missing`。它不输出凭据值，也不输出任何路径；按最后一行区分"凭据缺失"与"插件安装不完整"。凭据文件不可读或损坏时，`check` 改在 stderr 报 `Stitch credential check failed: ...` 并以 1 退出；此时先修复或删除该凭据文件再重跑 `check`，不要新建 key。
8. 运行期 401：代理强制刷新一次凭据（ADC 重新铸令牌），仍 401 才弹本地设置页；403 属权限问题，不刷新不重放。
9. `list_projects` 返回项目或空列表后，才标记认证可用。
10. **Codex 宿主原生 OAuth（可选高级通道）**：`python scripts/stitch_mcp_proxy.py --http --port 21434` 启动本地 HTTP 端点；`python scripts/stitch_setup.py codex-oauth` 打印 Codex config.toml 配置块（`url` 指向本地端点 + `oauth.client_id` 填 Google OAuth Client ID + scopes 默认 cloud-platform/openid/email）。宿主首次调用收到 401 挑战 → 自动发现 Google 为授权服务器 → 浏览器点击授权 → 宿主保存并自动刷新令牌，代理只透传 `Authorization: Bearer`。前置：Google Cloud Console 注册一个 Desktop 型 OAuth Client ID（环境变量 `STITCH_OAUTH_CLIENT_ID` 或 `--client-id` 传入）；可选 `GOOGLE_CLOUD_PROJECT` 供本地端点发送 `X-Goog-User-Project`。该通道令牌完全由宿主管，本地凭据文件与 ADC 不参与。

用户交接必须包含 Stitch Settings、当前缺项、自动打开状态、安全边界和只读验证步骤；只有自动打开失败时才要求用户使用安装副本中的真实脚本路径。
