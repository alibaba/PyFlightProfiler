import os
import re
import unittest

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
SKILLS_DIR = os.path.join(REPO_ROOT, "skills")

# `_install_skills` reads the description straight off this line, so the format
# is load-bearing rather than cosmetic.
FRONTMATTER_FIELD = re.compile(r"^(name|description):\s*(.+?)\s*$")


def skill_directories():
    if not os.path.isdir(SKILLS_DIR):
        return []
    return sorted(
        name
        for name in os.listdir(SKILLS_DIR)
        if name.startswith("flight-profiler-")
        and os.path.isdir(os.path.join(SKILLS_DIR, name))
    )


def read_frontmatter(skill_name):
    """Parse the leading `---` block of a SKILL.md into a dict."""
    path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
    fields = {}
    with open(path, encoding="utf-8") as handle:
        first = handle.readline().strip()
        if first != "---":
            return fields
        for line in handle:
            if line.strip() == "---":
                break
            match = FRONTMATTER_FIELD.match(line)
            if match:
                fields[match.group(1)] = match.group(2)
    return fields


def read_doc(relative_path):
    with open(os.path.join(REPO_ROOT, relative_path), encoding="utf-8") as handle:
        return handle.read()


@unittest.skipIf(not skill_directories(), "skills/ is not present in this layout")
class SkillCatalogueTest(unittest.TestCase):
    """Guards the contract `flight_profiler install-skills` relies on."""

    def test_every_skill_directory_has_a_skill_file(self):
        for skill in skill_directories():
            path = os.path.join(SKILLS_DIR, skill, "SKILL.md")

            self.assertTrue(os.path.isfile(path), f"{skill} has no SKILL.md")

    def test_frontmatter_name_matches_the_directory(self):
        # install-skills copies by directory name; an agent selects by the
        # frontmatter name. They have to agree or the skill is unreachable.
        for skill in skill_directories():
            self.assertEqual(skill, read_frontmatter(skill).get("name"), skill)

    def test_every_skill_has_a_single_line_description(self):
        for skill in skill_directories():
            description = read_frontmatter(skill).get("description", "")

            self.assertTrue(description, f"{skill} has no description")
            self.assertNotIn("\n", description, skill)

    def test_descriptions_say_when_to_use_the_skill(self):
        # A description is how an agent decides whether to load the skill at
        # all, so a bare restatement of the name is not enough.
        for skill in skill_directories():
            description = read_frontmatter(skill).get("description", "")

            self.assertGreater(len(description), 60, f"{skill}: {description!r}")

    def test_every_skill_is_listed_in_the_readme(self):
        readme = read_doc("README.md")

        for skill in skill_directories():
            self.assertIn(f"`{skill}`", readme, f"{skill} missing from README.md")

    def test_every_skill_is_listed_in_both_wikis(self):
        for doc in ("docs/WIKI.md", "docs/WIKI_zh.md"):
            content = read_doc(doc)
            for skill in skill_directories():
                self.assertIn(f"`{skill}`", content, f"{skill} missing from {doc}")


if __name__ == "__main__":
    unittest.main()
