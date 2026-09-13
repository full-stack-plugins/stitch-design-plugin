# Stitch Design First-Use Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local three-step browser wizard that saves a Stitch API key to the current user's restricted configuration and launches Codex with `STITCH_API_KEY`.

**Architecture:** Extend the Python setup utility with a loopback-only HTTP server and three bundled static assets. The key is posted only to `127.0.0.1`, validated with a per-run CSRF token, atomically saved, removed from the UI, and injected only into a newly launched child process.

**Tech Stack:** Python 3 standard library, semantic HTML, CSS, vanilla JavaScript, unittest.

**Spec:** `docs/superpowers/specs/2026-09-13-stitch-first-use-onboarding-design.md`

## Global Constraints

- Ordinary users see only: get key, save key, reopen Codex.
- No external JavaScript, fonts, images, analytics, or public service.
- Never place the key in URLs, logs, browser storage, page source, error responses, or Git.
- Preserve `ON_USE` and the existing `.mcp.json` environment-header mapping.
- Advanced commands remain collapsed by default.
- Validate at 390×884, 768×1024, and 1280×1024.
- Do not commit or push without separate authorization.

---

### Task 1: Credential and launch core

**Files:**
- Modify: `scripts/stitch_setup.py`
- Create: `tests/test_stitch_setup.py`
- Modify: `tests/test_distribution.py`

**Interfaces:**
- Produces: `save_key(key: str, destination: Path) -> None`
- Produces: `load_key() -> str | None`
- Produces: `launch_command(arguments: list[str], wait: bool) -> int`

- [ ] **Step 1: Write failing tests**

Test blank-key rejection, Unix `0600` file mode, existing-environment precedence, missing executable handling, child environment injection, and secret-free output.

- [ ] **Step 2: Verify RED**

Run:

```bash
python3 -m unittest -v tests.test_stitch_setup
```

Expected: FAIL because the dedicated test module and reusable launch interface do not exist.

- [ ] **Step 3: Implement minimal reusable core**

Refactor the current setup script so `run_command` delegates to `launch_command`. Waiting CLI commands use `subprocess.call`; desktop launches use `subprocess.Popen` with the same key-injected environment. Never include the key in process arguments.

- [ ] **Step 4: Verify GREEN**

```bash
python3 -m unittest -v tests.test_stitch_setup tests.test_distribution
```

Expected: PASS with zero failures.

- [ ] **Step 5: Commit only if separately authorized**

```bash
git add scripts/stitch_setup.py tests/test_stitch_setup.py tests/test_distribution.py
git commit -m "refactor: prepare Stitch onboarding launch core"
```

---

### Task 2: Loopback setup server

**Files:**
- Modify: `scripts/stitch_setup.py`
- Modify: `tests/test_stitch_setup.py`

**Interfaces:**
- Produces: `create_setup_server(host="127.0.0.1", port=0)`
- Produces: CLI command `stitch_setup.py ui`
- Consumes: `save_key`, `config_path`, `launch_command`

- [ ] **Step 1: Write failing HTTP security tests**

Use real loopback requests to assert:

- GET `/` sets `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and restrictive CSP.
- POST `/api/save` rejects missing CSRF, wrong Origin, non-JSON, blank keys, and bodies larger than 8192 bytes.
- Valid save persists the key but never includes it in the response.
- POST `/api/launch` requires the same CSRF token.

- [ ] **Step 2: Verify RED**

```bash
python3 -m unittest -v tests.test_stitch_setup.SetupServerTests
```

Expected: FAIL because the server interface does not exist.

- [ ] **Step 3: Implement the local server**

Use `ThreadingHTTPServer(("127.0.0.1", 0), Handler)` and `secrets.token_urlsafe(32)`. Serve only `/`, `/styles.css`, and `/app.js`. Override request logging so bodies and query data are never logged. Add `ui` to start the server, open the browser, and stop after completion or ten minutes.

- [ ] **Step 4: Verify GREEN**

```bash
python3 -m unittest -v tests.test_stitch_setup tests.test_distribution
```

Expected: PASS with zero failures.

- [ ] **Step 5: Commit only if separately authorized**

```bash
git add scripts/stitch_setup.py tests/test_stitch_setup.py
git commit -m "feat: add loopback Stitch setup server"
```

---

### Task 3: Three-step onboarding page

**Files:**
- Create: `assets/setup/index.html`
- Create: `assets/setup/styles.css`
- Create: `assets/setup/app.js`
- Modify: `tests/test_stitch_setup.py`
- Modify: `scripts/validate_distribution.py`

**Interfaces:**
- Consumes: POST `/api/save` with `csrfToken` and `apiKey`
- Consumes: POST `/api/launch` with `csrfToken` and `target`
- Produces: accessible three-step UI

- [ ] **Step 1: Write failing static UI tests**

Assert exactly three `setup-step` sections, one password input, one collapsed `details` block, no external assets, no browser storage, and no logging calls.

- [ ] **Step 2: Verify RED**

```bash
python3 -m unittest -v tests.test_stitch_setup.StaticUiTests
```

Expected: FAIL because the assets do not exist.

- [ ] **Step 3: Implement the page**

Create:

- Step 1 “获取 Key” with a button to Stitch Settings.
- Step 2 masked input, reveal control, and “保存到本机”.
- Step 3 success state and “打开 Codex”, disabled before save.
- A polite live-status region and collapsed “高级设置”.

JavaScript keeps the key only in the input value, posts it once, clears the field after every response, and never writes it to DOM text, URL, console, or storage. CSS uses a centered card, soft neutral background, 44px targets, visible focus, and responsive rules for the three required sizes.

- [ ] **Step 4: Verify GREEN**

```bash
python3 -m unittest -v tests.test_stitch_setup tests.test_distribution
python3 scripts/validate_distribution.py .
```

Expected: PASS; distribution reports 40 skills and version 0.4.0.

- [ ] **Step 5: Commit only if separately authorized**

```bash
git add assets/setup scripts/validate_distribution.py tests/test_stitch_setup.py
git commit -m "feat: add three-step Stitch onboarding page"
```

---

### Task 4: First-use routing and final verification

**Files:**
- Modify: `skills/stitch-local-setup/SKILL.md`
- Modify: `skills/stitch-local-setup/references/workflow.md`
- Modify: `skills/stitch-local-setup/references/anti-patterns.md`
- Modify: `skills/stitch-local-setup/references/faq-deep.md`
- Modify: `skills/stitch-local-setup/examples/local-validation.md`
- Modify: `README.md`
- Modify: `docs/getting-started.zh-CN.md`
- Modify: `PRIVACY.md`
- Modify: `tests/test_distribution.py`

**Interfaces:**
- Consumes: `stitch_setup.py ui`
- Produces: one UI-opening action as the normal first-use response

- [ ] **Step 1: Write failing routing tests**

Require the Skill and guide to contain “打开本地设置向导”, `stitch_setup.py ui`, the three step names, and the advanced-mode boundary. Require raw environment commands to appear only in advanced documentation.

- [ ] **Step 2: Verify RED**

```bash
python3 -m unittest -v tests.test_distribution.DistributionContractTests.test_first_use_skill_routes_missing_credentials_to_local_setup
```

Expected: FAIL because command-line setup is still the primary path.

- [ ] **Step 3: Update routing and documentation**

The normal first-use action is:

```bash
python3 /absolute/plugin/root/scripts/stitch_setup.py ui
```

Use `py` on Windows. When authorized, the agent opens the UI; otherwise it returns one exact command. Keep ChatGPT web marked as waiting for a formal connector/OAuth.

- [ ] **Step 4: Run all automated gates**

```bash
python3.13 /Users/wandl/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/stitch-local-setup
python3 -m unittest -v tests
python3 scripts/validate_distribution.py .
sh -n scripts/stitch_setup.sh
shellcheck scripts/stitch_setup.sh
git diff --check
```

Expected: every command exits zero.

- [ ] **Step 5: Visual verification**

Open the local UI without a real key. At 390×884, 768×1024, and 1280×1024 verify no horizontal overflow, readable central card, accessible input/buttons, visible focus, and collapsed advanced settings. Confirm no request occurs before Save.

- [ ] **Step 6: TRACE verification**

Evaluate Trust, Reliability, Adaptability, Convention, and Effectiveness. Fix every sub-item below 5.0.

- [ ] **Step 7: Commit only if separately authorized**

```bash
git add skills/stitch-local-setup README.md docs/getting-started.zh-CN.md PRIVACY.md tests/test_distribution.py
git commit -m "docs: make Stitch first-use setup visual"
```
