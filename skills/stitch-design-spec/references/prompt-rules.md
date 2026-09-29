# 三段提示编译规则

## 1. 模式优先判定

| 条件 | 模式 | 正文规则 |
| --- | --- | --- |
| 用户明确编辑现有屏幕某区域 | targeted-edit | 只写目标及差值；允许该差值明确要求的颜色/字体等 |
| 新屏，执行器已确认当前项目应用了 designSystem | applied-system | 只写内容、布局、组件结构、交互；hex、颜色角色、字体、主题、圆角等移到独立系统交接 |
| prompt-only、没有应用证据或 legacy 工具路径 | inline | 将有来源的视觉定义内联；未确认视觉建议明确标注 |

三种模式不能混写。编辑优先于新屏系统模式。执行器后来提供有效系统证据时，从同一页面合同重新编译提示，不重做产品设计。模式名是本技能本地协议。

## 2. 编译步骤

1. `[Context]` 写产品/模块、用户任务、设备与视口、语言、页面及目标状态。inline 才加入 DESIGN SYSTEM 区块，写来源与视觉建议；具体颜色使用“名称 + hex + 功能角色”，未知则保持待确认，不制造品牌事实。
2. `[Layout]` 按视觉和阅读顺序编号，写区域位置、层级、滚动/固定关系、必要尺寸，以及窄屏折叠规则。桌面外壳、业务页、Agent 侧栏的职责分别说清；不要每页更换外壳。
3. `[Components]` 写实际标签、数据字段、筛选/排序/分页、动作、禁用条件、反馈、错误与恢复、焦点/键盘；不虚构 API 或权限。
4. 每条交互回查源合同：触发→条件→反馈→目的地→失败/恢复。提示中的演示数据显式标注。
5. applied-system 检查正文没有视觉 token 或颜色角色；这些保持在源规格/系统交接中。表达“可见焦点”“错误文本”等行为要求可以保留。
6. 编辑只写请求的变更；不把整个 DESIGN.md 或无关组件塞入提示。模糊输入用 [词汇库](KEYWORDS.md) 细化组件，不能无条件添加登录、支付等功能。

## 3. 框架合同

先匹配 uviewpro / uview-pro，再匹配 uview，防止误选 Vue 2 契约。匹配名字是选取输入契约，不保证 Stitch 生成可运行框架代码。

| 名称/关键词 | 合同技能 |
| --- | --- |
| bootstrap / bs-vue | stitch-ui-contract-bootstrap |
| element / element-plus | stitch-ui-contract-element-plus |
| layui / layui-vue | stitch-ui-contract-layui |
| vant / vant4 | stitch-ui-contract-vant |
| uview / uview2 | stitch-ui-contract-uview2 |
| uviewpro / uview-pro | stitch-ui-contract-uviewpro |

读取已安装的对应技能，按名使用其合同。缺失时说明缺少哪个合同；可以保留不承诺框架精确风格的草案，不编造契约。安装说明：`npx skills add full-stack-skills/stitch-skills --skill <合同技能名>`，不自动安装。

保留 `CONTRACT_SELECTION_JSON_V1`：version、designSystem、mode、contracts.include、states.include。include 项必须取自实际读取的合同，只选本页相关组件/状态。selector JSON 在三段提示之外作为交接元信息。inline 可内联视觉与结构约束；applied-system 只注入结构/行为约束，视觉 token 分离；targeted-edit 仅注入此次差值有关的约束。

## 4. 防止伪完成

文档规格不是远程写请求。不得假定当前模型/设备枚举、凭本地颜色或字体字段创建 API 参数；由 stitch-ui-execute 根据实际工具 schema 映射。其安装说明：`npx skills add full-stack-skills/stitch-skills --skill stitch-ui-execute`。
