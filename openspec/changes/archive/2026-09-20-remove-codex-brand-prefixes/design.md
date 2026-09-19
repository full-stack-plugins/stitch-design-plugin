## Context

这些设计源自 Codex-only 阶段，但目标插件现在需要同时面向 Codex、ZCode 与 Kimi。公共能力名称必须与宿主适配层分离。

## Decision

现行公共名称使用产品/角色名称；Codex 名称只在 `.codex-plugin`、Codex CLI、Codex 专属测试或明确的历史说明中出现。历史仓库名不改写，未来插件和技能 ID 不再继承旧前缀。

## Validation

运行仓库测试、残留命名审计、`git diff --check` 与严格 OpenSpec 验证。
