# 覆盖矩阵

| 页面/来源 | 状态 | 流程 | 提示 | 任务 |
| --- | --- | --- | --- | --- |
| P01 / S1,S2,S3 | normal, loading, empty, error, permission-denied, offline, partial-data | F01 | Q01 | T01,T03 |
| P02 / S1,S2,S3 | normal, loading, empty, error, permission-denied, offline, partial-data | F01,F02 | Q02 | T02,T03 |

两份提示各编排一页的状态变体，不把“覆盖”当作已生成7张图。危险操作与独立控制台/日志页是明确范围外；本地示例暂无 deferrals。真实项目需要这些能力时，先补业务权限与确认合同，再追加页面/提示/任务。实现和视觉验收均未执行。
