# Stitch Design Technical Solution

> **Scope:** Implementation decisions, interfaces, security controls, tests, release, and migration for Stitch Design 0.8.0.
>
> **Updated:** 2026-09-14

[简体中文](Stitch-Design-Technical-Solution.zh_CN.md) | [Architecture](Stitch-Design-Architecture.md)

## 1. Solution baseline

| Area | Selected solution | Reason |
|:---|:---|:---|
| Host packaging | Codex compatibility manifest | Currently supported and verified |
| Tool transport | Bundled stdio proxy to Google Stitch HTTP MCP | Reliable host integration and provider-owned execution |
| Authentication | Process environment or restricted user configuration | Avoids interactive system prompts and keeps the key outside the package |
| Workflow layer | 43 Agent Skills plus Delivery Harness | Precise discovery and verified delivery |
| First-use UI | Python stdlib loopback server + static assets | No new runtime dependency |
| Credential persistence | Cross-platform current-user JSON with restricted permissions | Predictable non-interactive behavior |
| Validation | Python unittest + distribution validator + ShellCheck | Reproducible offline gates |

## 2. Decision records

| Decision | Rationale | Reversal condition |
|:---|:---|:---|
| Ship a compatibility package with a local stdio proxy | Keeps the key out of committed configuration and lets one component own credential refresh | If the host offers a first-class credential provider |
| Publish 43 focused Skills instead of one omnibus Skill | Progressive disclosure keeps the loaded context small and the routing precise | None |
| Inject two local asset tools beside the 15 upstream tools | Upstream exposes no local file import or export, so the local pair is declared rather than implied | If upstream adds equivalent tools |
| Keep the delivery Harness as an interactive local controller | Long delivery flows need explicit human gates, not autonomous approval | If the host provides durable job orchestration with approvals |
| Refuse to resubmit after an unknown write result | A duplicate write can create duplicate remote state and duplicate spend | If the remote API exposes an idempotency key |
| Keep the portable and public migration inactive | The public path requires a remote HTTPS MCP review that has its own acceptance process | When that review is available and explicitly requested |
| Require Python 3.11 or newer on `PATH` | The proxy and Harness use modern standard-library features | If the minimum supported host interpreter changes |

## 3. Repository mapping

| Path | Contract |
|:---|:---|
| `.codex-plugin/plugin.json` | Plugin identity, version, presentation, MCP path |
| `.agents/plugins/marketplace.json` | Public Git source and `ON_USE` policy |
| `.mcp.json` | Bundled stdio proxy command and plugin-root working directory |
| `stitch_harness/` | Contracts, proxy, gates, receipts, state and archive |
| `skills/` | Workflow and conversion contracts |
| `scripts/stitch_setup.py` | Setup, check, run, CLI, desktop, UI server |
| `scripts/live_canary.py` | Bounded provider/asset smoke, strict MCP parsing, sanitized evidence and cleanup reconciliation |
| `docs/live-harness-controller.md`, `docs/live-harness-controller.zh_CN.md` | Separate interactive real-Harness acceptance path, in English and Chinese |
| `assets/setup/` | Single-card onboarding page |
| `scripts/validate_distribution.py` | Package contract and secret-like pattern scan |
| `tests/` | Distribution, credential, HTTP security, and UI structure tests |

The runtime remains Python-only. On every supported host, PATH `python` must resolve to Python 3.11 or newer; `.mcp.json`, setup instructions, and CI all use that exact command.

## 4. First-use implementation

```mermaid
sequenceDiagram
    participant S as MCP proxy
    participant U as User
    participant L as Local Wizard
    participant F as Restricted User Config
    S->>S: resolve credential
    alt missing
      S->>S: acquire 10-minute launch marker
      S->>L: detached ui on 127.0.0.1 random port
      L-->>U: single-card Token page
      U->>L: submit masked key
      L->>L: Origin + CSRF + size + JSON validation
      L->>F: atomic write
      L->>L: clear input
      U->>S: retry the original request
    end
```

HTTP routes:

| Route | Method | Purpose | Guard |
|:---|:---:|:---|:---|
| `/` | GET | HTML shell | no-store + CSP |
| `/styles.css` | GET | Local styles | same origin |
| `/app.js` | GET | Local interaction | same origin |
| `/api/save` | POST | Validate and persist key | Origin, CSRF, JSON, 8192-byte cap |
| `/api/launch` | POST | Launch Codex child process | Origin and CSRF |

The server overrides request logging and never returns submitted values. The UI does not use cookies, localStorage, sessionStorage, remote assets, or telemetry.

## 5. Credential configuration

```mermaid
flowchart TD
    Start(["First Stitch use"]) --> Env{"STITCH_API_KEY in current process?"}
    Env -->|Yes| Direct["Use process value"]
    Env -->|No| Store{"Restricted user config contains key?"}
    Store -->|Yes| Inject["Read once inside local stdio proxy"]
    Store -->|No| Gate{"Launch marker is fresh?"}
    Gate -->|No| Wizard["Open local setup wizard"]
    Gate -->|Yes| Wait["Keep current wizard; do not reopen"]
    Wizard --> Save["Validate and save key"]
    Save --> Inject
    Wait --> Save
    Direct --> Ready(["Invoke Stitch MCP"])
    Inject --> Ready
```

The wizard writes to the restricted current-user configuration.

Key rotation: open the UI, save the new key, start a new Codex process, run read-only `list_projects`, then revoke the old key in Stitch Settings.

### 4.1 Loopback request flow

