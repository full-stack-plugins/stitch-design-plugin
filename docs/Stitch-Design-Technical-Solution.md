# Stitch Design Technical Solution

> **Scope:** Implementation decisions, interfaces, security controls, tests, release, and migration for Stitch Design 0.4.0.
>
> **Updated:** 2026-09-13

[简体中文](Stitch-Design-Technical-Solution.zh_CN.md) | [Architecture](Stitch-Design-Architecture.md)

## 1. Solution baseline

| Area | Selected solution | Reason |
|:---|:---|:---|
| Host packaging | Codex compatibility manifest | Currently supported and verified |
| Tool transport | Google Stitch remote HTTP MCP | Provider-owned tool schema and execution |
| Authentication | `env_http_headers` from `STITCH_API_KEY` | Keeps key outside package |
| Workflow layer | 40 independent Agent Skills | Precise discovery and progressive disclosure |
| First-use UI | Python stdlib loopback server + static assets | No new runtime dependency |
| Credential persistence | User-scoped JSON with restricted permissions | Cross-platform compatibility |
| Validation | Python unittest + distribution validator + ShellCheck | Reproducible offline gates |

## 2. Repository mapping

| Path | Contract |
|:---|:---|
| `.codex-plugin/plugin.json` | Plugin identity, version, presentation, MCP path |
| `.agents/plugins/marketplace.json` | Public Git source and `ON_USE` policy |
| `.mcp.json` | Stitch URL and API-key header mapping |
| `skills/` | Workflow and conversion contracts |
| `scripts/stitch_setup.py` | Setup, check, run, CLI, desktop, UI server |
| `assets/setup/` | Single-card onboarding page |
| `scripts/validate_distribution.py` | Package contract and secret-like pattern scan |
| `tests/` | Distribution, credential, HTTP security, and UI structure tests |

## 3. First-use implementation

```mermaid
sequenceDiagram
    participant S as Setup Skill
    participant U as User
    participant L as Local Wizard
    participant F as User Config
    participant C as New Codex
    S->>S: check credential presence
    alt missing
      S->>L: start ui on 127.0.0.1 random port
      L-->>U: three-step page
      U->>L: submit masked key
      L->>L: Origin + CSRF + size + JSON validation
      L->>F: atomic write
      L->>L: clear input
      U->>L: open Codex
      L->>C: launch with STITCH_API_KEY
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

## 4. Credential configuration

```mermaid
flowchart TD
    Start(["First Stitch use"]) --> Env{"STITCH_API_KEY in current process?"}
    Env -->|Yes| Direct["Use process value"]
    Env -->|No| File{"User credential file exists?"}
    File -->|Yes| Inject["Load into a newly launched Codex process"]
    File -->|No| Wizard["Open local setup wizard"]
    Wizard --> Save["Validate and save key"]
    Save --> Inject
    Direct --> Ready(["Invoke Stitch MCP"])
    Inject --> Ready
```

The writer creates the parent directory before an atomic temporary-file replacement. Unix applies `0700` to the directory and `0600` to the file. Windows stores under the current user's `APPDATA` and inherits its ACL. This mechanism is a compatibility store, not an encrypted vault.

Key rotation: open the UI, save the new key, start a new Codex process, run read-only `list_projects`, then revoke the old key in Stitch Settings.

### 4.1 Loopback request flow

```mermaid
sequenceDiagram
    participant B as Browser
    participant H as 127.0.0.1 server
    participant V as Request validator
    participant F as Credential file
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

## 5. MCP and Skill behavior

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

## 6. Security controls

| Threat | Control | Evidence |
|:---|:---|:---|
| Key committed to package | Environment mapping and secret scan | Validator |
| Cross-site local POST | Exact Origin and CSRF validation | HTTP tests |
| Oversized/malformed request | JSON content type and 8192-byte limit | Handler/tests |
| Browser persistence | No storage APIs; clear input | `app.js` |
| External content execution | Self-only CSP and bundled assets | Response headers |
| Duplicate remote writes | Read-before-retry workflow | Skill contracts |
| Shared identity | User-provided key only | Privacy and setup docs |

## 7. Verification and release

```mermaid
flowchart LR
    Source["Working tree"] --> Unit["16 unit tests"]
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
python3 -m unittest discover -s tests -v
python3 scripts/validate_distribution.py .
python3.13 /Users/wandl/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/stitch-local-setup
shellcheck scripts/stitch_setup.sh
git diff --check
```

Release proof for 0.4.0:

- commit/tag/remote SHA: `6cf533ee884157a5a265c6200bbff6842b62c0f5`;
- 16 automated tests passed;
- 40 Skills validated;
- public Marketplace install resolved version 0.4.0;
- installed artifact matched source except local `.DS_Store`;
- onboarding rendered at 390×884, 768×1024, and 1280×1024.

## 8. Limitations and roadmap

| Item | Current status | Exit condition |
|:---|:---|:---|
| ChatGPT web | Experimental | Verified connector/OAuth and `list_projects` |
| Portable Agent Plugins manifest | Blocked | Portable credential reference or OAuth |
| Encrypted local vault | Not implemented | Host-managed secret UI/store |
| Windows live acceptance | Code path only | Real Windows host validation |
| Continuous remote CI | No workflow present | Add and verify GitHub Actions |

---

**Document version:** 1.1.0 · **Status:** Implementation-aligned
