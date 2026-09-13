"""Repository-wide Skill contracts for the live Stitch tool catalog."""

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


class SkillContractTests(unittest.TestCase):
    def _skill_markdown(self):
        return sorted(path for path in SKILLS.rglob("*.md") if "LICENSE" not in path.name)

    def test_every_live_tool_has_an_owning_skill(self):
        tools = {tool["name"] for tool in json.loads(
            (ROOT / "tests/fixtures/stitch-tool-contract.json").read_text(encoding="utf-8")
        )["tools"]}
        ownership = {
            "stitch-mcp-create-project": {"create_project"},
            "stitch-delete-project": {"delete_project"},
            "stitch-mcp-generate-screen-from-text": {"generate_screen_from_text"},
            "stitch-mcp-get-project": {"get_project"},
            "stitch-mcp-get-screen": {"get_screen"},
            "stitch-mcp-list-projects": {"list_projects"},
            "stitch-mcp-list-screens": {"list_screens"},
            "stitch-upload-to-stitch": {"upload_design_md"},
            "stitch-manage-design-system": {
                "apply_design_system", "create_design_system",
                "create_design_system_from_design_md", "list_design_systems",
                "update_design_system",
            },
            "stitch-ui-designer": {"edit_screens", "generate_variants"},
        }
        for owner in ownership:
            self.assertTrue((SKILLS / owner / "SKILL.md").is_file(), owner)
        self.assertEqual(set().union(*ownership.values()), tools)

    def test_root_router_covers_setup_reads_writes_assets_and_delivery(self):
        router = (SKILLS / "stitch-design-use" / "SKILL.md").read_text(encoding="utf-8")
        for route in (
            "stitch-local-setup", "stitch-mcp-list-projects", "stitch-mcp-get-project",
            "stitch-mcp-list-screens", "stitch-mcp-get-screen", "stitch-ui-designer",
            "stitch-manage-design-system", "stitch-upload-to-stitch", "stitch-delivery-harness",
        ):
            self.assertIn(route, router)

    def test_canonical_screen_resource_arguments_are_used(self):
        bad_get = re.compile(
            r"get_screen`? with (?:the parsed )?`?projectId`? and `?screenId`?"
            r"|get_screen[^\n]*\{\s*[\"']projectId[\"']"
            r"|Numeric ID[^\n]*get_screen"
            r"|get_screen`? with the selected `screenId`",
            re.I,
        )
        bad_list = re.compile(
            r"list_screens[^\n]*\{\s*[\"']projectId[\"']\s*:\s*[\"']projects/"
            r"|Full Name[^\n]*list_screens",
            re.I,
        )
        relevant = [path for path in self._skill_markdown() if "get_screen" in path.read_text(encoding="utf-8") or "list_screens" in path.read_text(encoding="utf-8")]
        for path in relevant:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsNone(bad_get.search(text), "get_screen must receive name: projects/{project}/screens/{screen}")
                self.assertIsNone(bad_list.search(text), "list_screens must receive a bare projectId")

    def test_live_schema_guidance_does_not_freeze_removed_enums(self):
        paths = [
            SKILLS / "stitch-mcp-generate-screen-from-text",
            SKILLS / "stitch-manage-design-system",
            SKILLS / "stitch-ui-design-spec-generator",
        ]
        retired = ("GEMINI_3_PRO", "GEMINI_3_FLASH", "SMART_WATCH", "FRUIT_SALAD", "RAINBOW")
        for root in paths:
            for path in root.rglob("*.md"):
                text = path.read_text(encoding="utf-8")
                with self.subTest(path=path.relative_to(ROOT)):
                    for value in retired:
                        self.assertNotIn(value, text)

    def test_read_and_prompt_only_skills_do_not_claim_write_access(self):
        read_or_prompt = (
            "stitch-mcp-get-project", "stitch-mcp-get-screen", "stitch-mcp-list-projects",
            "stitch-mcp-list-screens", "stitch-ued-guide", "stitch-ui-design-spec-generator",
        )
        for name in read_or_prompt:
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            frontmatter = text.split("---", 2)[1]
            with self.subTest(skill=name):
                self.assertNotRegex(frontmatter, r"(?m)^allowed-tools:.*\bWrite\b")

    def test_delete_skill_requires_preview_approval_single_call_and_reconciliation(self):
        text = (SKILLS / "stitch-delete-project" / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ("projects/{project}", "明确批准", "仅调用一次", "list_projects", "删除前"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
