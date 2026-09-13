# 跨平台本地凭据工作流

1. 环境变量存在：直接使用，不读配置文件。
2. 环境变量缺失、凭据文件有效：启动器读取后仅注入子进程。
3. 两者都缺失：提示 `setup`，不调用远程 Stitch。
4. Windows 路径：`%APPDATA%\stitch-design\credentials.json`。
5. macOS/Linux 路径：`$XDG_CONFIG_HOME/stitch-design/credentials.json`，未设置时使用 `~/.config/stitch-design/credentials.json`。
6. `check` 只返回状态和路径，不输出 key。
7. `list_projects` 返回项目或空列表后，才标记认证可用。

用户交接必须包含 Stitch Settings、当前缺项、安装副本中的真实脚本路径、安全边界和只读验证步骤。
