---
name: stitch-local-setup
description: 本地首次使用 Stitch Design、缺少凭据或认证失败时，优先指导通过 gcloud 完成浏览器点击授权（ADC），不可用时降级为从 Stitch Settings 粘贴 key 到本地配置器；网页 ChatGPT 连接不使用本流程。
license: Apache-2.0
---

# Stitch Design 本地首次设置

## 快速开始

典型触发：

1. “第一次使用 Stitch Design。”
2. “Stitch 提示缺少凭据 / STITCH_API_KEY。”
3. “帮我配置 Stitch 授权，但不要写进 shell profile。”

面向 Windows、macOS、Linux 的本地 Codex 用户。插件已内置本地 stdio MCP 代理；本 Skill 只处理用户凭据缺失和受限的用户级配置。代理支持两种鉴权：**Google Cloud ADC（推荐，浏览器点击授权，令牌由 gcloud 自动刷新）** 与 **Stitch API key（粘贴保存）**；前者优先，走不通时自动落到后者。

所有支持宿主的 PATH 中的 `python` 必须解析为 Python 3.11 或更高版本；插件 MCP 和本设置流程使用同一命令。

## 能力边界说明

### ✅ 擅长处理

- 检查凭据状态（ADC 或 `STITCH_API_KEY`），不输出其值。
- 指导用户运行 gcloud 浏览器授权（`gcloud` 子命令），本机不落长期密钥。
- 指导用户隐藏输入自己的 Stitch API key，并保存到跨平台的当前用户受限配置文件。
- 用保存的凭据启动 Codex CLI，或向用户指定的本地命令注入环境变量。

### ⚠️ 需要用户完成

