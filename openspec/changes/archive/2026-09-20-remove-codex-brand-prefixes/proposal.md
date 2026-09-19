## Why

现行设计仍把已经跨宿主的公共插件、技能或生产者写成 `codex-*`，会让后续实现继续复制早期单宿主命名。

## What Changes

- 将现行公共插件、技能、目录与测试夹具引用迁移到无宿主前缀的名称。
- 保留 `.codex-plugin`、Codex CLI 与已归档仓库名称等真实宿主/历史事实。
- 增加跨宿主命名规范，阻止新的公共 `codex-<product>` 标识。

## Capabilities

### New Capabilities

- `cross-host-plugin-identity`: 定义跨宿主公共命名和允许的 Codex 专属例外。

### Modified Capabilities

None.

## Impact

仅影响现行规格、计划、测试夹具和命名规范；不重命名宿主 manifest、历史归档仓库或已发布 tag。
