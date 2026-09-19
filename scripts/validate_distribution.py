#!/usr/bin/env python3
"""Validate the public Stitch compatibility-plugin distribution."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from scan_secrets import scan


EXPECTED_REPOSITORY = "https://github.com/full-stack-plugins/stitch-design-plugin"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def frontmatter_name(skill_file: Path) -> str:
    match = re.search(r"(?m)^name:\s*[\"']?([^\n\"']+)", skill_file.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"missing skill name: {skill_file}")
    return match.group(1).strip()


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    manifest = load_json(root / ".codex-plugin" / "plugin.json")
    mcp = load_json(root / ".mcp.json")
    marketplace = load_json(root / ".agents" / "plugins" / "marketplace.json")
    lock = load_json(root / "skills.lock.json")
    local_inventory = load_json(root / "plugin-local-skills.json")
    expected_version = str(manifest.get("version", "")).split("+", 1)[0]
    expected_skills = sum(
        len(source.get("skills", [])) for source in lock.get("sources", [])
    ) + len(local_inventory.get("skills", []))

    if manifest.get("name") != "stitch-design":
        errors.append("manifest name must be stitch-design")
    if not expected_version:
        errors.append("manifest version must be present")
    if manifest.get("repository") != EXPECTED_REPOSITORY:
        errors.append("manifest repository mismatch")
    interface = manifest.get("interface", {})
    if interface.get("displayName") != "Google Stitch Design":
        errors.append("display name must be Google Stitch Design")
    for field in ("privacyPolicyURL", "termsOfServiceURL"):
        value = interface.get(field, "")
        if not value.startswith(EXPECTED_REPOSITORY + "/blob/main/"):
            errors.append(f"invalid interface {field}")

    server = mcp.get("mcpServers", {}).get("stitch", {})
    expected_server = {
        "type": "stdio",
        "command": "python3",
        "args": ["scripts/stitch_mcp_proxy.py"],
        "cwd": ".",
    }
    if server != expected_server:
        errors.append("Stitch MCP must use the Python-only cross-platform stdio proxy")

    entries = [item for item in marketplace.get("plugins", []) if item.get("name") == "stitch-design"]
    if len(entries) != 1:
        errors.append("repository marketplace must contain one stitch-design entry")
    else:
        entry = entries[0]
        expected_source = {
            "source": "url",
            "url": EXPECTED_REPOSITORY + ".git",
            "ref": f"v{manifest['version'].split('+', 1)[0]}",
        }
        if entry.get("source") != expected_source:
            errors.append("repository marketplace source mismatch")
        if entry.get("policy") != {"installation": "AVAILABLE", "authentication": "ON_USE"}:
            errors.append("repository marketplace policy mismatch")

    if (root / "plugin.json").exists() or (root / "mcp.json").exists():
        errors.append("portable root manifests must remain inactive until portable auth exists")

    skill_dirs = sorted(path for path in (root / "skills").iterdir() if path.is_dir())
    if len(skill_dirs) != expected_skills:
        errors.append(f"expected {expected_skills} skills, found {len(skill_dirs)}")
    for skill_dir in skill_dirs:
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"missing SKILL.md: {skill_dir.name}")
            continue
        name = frontmatter_name(skill_file)
        if name != skill_dir.name or NAME_PATTERN.fullmatch(name) is None:
            errors.append(f"invalid skill identity: {skill_dir.name} -> {name}")

    for required in ("README.md", "README.zh-CN.md", "PRIVACY.md", "TERMS.md", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "requirements-test.txt", "requirements-harness.txt", "assets/setup/index.html", "assets/setup/styles.css", "assets/setup/app.js", "docs/Stitch-Design-Architecture.md", "docs/Stitch-Design-Architecture.zh_CN.md", "docs/Stitch-Design-Technical-Solution.md", "docs/Stitch-Design-Technical-Solution.zh_CN.md", "docs/getting-started.zh-CN.md", "docs/portable-migration.md", "scripts/stitch_setup.py", "scripts/stitch_setup.sh", "scripts/stitch_mcp_proxy.py", "scripts/stitch_harness.py", "scripts/setup_harness_runtime.py", "scripts/smoke_mcp_config.py", "scripts/validate_skills.py", "scripts/validate_markdown_links.py", "scripts/scan_secrets.py", "stitch_harness/mcp_proxy.py", "stitch_harness/assets.py", "stitch_harness/evidence_writer.py", "stitch_harness/spec.schema.json", "stitch_harness/spec-template.json"):
        if not (root / required).is_file():
            errors.append(f"missing required file: {required}")

    errors.extend(f"secret-like content detected: {finding}" for finding in scan(root))

    return errors


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors = validate(root)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    manifest = load_json(root / ".codex-plugin" / "plugin.json")
    lock = load_json(root / "skills.lock.json")
    local_inventory = load_json(root / "plugin-local-skills.json")
    expected_skills = sum(
        len(source.get("skills", [])) for source in lock.get("sources", [])
    ) + len(local_inventory.get("skills", []))
    version = str(manifest.get("version", "")).split("+", 1)[0]
    print(f"validated {expected_skills} skills and compatibility distribution {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