- ADC 方式：本机安装 Google Cloud SDK；在浏览器中完成 Google 授权点击；首次使用建议设置配额项目（`GOOGLE_CLOUD_PROJECT` 或 `gcloud config set project`）。
- API key 方式：登录 [Stitch Settings](https://stitch.withgoogle.com/settings) 创建或轮换自己的 key，只在本机配置器的隐藏提示中输入。
- 重新启动 Codex，让新进程获得最新凭据状态。

### ❌ 不适用场景及交接

- ChatGPT 网页插件授权：应由正式 connector/OAuth 处理，不要求用户粘贴 key。
- **纯对话（chat）模式首次配置**：chat 模式无法完成本机凭据写入，首次配置必须在 Work/本地模式完成（或用户手动创建凭据文件）；配置完成后，chat 模式即可复用本机凭据调用 Stitch 工具。
- 团队共享一个作者 key：每位用户使用独立凭据，或建设租户隔离的认证网关。
- 将凭据写入 Codex 配置、shell profile、项目文件或权限不受限的文件。

## 首次使用工作流

1. 先用配置器做只读检查；它按顺序校验 ADC 可用性、API key 可读性、以及插件根 `.mcp.json` 是否存在，只输出状态行，不打印凭据或路径：

   ```bash
   python /absolute/plugin/root/scripts/stitch_setup.py check
   ```

2. 检查通过后继续原来的 Stitch 任务。输出 `Google Cloud ADC credential is available` 表示 ADC 授权可用，无需再配 key。
3. 检查失败时暂停远程调用，并按最后一行输出区分分支，不要混为一谈：

   - **推荐分支（gcloud ADC）**：本机有 Google Cloud SDK 时优先执行：

     ```bash
     python /absolute/plugin/root/scripts/stitch_setup.py gcloud
     ```

     它会先打印授权链接再打开浏览器，用户点击同意即可；成功后令牌由 gcloud 自动刷新，本插件不保存长期密钥。命令失败会给出降级提示，此时改走 key 分支。
   - `STITCH_API_KEY is not configured`：key 分支凭据缺失。MCP 代理会自动打开本地 Token 页面；页面顶部即“使用 Google 账号授权（推荐）”入口，粘贴保存只是降级方式。不要让用户把 key 粘贴到聊天。代理在刷新一次后仍收到 401 时也会打开同一页面，用于重新授权或更换失效 Key。
   - `Stitch MCP configuration is missing`：凭据可读但插件根缺少 `.mcp.json`，属于安装不完整。此时新建凭据无效，应修复或重新安装插件后重跑 `check`。
4. 正常情况下等待自动打开的本地页面。代理使用 10 分钟冷却标记避免同一缺失凭据连续弹窗；标记只记录启动时间，不包含凭据。只有浏览器被系统策略阻止或页面未出现时，才从当前 `SKILL.md` 向上两级定位插件根目录并手动打开：

   - Windows：

     ```powershell
     python C:\absolute\plugin\root\scripts\stitch_setup.py ui
     ```

   - macOS / Linux：

     ```bash
     python /absolute/plugin/root/scripts/stitch_setup.py ui
     ```

5. 用户在单卡片中完成授权（推荐按钮）或粘贴保存 Token；获取链接、三条说明和高级命令保持轻量，不再显示独立三步向导。
6. 凭据仅来自当前进程或受限的用户配置文件；启用 ADC 时另有 gcloud 自有配置目录中的短期令牌，本插件不经手。没有其他存储迁移入口。可用 `STITCH_AUTH_MODE=adc|stored_key` 强制指定来源，`STITCH_DISABLE_ADC=1` 关闭 ADC 探测。
7. 设置后先回到对话重新发起原请求。若当前宿主没有重新建立 MCP 进程，再使用配置器启动 Codex：

   ```bash
   python /absolute/plugin/root/scripts/stitch_setup.py cli
   ```

   Windows 使用同一个 `python ... cli` 命令。自定义启动命令使用 `run -- <command>`。
8. 新任务先只读调用 `list_projects`。项目列表或明确的空列表都算认证成功；未知或超时不执行写操作。

## 安全与降级

- 降级链固定为：ADC 可用 → 使用 ADC；ADC 不可用或授权取消 → 已存 API key；两者皆无 → 弹本地设置页。运行期 401 会先强制刷新一次（ADC 重新铸令牌），仍失败才弹页。
- 不搜索浏览器、其他客户端配置、shell profile、历史或日志中的凭据。
- 不执行 `echo "$STITCH_API_KEY"`、`printenv STITCH_API_KEY` 或全量 `env`。
- 凭据不进入插件目录、Git 或 Codex 配置；用户配置目录和文件在 Unix 使用 `0700`/`0600`，Windows 继承当前用户 Profile ACL。配置器不修改 `.zshrc`、PowerShell Profile 或系统环境。ADC 的刷新令牌由 gcloud 在其自有配置目录管理，本插件只调用其命令取短期令牌。
- PATH `python` 缺失或低于 3.11 时，先阻塞插件调用并给出修复说明；会话级环境变量不能修复解释器前置条件。

## FAQ

**Q1：推荐哪种方式？** 有 Google Cloud SDK 时优先 gcloud ADC（`gcloud` 子命令，浏览器点击一次授权，令牌自动刷新）；无 SDK 或无法安装时用 Stitch Settings 的 key 粘贴到本地配置器。

**Q2：为什么安装后还需要授权？** 安装已完成 MCP 配置；授权（ADC 或 key）用于 Stitch 用户认证。

**Q3：会修改 shell 配置吗？** 不会。ADC 由 gcloud 自有配置管理；key 存独立的用户凭据文件。

**Q3.1：为什么页面没有自动打开？** 自动打开由本地 MCP 代理在首次缺少凭据时触发，并有 10 分钟防重复冷却。若浏览器策略阻止打开，请使用上面的 `ui` 命令；不需要把凭据发到聊天。

**Q4：保存在哪里？** ADC 刷新令牌在 gcloud 配置目录（`application_default_credentials.json`），本插件不经手；API key 在 Unix `$XDG_CONFIG_HOME/stitch-design/credentials.json` 或 `~/.config/...`，Windows `%APPDATA%\stitch-design\credentials.json`。移除方式：ADC 运行 `gcloud auth application-default revoke`；key 先在 Stitch Settings 吊销再删除凭据文件。

**Q5：如何验证？** 运行 `stitch_setup.py check`，重启后只读调用 `list_projects`。

**Q6：能把 key 发给智能体吗？** 不能，只在本机隐藏提示或浏览器授权页输入。

## 按需参考

- 状态和平台分支见 [工作流](references/workflow.md)。
- 不安全方案见 [反模式](references/anti-patterns.md)。
- 存储、轮换和 connector 边界见 [深度 FAQ](references/faq-deep.md)。
- 行为验证见 [本地验证示例](examples/local-validation.md)。
