# 外部证据合同

Stitch、ImageGen、OCR和视觉评估由真实工具执行；本地 Harness 只接收以下脱敏 envelope：

```json
{
  "schema_version": 1,
  "step": "imagegen",
  "provider": {"name": "provider", "tool": "tool-name", "model": "reported-version"},
  "invoked_at": "2026-09-14T00:00:00Z",
  "source_artifacts": [{"path": "artifacts/source.png", "sha256": "64-lowercase-hex"}],
  "artifacts": [{"path": "artifacts/art.png", "sha256": "64-lowercase-hex", "mime": "image/png", "width": 1350, "height": 768}],
  "result": {"status": "generated"}
}
```

路径必须位于当前 run；哈希在写 evidence 前从实际文件计算。不得保存 API Key、Cookie、Authorization/Header、base64 全文或带签名下载 URL。供应商只返回成功文本却没有产物时，不创建通过 evidence。

OCR 的 `result.texts` 保存识别文本数组；视觉评估的 `result.scores` 必须包含 `hierarchy`、`density`、`color`、`component_quality`、`completion`，并携带 `layout_score`。未知写入只保存 `schema_version`、`step` 和 `result: "unknown"`，不得伪造资源 ID。

使用 `EvidenceWriter` 的 `stitch_generation`、`imagegen`、`ocr`、`roundtrip`、`editability` 和 `visual_review` 方法生成类型化 envelope。`imagegen` 必须传真实 `width`/`height`。`editability` 必须输入 before/edited/restored HTML 与 render 六个文件，写出六个唯一 `semantic_role`；任一 result 哈希不等于实际 artifact 哈希、edited 未变化或 restored 不等于 before，Harness 均拒绝。`visual_review` 的 source artifacts 只能来自当前 run 的 imagegen/roundtrip receipts。

`not_applied` 与 `applied` reconciliation 都必须包含三条类型化 `read_probes`：每条使用唯一的 `get_project`、`list_screens` 或 `get_screen`，并提供带时区 `invoked_at`、唯一 `response_id`、枚举 `status`、`result_sha256` 和唯一的 run-local `application/json` artifact。结果哈希必须等于 artifact 哈希；artifact JSON 也执行递归敏感信息检查。裸工具名列表不能授权重试。
