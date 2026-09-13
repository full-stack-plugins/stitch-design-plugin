# Stitch Design Functional Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a safe 0.5.2 protocol hotfix followed by a 0.6.0 executable Stitch design-delivery loop.

**Architecture:** Keep the dependency-free Python stdio bridge, repair provider schemas at the boundary, and add namespaced local asset tools rather than introducing a Node runtime. Harden the existing finite-state Harness so state, receipts, approval, comparison, and archive share one enforceable contract.

**Tech Stack:** Python 3.11+, stdlib HTTP/JSON/path primitives, optional isolated Pillow 12.3.0, Agent Skills, GitHub Actions, unittest.

**Spec:** `docs/superpowers/specs/2026-09-14-stitch-functional-closure-design.md`

## Global Constraints

- Default credential reads are environment then restricted user configuration; native secret stores are never touched implicitly.
- Credentials, authorization headers, base64 bodies, signed URLs, and private project data never enter logs, argv, receipts, tests, or releases.
- Every behavior change follows RED -> GREEN -> regression verification.
- Remote write tests use one authorized temporary project and always attempt verified cleanup.
- 0.5.2 and 0.6.0 have separate commits, tags, releases, installations, and evidence.

---

### Task 1: Harden Harness receipts, approval, and archive

**Files:**
- Modify: `stitch_harness/evidence.py`
- Modify: `stitch_harness/storage.py`
- Modify: `stitch_harness/orchestrator.py`
- Modify: `stitch_harness/archive.py`
- Modify: `stitch_harness/cli.py`
- Test: `tests/test_external_evidence.py`
- Test: `tests/test_harness_state.py`
- Test: `tests/test_harness_orchestrator.py`
- Test: `tests/test_harness_archive.py`

**Interfaces:** Produces safe `Receipt.step`, `RunStore.required_approval_artifacts(run)`, `RunStore.verify_approval(run)`, and archive-time chain verification.

- [ ] Add failing tests for an unknown step outside the allowlist, approval with an incomplete artifact set, modified approved artifacts, and archive attempts with an invalid chain.
- [ ] Run the four focused test modules and confirm each new test fails for the intended missing guard.
- [ ] Implement fixed step validation, safe receipt filenames, required approval artifact derivation, archive-time verification, and manifest inclusion.
- [ ] Run the focused modules and the full suite; commit `fix: enforce harness evidence and archive gates`.

### Task 2: Harden MCP lifecycle, schemas, and failure semantics

**Files:**
- Create: `stitch_harness/tool_catalog.py`
- Modify: `stitch_harness/mcp_proxy.py`
- Modify: `stitch_harness/preflight.py`
- Create: `tests/fixtures/stitch-tool-contract.json`
- Modify: `tests/test_mcp_proxy.py`
- Modify: `tests/test_preflight.py`

**Interfaces:** Produces `repair_tool_schemas(tools)`, `validate_tool_catalog(tools)`, `ToolCatalog`, annotation-based `is_write_tool(name)`, and strict `stitch_read_probe`.

- [ ] Add failing tests for missing `$defs`, wrong initialize ID/error, missing tools capability, wrong final response ID, malformed projects, duplicate global MCP, 403 replay, write 502 classification, and the 300-second default.
- [ ] Run focused tests and confirm RED.
- [ ] Implement schema repair for `ScreenInstance`, `SelectedScreenInstance`, and `File`; cursor-aware catalog validation; strict response validation; bounded timeout configuration; 401-only refresh; unknown-write classification for 408/5xx; and global-MCP collision detection.
- [ ] Run focused and full tests; commit `fix: validate Stitch MCP lifecycle and schemas`.

### Task 3: Repair setup, upload, and Skill contracts

**Files:**
- Modify: `scripts/stitch_setup.py`
- Modify: `stitch_harness/secrets.py`
- Modify: `skills/stitch-upload-to-stitch/scripts/upload_to_stitch.py`
- Modify: `skills/stitch-upload-to-stitch/tests/test_upload.py`
- Modify: `skills/stitch-local-setup/**`
- Modify: `skills/stitch-mcp-*/**`
- Modify: `skills/stitch-manage-design-system/**`
- Modify: affected conversion Skills and references
- Create: `skills/stitch-delete-project/**`
- Create: `skills/stitch-design-use/**`
- Modify: distribution tests and bilingual documents

