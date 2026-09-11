此文保留上游扩展流程及代码示例，属于按需参考。先读 [中文入口](../SKILL.md) 的范围、权限、来源和验证约束。历史工具名与参数必须以实际连接的 schema 和目标依赖版本核对；英文示例为结构演示，不是业务事实或已经执行的结果。

# Upload-to-Stitch

Upload local assets (images, mockups, HTML, and markdown files) to a Stitch project using the
provided upload script, which bypasses the MCP tool's base64 output token limits.

> [!NOTE]
> Large base64 payloads may exceed tool/model limits. The script encodes files in-process and uses HTTPS without redirects or automatic retries.

## Steps

### 1. Identify Target Project

Use `list_projects` to find the correct `projectId`.

### 2. Credentials

Use `STITCH_API_KEY` from the execution environment. Do not search other clients' configuration or request plaintext credentials in chat. The deprecated `--api-key` remains compatible but exposes argv; prefer the environment.

### 3. Run Upload Script

Verify that existing authorization covers these exact files and project. Prepare the file list, sizes and types before any new authorization is needed.

Use `run_command` to execute the Python script:

```bash
python3 <SKILL_DIR>/scripts/upload_to_stitch.py \
  --project-id <PROJECT_ID> \
  --file-path <PATH_TO_FILE> \
  --title /orders \
  --generated-by stitch-extract-static-html
```

> [!TIP]
> **macOS / SSL Certificate Troubleshooting:**
> If the upload fails with `ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate`, this means your Python installation does not have root certificate authorities configured.
>
> The script automatically attempts to use the `certifi` package to load the CA bundle if it is installed in your python environment. If `certifi` is not installed, use an existing trusted CA bundle with the `SSL_CERT_FILE` environment variable. Do not disable certificate verification or install dependencies without an authorized scope.

### Recovery and output

The CLI emits only validated screen names and instance id/sourceScreen fields. The response must be an object with a nonempty screens array; screenInstances must be an array and nonempty when the CLI requested instances. Every identifier must be a string in the local accepted syntax, screen resource paths must belong to the requested project, and instance sourceScreen must reference a returned screen. Object-valued fields, unexpected shapes, duplicates and empty results are unknown outcomes, not success. Extra response fields are discarded. The local identifier syntax is conservative (32-character hexadecimal IDs as illustrated by the pinned design-system tool-schema examples); an unrecognized future format requires reconciliation, not printing raw values. The CLI never logs the response body or key. On timeouts, malformed responses or HTTP errors, reconcile via get_project/list_screens/get_screen before deciding a new write.

### Supported File Types

| Extension | MIME Type |
|:---|:---|
| `.png` | `image/png` |
| `.jpg`, `.jpeg` | `image/jpeg` |
| `.webp` | `image/webp` |
| `.html`, `.htm` | `text/html` |
| `.md` | `text/markdown` |

The script auto-detects MIME type from the file extension.

### Script Options

- `--project-id`: **Required**. The Stitch project ID.
- `--file-path`: **Required**. Path to the local file to upload.
- `--api-key`: Legacy compatibility flag. Prefer the `STITCH_API_KEY` environment variable.
- `--api-url`: Optional. Base URL of the Stitch API. Defaults to `https://stitch.googleapis.com`.
- `--title`: Optional. Title for the uploaded screen. When uploading extracted HTML from a web app, set this to the **route path** of the page (e.g., `'/dashboard'`, `'/settings/profile'`, `'/inbox'`) so that the screen name/title in Stitch clearly identifies the route.
- `--generated-by`: Optional. Specify how the uploaded file was generated (e.g., 'stitch-extract-static-html' skill, 'Claude Code', 'Codex', 'Gemini' etc.).
