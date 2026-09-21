"""Group 3 contract tests: the stitch-visual-judge plugin-local skill.

Covers:
- 3.1 the skill is declared in plugin-local-skills.json and does not collide
  with a managed (vendored) skill.
- 3.2 the skill enforces fresh-context independence and forbids the executor's
  diagnosis.
- 3.3 the scoring contract requires the five axes and a gap list with stable
  ids, descriptions, and repair directions.
- 3.4 the anti-ratchet rule is encoded (no obligation to raise, regression must
  score lower).
- 3.5 the skill reports the deterministic layout score and the judge scores as
  distinct sources.
"""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SKILL_DIR = ROOT / "skills" / "stitch-visual-judge"


class JudgeSkillContractTests(unittest.TestCase):
    def _skill_text(self) -> str:
        return (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    def test_3_1_skill_is_declared_plugin_local_and_not_managed(self):
        inventory = json.loads((ROOT / "plugin-local-skills.json").read_text(encoding="utf-8"))
        self.assertIn("stitch-visual-judge", inventory["skills"])
        lock = json.loads((ROOT / "skills.lock.json").read_text(encoding="utf-8"))
        managed = {
            name
            for source in lock["sources"]
            for name in source["skills"]
        }
        self.assertNotIn("stitch-visual-judge", managed)

    def test_3_1_skill_structure_validates(self):
        errors = []
        skill_file = SKILL_DIR / "SKILL.md"
        if not skill_file.is_file():
            errors.append("SKILL.md missing")
        self.assertEqual(errors, [])
        text = self._skill_text()
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("name: stitch-visual-judge", text)

    def test_3_2_independence_rules_present(self):
        text = self._skill_text()
        self.assertIn("fresh context", text.lower())
        self.assertIn("Never receive the executor's own diagnosis", text)

    def test_3_3_scoring_contract_axes_and_gap_shape(self):
        text = self._skill_text()
        for axis in ("hierarchy", "density", "color", "component_quality", "completion"):
            self.assertIn(axis, text)
        contract = (SKILL_DIR / "references" / "scoring-contract.md").read_text(encoding="utf-8")
        for required in ('"id"', '"description"', '"repair"'):
            self.assertIn(required, contract)
        self.assertIn("stable", contract.lower())

    def test_3_4_anti_ratchet_encoded(self):
        text = self._skill_text()
        self.assertIn("Anti-ratchet", text)
        self.assertIn("regressed", text.lower())

    def test_3_5_distinct_sources_reporting(self):
        text = self._skill_text()
        self.assertIn("distinct", text.lower())
        self.assertIn("layout_score", text)


if __name__ == "__main__":
    unittest.main()
