# Stitch Design Functional Closure Design

> **Status:** Approved for implementation on 2026-09-14
>
> **Target releases:** 0.5.2 safety/protocol hotfix, then 0.6.0 end-to-end capability closure

## 1. Goal

Make Stitch Design a verifiable product workflow rather than a collection of mostly independent Skills: one installation source, one credential path, a protocol-correct MCP bridge, accurate coverage of the live Stitch tool catalog, safe local asset operations, and a Harness whose state cannot advance or archive without the evidence it claims.

## 2. Evidence baseline

- Source, `origin/main`, tag `v0.5.1`, GitHub Release, and installed Marketplace snapshot resolve to commit `07cb947c864e6c6dc94875078bca815c80d8a775`.
- The installed proxy completes MCP `2025-06-18` initialization and discovers 15 live Stitch tools.
- The real read chain `list_projects -> get_project -> list_screens -> get_screen` passes with the user-scoped credential.
- The legacy `com.partme.stitch-design` Keychain item has been deleted.
- A separate global MCP configuration named `stitch` still conflicts with the plugin-owned server name.
- Remote write, upload, download, design-system, edit, variant, cleanup, and Harness archive chains are not yet accepted.

## 3. Product boundaries

### 3.1 Default authentication

The default credential chain is current-process `STITCH_API_KEY`, then the restricted user configuration file. Default operations MUST NOT access a native system secret store. The broken `migrate` command and native-store implementations are removed from the user-facing runtime. The setup Skill uses `stitch_setup.py check`; it does not infer absence from the process environment alone.

### 3.2 MCP ownership

The plugin-owned stdio server is the only supported local Codex Stitch MCP source. Preflight fails with a precise remediation when `codex mcp get stitch` finds a separate global server. Removing that global entry is part of the authorized acceptance setup.

### 3.3 Trust model

Receipt hashes detect accidental or post-approval artifact changes; they are not signatures against a malicious local process. Documentation must call this cooperative local integrity, not cryptographic authorship proof. User approval remains an explicit action and must bind the exact required artifact set.

## 4. Release 0.5.2 requirements

### 4.1 Receipt and archive safety

- Evidence `step` values must come from a fixed allowlist and match the current state's expected step.
- Receipt filenames use a validated safe slug only; raw external values never become paths.
- Unknown write evidence validates its step before a receipt is written.
- `archive` re-runs receipt-chain and artifact-hash verification immediately before copying.
- The archive contains the run manifest and verifies its copied artifact hashes before publication.
- Approval must bind, at minimum: accepted roundtrip HTML, final Stitch render, accepted art render, and the three comparison images.
- A changed or missing approved artifact blocks archival even when the manifest state says `APPROVED`.

### 4.2 MCP protocol and schema safety

- `initialize` validation requires the matching response ID, no JSON-RPC error, a supported protocol result, and a `tools` capability.
- Preflight calls `tools/list`, follows cursors, validates the required live catalog, annotations, input/output schemas, and every local `$ref`.
- Known omitted definitions (`ScreenInstance`, `SelectedScreenInstance`, `File`) are injected before tool metadata reaches Codex.
- `list_projects` acceptance requires matching response ID and `structuredContent.projects` as a list.
- Request timeout defaults to 300 seconds and is configurable within a bounded range.
- Only HTTP 401 refreshes a credential and retries once. HTTP 403 is permission denied and is not replayed.
- HTTP 408 and 5xx for non-idempotent tools become `UnknownWriteResult`; callers must reconcile with reads.
- Read/write classification uses live tool annotations when available, with a conservative write default.

### 4.3 Skill contract repair

- `get_screen` always receives `name: projects/{project}/screens/{screen}`.
- `list_screens` receives a bare project ID.
- All conversion and design-analysis references use the same canonical resource-name helper wording.
- Model, device, font, and color-variant guidance follows the live schema; unsupported fixed enums are removed.
- `delete_project` receives a dedicated destructive Skill with exact target preview, explicit approval, a single call, and read-only reconciliation.
- Prompt-only and read-only Skills do not claim broad write access.
- A root router sends missing-credential work to local setup, reads to read Skills, writes to the UI designer/design-system manager, assets to local asset operations, and full delivery to the Harness.

### 4.4 Upload hardening

- Upload authentication uses `platform_secret_provider()`; `--api-key` is removed.
- Production uploads are pinned to `https://stitch.googleapis.com`; only an injected loopback transport is accepted by tests.
- Markdown uses the remote `upload_design_md` flow. Local private REST upload supports PNG, JPG, JPEG, WEBP, HTML, and HTM only.
- The response parser accepts the current `results[].screen` contract and fails closed on unknown shapes.
- Upload never follows redirects, never logs base64 or credentials, and never blindly retries.

## 5. Release 0.6.0 requirements

### 5.1 Local virtual asset tools

The stdio proxy adds two namespaced local tools without shadowing provider tools:

- `stitch_local_upload_asset(projectId, filePath, title?, createScreenInstances?)`
- `stitch_local_download_assets(projectId, outputDir, assetsSubdir?, screenNames?, referencedAssetPolicy?)`; `screenNames` carries already verified same-project resources when the live provider does not enumerate screens. `referencedAssetPolicy` defaults to `best_effort` and also accepts `strict`.

