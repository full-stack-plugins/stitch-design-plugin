---
name: stitch-local-setup
description: 本地首次使用 Stitch Design、缺少 STITCH_API_KEY 或认证失败时，指导 Windows、macOS、Linux 用户从 Stitch Settings 获取 key，并通过插件配置器完成一次性设置；网页 ChatGPT 连接不使用本流程。
license: Apache-2.0
---

# Stitch Design 本地首次设置

## 快速开始

典型触发：

1. “第一次使用 Stitch Design。”
2. “Stitch 提示缺少 STITCH_API_KEY。”
3. “帮我配置 Stitch key，但不要写进 shell profile。”

面向 Windows、macOS、Linux 的本地 Codex 用户。插件已内置 MCP URL；本 Skill 只处理用户凭据缺失和启动时环境变量注入。

## 能力边界说明

### ✅ 擅长处理

- 检查 `STITCH_API_KEY` 是否已在当前进程或插件凭据文件中配置，不输出其值。
- 指导用户隐藏输入自己的 Stitch API key，并保存到当前用户的受限配置目录。
- 用保存的凭据启动 Codex CLI，或向用户指定的本地命令注入环境变量。

### ⚠️ 需要用户完成

- 登录 [Stitch Settings](https://stitch.withgoogle.com/settings) 创建或轮换自己的 key。
- 只在本机配置器的隐藏提示中输入 key。
- 重新启动 Codex，让新进程获得 `STITCH_API_KEY`。

### ❌ 不适用场景及交接

- ChatGPT 网页插件授权：应由正式 connector/OAuth 处理，不要求用户粘贴 key。
- 团队共享一个作者 key：每位用户使用独立凭据，或建设租户隔离的认证网关。
- 声称配置文件等同系统密钥库：它是权限受限的用户文件，不是硬件或系统凭据保险库。

## 首次使用工作流

1. 先做布尔检查，不读取或打印 key：

   ```bash
   test -n "$STITCH_API_KEY" && echo "STITCH_API_KEY is set" || echo "STITCH_API_KEY is not set"
   ```

2. 如果当前环境已设置，继续原来的 Stitch 任务。
3. 如果没有设置，暂停远程调用，告诉用户从 Stitch Settings 创建 key；不要让用户把 key 粘贴到聊天。
4. 从当前 `SKILL.md` 向上两级定位插件根目录，打开极简本地设置向导：

   - Windows：

     ```powershell
     py C:\absolute\plugin\root\scripts\stitch_setup.py ui
     ```

   - macOS / Linux：

     ```bash
     python3 /absolute/plugin/root/scripts/stitch_setup.py ui
     ```

5. 用户在同一张卡片中完成“获取 Key → 保存到本机 → 打开 Codex”；高级命令默认折叠。
6. 设置后启动 Codex：

   ```bash
   python3 /absolute/plugin/root/scripts/stitch_setup.py cli
   ```

   Windows 使用 `py ... cli`。自定义启动命令使用 `run -- <command>`。
7. 新任务先只读调用 `list_projects`。项目列表或明确的空列表都算认证成功；未知或超时不执行写操作。

## 安全与降级

- 不搜索浏览器、其他客户端配置、shell profile、历史或日志中的 key。
- 不执行 `echo "$STITCH_API_KEY"`、`printenv STITCH_API_KEY` 或全量 `env`。
- 配置文件不进入插件目录或 Git；配置器不修改 `.zshrc`、PowerShell Profile 或系统环境。
- 如果用户要求系统凭据保险库，说明当前配置器未提供该保证，建议等待官方 Stitch connector/OAuth。
- 缺少 Python 时，提供当前终端的会话级环境变量方案，并说明关闭终端后失效。

## FAQ

**Q1：key 在哪里获取？** 在 [Stitch Settings](https://stitch.withgoogle.com/settings) 创建。

**Q2：为什么安装后还需要 key？** 安装已完成 MCP 配置；key 用于 Stitch 用户认证。

**Q3：会修改 shell 配置吗？** 不会。配置器使用独立的用户凭据文件。

**Q4：保存在哪里？** Windows 使用 `APPDATA`；macOS/Linux 使用 `XDG_CONFIG_HOME` 或 `~/.config`。

**Q5：如何验证？** 运行 `stitch_setup.py check`，重启后只读调用 `list_projects`。

**Q6：能把 key 发给智能体吗？** 不能，只在本机隐藏提示中输入。

## 按需参考

- 状态和平台分支见 [工作流](references/workflow.md)。
- 不安全方案见 [反模式](references/anti-patterns.md)。
- 存储、轮换和 connector 边界见 [深度 FAQ](references/faq-deep.md)。
- 行为验证见 [本地验证示例](examples/local-validation.md)。
