# Stitch Design 技术方案

> **范围**：说明 Stitch Design 0.5.2 的实现决策、接口、安全、测试、发布和迁移方案。
>
> **最后更新**：2026-09-14

[English](Stitch-Design-Technical-Solution.md) | [架构文档](Stitch-Design-Architecture.zh_CN.md)

## 1. 技术基线

| 领域 | 选型 | 理由 |
|:---|:---|:---|
| 宿主打包 | Codex compatibility manifest | 当前已支持并验证 |
| 工具传输 | 内置 stdio 代理连接 Google Stitch HTTP MCP | 宿主连接可靠，工具执行仍由供应商负责 |
| 认证 | 显式进程环境或受限用户配置 | 避免交互式系统弹窗，Key 不进入插件包 |
| 工作流 | 43 个 Agent Skills + 交付 Harness | 精确发现与可验证交付 |
| 首次设置 | Python 标准库 Loopback 服务 + 静态页面 | 不增加第三方运行依赖 |
| 凭据保存 | 跨平台当前用户 JSON，使用受限权限 | 行为可预测且非交互 |
| 验证 | unittest、分发校验、ShellCheck | 可复现离线门禁 |

## 2. 工程映射

| 路径 | 合同 |
|:---|:---|
| `.codex-plugin/plugin.json` | 身份、版本、展示、MCP 路径 |
| `.agents/plugins/marketplace.json` | Git 来源和 `ON_USE` 策略 |
| `.mcp.json` | 内置 stdio 代理命令和插件根工作目录 |
| `stitch_harness/` | 契约、代理、门禁、receipts、状态和归档 |
| `skills/` | 工作流和转换合同 |
| `scripts/stitch_setup.py` | setup/check/run/cli/desktop/ui |
| `assets/setup/` | 中央单卡片首次设置页 |
| `scripts/validate_distribution.py` | 包合同和秘密模式扫描 |
| `tests/` | 分发、凭据、HTTP 安全和 UI 结构测试 |

运行时保持纯 Python 架构。所有支持宿主的 PATH 的 `python` 必须解析为 Python 3.11 或更高版本；`.mcp.json`、设置说明与 CI 均使用这一精确命令。

## 3. 首次设置主链

```mermaid
sequenceDiagram
    participant S as Setup Skill
    participant U as 用户
    participant L as 本地向导
    participant F as 用户受限配置
    participant C as 新 Codex 进程
    S->>S: 检查凭据
    alt 缺失
      S->>L: 监听 127.0.0.1 随机端口
      L-->>U: 三步页面
      U->>L: 提交密码输入框中的 Key
      L->>L: Origin/CSRF/大小/JSON 校验
      L->>F: 原子写入
      L->>L: 清空输入框
      U->>L: 打开 Codex
      L->>C: 注入 STITCH_API_KEY 后启动
    end
```

| 路由 | 方法 | 用途 | 门禁 |
|:---|:---:|:---|:---|
| `/` | GET | HTML | no-store + CSP |
| `/styles.css` | GET | 本地样式 | 同源 |
| `/app.js` | GET | 页面交互 | 同源 |
| `/api/save` | POST | 保存 Key | Origin、CSRF、JSON、8192 字节 |
| `/api/launch` | POST | 启动 Codex | Origin、CSRF |

服务关闭请求日志，不返回提交值；页面不使用 Cookie、浏览器存储、远程资产和埋点。

## 4. 配置与轮换

```mermaid
flowchart TD
    Start(["首次使用 Stitch"]) --> Env{"当前进程存在 STITCH_API_KEY？"}
    Env -->|是| Direct["直接使用进程变量"]
    Env -->|否| Store{"用户受限配置存在 Key？"}
    Store -->|是| Inject["本地 stdio 代理每进程读取一次"]
    Store -->|否| Wizard["打开本地设置向导"]
    Wizard --> Save["校验并保存 Key"]
    Save --> Inject
    Direct --> Ready(["调用 Stitch MCP"])
    Inject --> Ready
```

优先级：显式进程环境变量 → 受限用户配置 → 打开设置页。

轮换步骤：打开向导 → 保存新 Key → 启动新 Codex → 只读 `list_projects` → 在 Stitch Settings 吊销旧 Key。

### 4.1 Loopback 请求流程