Both tools appear in `tools/list` with complete input/output schemas and annotations. Paths are validated, downloads are HTTPS allowlisted, signed URLs never enter argv or logs, writes stage into private temporary files, and final files are atomically published. Download validates status, Content-Type, maximum size, hashes, and contained output paths; it exports HTML, screenshots, referenced assets, and available DESIGN.md. Primary artifacts always fail closed. Under `best_effort`, a safe referenced dependency may be skipped after a download or content-validation failure and must produce a host-only warning; `strict` preserves all-or-nothing referenced-asset export. URL safety, path containment, size limits, successful-file limits, total export limits and an independent 500-URL discovery/request budget are never downgraded.

### 5.2 Executable Harness

- Add a checked-in page-spec JSON Schema and starter template.
- Add a `spec init` command that creates a non-overwriting starter spec.
- Add evidence builders for Stitch generation, ImageGen, OCR/business, roundtrip, editability, and visual review.
- After Stitch source acceptance, stop in `AWAITING_ART_DECISION` and ask the user to choose `enhance`, `keep_stitch`, or `cancel`. The decision command accepts only the user's exact canonical response through `--user-response`; it exposes no `--source user` override and performs no synonym or ambiguous-confirmation mapping. Only an exact `enhance` response may authorize ImageGen; the Harness must not infer this choice from the original request, a model recommendation, source acceptance, or replies such as “确认”“继续”“做按”.
- `keep_stitch` skips ImageGen, OCR, roundtrip, and image comparison, but still requires a reversible editability probe against the accepted Stitch HTML/render before entering final user approval. Its approval and archive artifact set binds the accepted Stitch source rather than synthetic art artifacts.
- `cancel` is terminal and records the decision without generating or archiving design artifacts.
- Page specs declare `source_mode`: `provider_generated` keeps strict Provider device/aspect/integer-scale validation; `imported_editable_html` accepts a mismatched Provider preview only when the evidence contains one actual render artifact whose dimensions exactly match the declared canvas and the editable HTML passes the same DOM/copy/business gates.
- OCR evidence fails whenever `observed_text_drift` is non-empty, even if the reduced critical-copy set would otherwise pass.
- Enhanced-art delivery inserts `SEMANTIC_NORMALIZED` between OCR acceptance and roundtrip. Its `stitch.normalize` receipt binds one raw editable HTML input, one normalized HTML output, and an explicit one-to-one `data-purpose` mapping. The output must equal the deterministic mapping result byte-for-byte and pass the page HTML gates before it may be uploaded and read back from Stitch.
- Layout comparison uses `coarse-edge-mae-v2`: grayscale images are blurred at a canvas-relative radius before edge MAE so illustration texture, shadows, and color enhancement do not masquerade as layout drift. Regression coverage requires texture-only changes to remain above the layout threshold while a geometric shift scores lower.
- Add a `compare` command that runs with the isolated Harness Python and writes three comparison images plus computed layout evidence.
- Editability evidence requires before, edited, restored HTML/render hashes and proves the restored hashes equal the before hashes.
- Unknown writes enter an explicit reconciliation state. Unknown evidence may bind a sanitized project ID and expected title. A `not_applied` result may use a successful screen inventory only when it binds the same project ID, declares complete pagination and contains normalized title hashes from which the Harness derives that the expected title is absent; only then may `get_screen` be `skipped/no_candidate_id`. Wrong-project, incomplete and matching inventories fail closed; any discovered candidate still requires `get_screen`. Attempts increment and block after three unresolved rounds.
- `BLOCKED` is resumable only through an explicit recovery command with a recorded reason.
- Archive publication is recoverable if copying succeeds but state persistence is interrupted.

### 5.3 CI and platform truth

- GitHub Actions runs unit tests, distribution validation, Skill validation, ShellCheck, secret scanning, and Python compilation on Ubuntu and macOS with Python 3.11 and 3.13.
- Windows runs Python unit/distribution tests and a proxy-launch smoke. Until that job and a real installed-host smoke pass, user docs say Windows code path only.
- A manual live-canary workflow accepts credentials only from repository secrets, creates a uniquely named temporary project, and guarantees cleanup in a final step.
- ChatGPT Web remains a separate, unproven product path.

## 6. Controlled live acceptance

After offline gates pass and the new plugin is installed, execute one authorized temporary project chain:

1. remove the separate global `stitch` MCP entry;
2. restart or create a fresh Codex task and prove plugin tool exposure;
3. create a uniquely named temporary project;
4. generate one minimal screen and read it back;
5. edit the screen and generate one variant;
6. create/update/list/apply one temporary design system;
7. upload one small local HTML or PNG through the local asset tool;
8. download and hash the project assets;
9. execute a minimal Harness run through comparison and explicit user approval evidence;
10. archive locally, verify the archive, delete the temporary remote project, and prove absence with `list_projects`.

No project identifiers, signed URLs, credentials, private HTML, or screenshots are written to public logs or release notes.

## 7. Release gates

Each release requires: clean unit suite, distribution validator, all Skill validators, link validation, ShellCheck, Python compilation, no secret-like content, independent code review, matching local/tracking/remote/tag SHA, GitHub Release, fresh Marketplace installation, installed-source diff, and a fresh-host smoke appropriate to the release claim.