**Interfaces:** Produces one canonical resource-name contract, config-backed upload authentication, exact Google upload origin, current upload response projection, destructive delete workflow, and root routing workflow.

- [ ] Add failing tests for config-only setup detection, absence of `migrate`, rejected non-Google upload origin, absence of `--api-key`, current `results[].screen` parsing, correct `get_screen` wording across all Skills, bare `list_screens` ID, and tool-to-Skill coverage.
- [ ] Run focused tests and confirm RED.
- [ ] Remove the broken migration surface, update setup detection, harden upload, repair all schema references/enums, add delete/router Skills, and narrow prompt/read-only permissions.
- [ ] Run upload tests, all Skill validators, link checks, distribution validation, and the full suite; commit `fix: align Stitch workflows with live tool contracts`.

### Task 4: Publish and verify 0.5.2

**Files:**
- Modify: `.codex-plugin/plugin.json`
- Modify: version assertions and release-status documentation
- Create: `.github/workflows/validate.yml`

**Interfaces:** Produces the public 0.5.2 hotfix and one installed plugin source.

- [ ] Add failing distribution tests for 0.5.2 and CI workflow gates, then implement the version/CI metadata.
- [ ] Run all offline gates and independent review.
- [ ] Remove the authorized global `stitch` MCP entry, push main, tag `v0.5.2`, publish GitHub Release, upgrade Marketplace, remove older enabled installs, and open a fresh task.
- [ ] Verify source/tracking/remote/tag/release/installed SHA and installed-source equality; prove handshake, 15 repaired tools, and the four-step read chain.

### Task 5: Add local asset tools and executable Harness 0.6.0

**Files:**
- Create: `stitch_harness/assets.py`
- Create: `stitch_harness/evidence_writer.py`
- Create: `stitch_harness/spec.schema.json`
- Create: `stitch_harness/spec-template.json`
- Modify: `stitch_harness/mcp_proxy.py`
- Modify: `stitch_harness/state.py`
- Modify: `stitch_harness/orchestrator.py`
- Modify: `stitch_harness/cli.py`
- Modify: `scripts/stitch_harness.py`
- Modify: `scripts/setup_harness_runtime.py`
- Modify: `skills/stitch-delivery-harness/**`
- Create/modify corresponding unit tests

**Interfaces:** Produces `stitch_local_upload_asset`, `stitch_local_download_assets`, `spec init`, typed evidence writers, `compare`, explicit reconciliation state, attempt limit, and recoverable archive publication.

- [ ] Add failing tests for local tool discovery/calls, path containment, HTTPS/host/type/size limits, atomic output, spec non-overwrite, evidence templates, comparison CLI, edit/restore hash parity, three unresolved attempts, recovery, and interrupted archive recovery.
- [ ] Run focused tests and confirm RED.
- [ ] Implement the local tools and Harness commands without adding a runtime dependency to normal MCP use.
- [ ] Run focused/full tests, all Skill validators, and independent review; bump to 0.6.0 and commit `feat: close the Stitch delivery workflow`.

### Task 6: Execute controlled live Canary and publish 0.6.0

**Files:**
- Create: `.github/workflows/live-canary.yml`
- Modify: README, architecture, technical solution, and acceptance evidence documentation

**Interfaces:** Produces sanitized live acceptance evidence and the public 0.6.0 release.

- [ ] Add a manual workflow with guaranteed cleanup and secret-only authentication; validate its syntax without running it remotely.
- [ ] Install the local 0.6.0 candidate and prove fresh-task tool exposure.
- [ ] Create one uniquely named temporary project; execute generate/read/edit/one-variant/design-system/upload/download/Harness comparison and archive; record only sanitized booleans, counts, hashes, and timestamps.
- [ ] Delete the temporary project in a final cleanup step and prove it is absent.
- [ ] Run final offline gates and independent review, push/tag/release 0.6.0, upgrade Marketplace, and verify source/remote/tag/release/install equality.