```mermaid
sequenceDiagram
    participant B as Browser
    participant H as 127.0.0.1 server
    participant V as Request validator
    participant F as Restricted user config
    B->>H: GET / with per-run CSRF token
    H-->>B: local assets + no-store + CSP
    B->>H: POST /api/save (Origin, CSRF, JSON)
    H->>V: check origin, token, type, and size
    alt valid request
      V->>F: restricted atomic replacement
      F-->>V: saved
      V-->>B: success without key value
    else invalid request
      V-->>B: generic error without echo
    end
```

## 6. MCP, Harness, and Skill behavior

The local stdio proxy owns MCP initialization, session headers, JSON/SSE responses, secret redaction, and a single refresh/retry only for HTTP 401. HTTP 403 is permission denied and is never refreshed or replayed. The Delivery Harness owns page contracts, finite states, deterministic gates, receipt hashes, recovery, explicit approval, and archive publication. Agent Skills invoke the real Stitch, ImageGen, OCR, and visual tools and import normalized evidence; provider success text alone is never accepted.

```mermaid
flowchart LR
    Codex --> Proxy[Local stdio MCP proxy]
    Proxy --> Stitch[Google Stitch MCP]
    Codex --> Skill[Delivery Harness Skill]
    Skill --> Core[Local state and gates]
    Skill --> Providers[Stitch / ImageGen / OCR]
    Core --> Receipts[Project receipts and archive]
```

The plugin does not reimplement Stitch SDK methods. It delegates live project, screen, design-system, generation, editing, variant, upload, and artifact behavior to the discovered Stitch MCP tools. Skills own task routing, local preparation, parameter checks, scope control, and ambiguous-write recovery.

Write recovery rule:

```mermaid
flowchart LR
    W["Write call"] --> R{"Definite result?"}
    R -->|Yes| D["Return verified result"]
    R -->|No / timeout| P["Read project/screen probes"]
    P --> F{"Remote result found?"}
    F -->|Yes| D
    F -->|No| U["Report unknown; do not resubmit"]
```

## 7. Security controls

| Threat | Control | Evidence |
|:---|:---|:---|
| Key committed to package | Environment mapping and secret scan | Validator |
| Cross-site local POST | Exact Origin and CSRF validation | HTTP tests |
| Oversized/malformed request | JSON content type and 8192-byte limit | Handler/tests |
| Browser persistence | No storage APIs; clear input | `app.js` |
| External content execution | Self-only CSP and bundled assets | Response headers |
| Exported HTML dependencies | Any public HTTPS hostname; reject credentials, local/internal names, IP literals, redirects, size and MIME violations | Local asset downloader |
| Duplicate remote writes | Read-before-retry workflow | Skill contracts |
| Shared identity | User-provided key only | Privacy and setup docs |

## 8. Verification and release

```mermaid
flowchart LR
    Source["Working tree"] --> Unit["Unit suite"]
    Source --> Dist["Distribution validator"]
    Source --> Skill["Skill structure validation"]
    Source --> Shell["ShellCheck"]
    Source --> Secrets["Secret-pattern scan"]
    Source --> Visual["390 · 768 · 1280 px visual QA"]
    Unit --> Gate{"All gates pass?"}
    Dist --> Gate
    Skill --> Gate
    Shell --> Gate
    Secrets --> Gate
    Visual --> Gate
    Gate -->|Yes| Publish["Commit · push · tag · release"]
    Gate -->|No| Fix["Correct and rerun affected gates"]
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
actionlint .github/workflows/live-canary.yml
git diff --check
```

The live workflow is intentionally excluded from push and pull-request triggers. It performs provider + asset smoke only, not Harness acceptance. Authentication is mapped only from the `STITCH_API_KEY` repository secret. Opaque identifiers remain in private runner state: POSIX applies `0600`; Windows uses current-user runner temp/profile ACLs without POSIX mode calls. Cleanup can recover a missing resource name only through bounded exact-title reads, then checkpoints identity before one delete; bounded absence reads follow every delete outcome. Variant acceptance requires exactly one same-project identity different from the source. Full Harness acceptance uses the [local Harness controller](live-harness-controller.md).

Release proof for 0.4.0:

- commit/tag/remote SHA: `6cf533ee884157a5a265c6200bbff6842b62c0f5`;
- 16 automated tests passed;
- 40 Skills validated;
- public Marketplace install resolved version 0.4.0;
- installed artifact matched source except local `.DS_Store`;
- onboarding rendered at 390×884, 768×1024, and 1280×1024.

## 9. Limitations and roadmap

| Item | Current status | Exit condition |
|:---|:---|:---|
| ChatGPT web | Experimental | Verified connector/OAuth and `list_projects` |
| Portable Agent Plugins manifest | Blocked | Portable credential reference or OAuth |
| Encrypted local vault | Not implemented | Host-managed secret UI/store |
| Windows live acceptance | Code path only | Real Windows host validation |
| Continuous remote CI | Workflow configured; remote run unverified | Observe successful GitHub Actions runs |

---

**Document version:** 2.7.10 · **Status:** Aligned with the 0.8.0 release candidate

## 10. Evidence map

| Claim | Evidence |
|:---|:---|
| MCP surface and proxy behaviour | `stitch_harness/mcp_proxy.py`, `stitch_harness/tool_catalog.py` |
| Local asset tools | `stitch_harness/assets.py` |
| Credential handling and storage | `stitch_harness/secrets.py`, `scripts/stitch_setup.py` |
| Skill catalogue | `skills/`, `scripts/validate_skills.py` |
| Harness gates and run state | `stitch_harness/orchestrator.py`, `stitch_harness/state.py` |
| Download allowlist | `scripts/validate_distribution.py` and the boundary tests |
| Verification records | `docs/live-canary-acceptance.md`, `docs/live-harness-controller.md` |