```mermaid
sequenceDiagram
    participant B as 浏览器
    participant H as 127.0.0.1 服务
    participant V as 请求校验器
    participant F as 用户受限配置
    B->>H: GET / 并携带单次 CSRF Token
    H-->>B: 本地资产 + no-store + CSP
    B->>H: POST /api/save（Origin、CSRF、JSON）
    H->>V: 校验 Origin、Token、类型和大小
    alt 请求合法
      V->>F: 受限权限原子替换
      F-->>V: 保存完成
      V-->>B: 成功响应，不返回 Key
    else 请求非法
      V-->>B: 通用错误，不回显输入
    end
```

## 5. MCP、Harness 与 Skill 责任

本地 stdio 代理负责 MCP 初始化、会话 Header、JSON/SSE、秘密脱敏，以及仅对 HTTP 401 的一次刷新和重试。HTTP 403 表示权限不足，不刷新也不重放。交付 Harness 负责页面契约、有限状态、机器门禁、receipt 哈希链、恢复、明确批准和归档。Agent Skills 调用真实 Stitch、ImageGen、OCR和视觉工具并回填规范化 evidence；仅有供应商成功文本不能通过。

```mermaid
flowchart LR
    Codex --> Proxy[本地 stdio MCP 代理]
    Proxy --> Stitch[Google Stitch MCP]
    Codex --> Skill[Delivery Harness Skill]
    Skill --> Core[本地状态与门禁]
    Skill --> Providers[Stitch / ImageGen / OCR]
    Core --> Receipts[项目 receipts 与归档]
```

插件不重复实现 Stitch SDK。项目、屏幕、设计系统、生成、编辑、变体、上传和资产操作由实际发现的 Stitch MCP 工具执行。Skill 负责意图路由、本地准备、参数核验、范围控制和不确定写入恢复。

```mermaid
flowchart LR
    W["写操作"] --> R{"有明确结果？"}
    R -->|是| D["返回已验证结果"]
    R -->|否/超时| P["读取项目/屏幕"]
    P --> F{"发现结果？"}
    F -->|是| D
    F -->|否| U["报告未知，不重发"]
```

## 6. 安全控制

| 风险 | 控制 | 证据 |
|:---|:---|:---|
| Key 进入仓库 | 环境映射 + 秘密扫描 | 校验器 |
| 跨站本地 POST | Origin + CSRF | HTTP 测试 |
| 畸形或超大请求 | JSON + 8192 字节限制 | Handler/测试 |
| 浏览器残留 | 禁用存储并清空输入 | `app.js` |
| 外部代码执行 | 本地资产与 self-only CSP | 响应 Header |
| 重复远程写 | 先读后重试 | Skill 合同 |
| 身份混用 | 每用户独立 Key | 隐私与设置文档 |

## 7. 验证与发布

```mermaid
flowchart LR
    Source["工作树"] --> Unit["单元测试套件"]
    Source --> Dist["分发校验器"]
    Source --> Skill["Skill 结构校验"]
    Source --> Shell["ShellCheck"]
    Source --> Secrets["秘密模式扫描"]
    Source --> Visual["390 · 768 · 1280 px 视觉验收"]
    Unit --> Gate{"全部门禁通过？"}
    Dist --> Gate
    Skill --> Gate
    Shell --> Gate
    Secrets --> Gate
    Visual --> Gate
    Gate -->|是| Publish["提交 · 推送 · 标签 · Release"]
    Gate -->|否| Fix["修正后重跑受影响门禁"]
    Fix --> Source
```

```bash
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
python scripts/validate_distribution.py .
python scripts/validate_skills.py skills
python scripts/validate_markdown_links.py .
python scripts/scan_secrets.py .
find scripts skills -type f -name '*.sh' -exec shellcheck {} +
python -m compileall -q scripts stitch_harness skills
actionlint .github/workflows/validate.yml
git diff --check
```

0.4.0 证据：提交/标签/远端 SHA 均为 `6cf533ee884157a5a265c6200bbff6842b62c0f5`；16 项测试、40 个 Skills、公开 Marketplace 安装、安装产物对比，以及 390×884、768×1024、1280×1024 视觉检查通过。

## 8. 限制与演进

| 项目 | 当前状态 | 退出条件 |
|:---|:---|:---|
| ChatGPT 网页版 | 实验性 | Connector/OAuth 与 `list_projects` 通过 |
| Portable manifest | 阻塞 | 可移植凭据引用或 OAuth |
| 加密本地保险库 | 未实现 | 宿主提供秘密存储 |
| Windows 实机 | 仅代码路径 | Windows 主机验收 |
| 远端 CI | Workflow 已配置，远端运行未验证 | 观察 GitHub Actions 成功运行 |

---

**文档版本**：2.1.0 · **状态**：与 0.5.2 发布候选对齐
