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

