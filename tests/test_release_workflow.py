"""The release workflow, `.github/workflows/release.yml`, held to its shape by `tools/check_workflows.py`'s
`release_problems` (#197's ruling 4′), and the version a cut asked with none is of. Each counter-example below is the
live file changed in one way, and the check names that way."""
from __future__ import annotations

import pathlib
import tempfile
import unittest

from release import cut
from tools import check_workflows

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIVE = (ROOT / ".github" / "workflows" / "release.yml").read_text()
STEP_ENV = "          RELEASE_TOKEN: ${{ steps.mint.outputs.token }}\n"


def caught(problems: list, words: str) -> bool:
    return len(problems) == 1 and words in problems[0]


class Shape(unittest.TestCase):
    def test_the_live_file_is_the_shape_and_keeps_every_other_rule(self):
        self.assertEqual(check_workflows.release_problems(LIVE), [])
        # It is spared the shim rule alone, which a workflow that moves the Release cannot keep: every other holds.
        self.assertEqual([rule for rule, _ in check_workflows.lint(LIVE)], ["shim", "shim"])
        self.assertEqual(check_workflows.SHAPED["release.yml"], ("shim",))
        self.assertEqual(check_workflows.run(), [])

    def test_each_counter_example_is_refused_for_its_one_fault(self):
        mint_with = "          permission-checks: read\n"
        cases = {
            "a second job": (LIVE + "  other:\n    runs-on: ubuntu-24.04\n    timeout-minutes: 5\n    permissions:\n"
                             "      contents: read\n    steps:\n      - run: make verify\n", "holds the job release and no other"),
            "another environment": (LIVE.replace("environment: factory-release", "environment: factory-next"),
                                    "runs on the environment factory-release"),
            "a job that writes": (LIVE.replace("    permissions:\n      contents: read\n",
                                               "    permissions:\n      contents: write\n"),
                                  "granted contents: read and nothing else"),
            "a checkout of a ref an output names": (LIVE.replace("        with:\n          persist-credentials: false\n",
                                                                 "        with:\n          ref: ${{ steps.mint.outputs.ref }}\n"
                                                                 "          persist-credentials: false\n"),
                                                    "its checkout step is given under with"),
            "a token for every repo": (LIVE.replace("          repositories: software-factory\n", ""),
                                       "its mint step is given under with"),
            "a token with more": (LIVE.replace(mint_with, mint_with + "          permission-administration: write\n"),
                                  "its mint step is given under with"),
            "another action mints": (LIVE.replace("64ab729a6294000f5aa4a4bc0b73d1f32bc45510 # v3.3.0",
                                                  "0000000000000000000000000000000000000000 # v3.2.0"),
                                     "its steps are mint, checkout, step"),
            "the token beside the job": (LIVE.replace("    environment: factory-release\n",
                                                      "    environment: factory-release\n    env:\n"
                                                      "      KEY: ${{ secrets.RELEASE_APP_KEY }}\n"),
                                         "its job has exactly"),
            "a step more": (LIVE + "      - run: make verify\n", "its steps are mint, checkout, step"),
            "the step given more": (LIVE.replace(STEP_ENV, STEP_ENV + "          GH_TOKEN: ${{ steps.mint.outputs.token }}\n"),
                                    "its step step is given under env"),
            "the schedule ungated": (LIVE.replace(" || (vars.FACTORY_RELEASE_AUTO == 'true' && (vars.FACTORY_PAUSED == '' "
                                                  "|| vars.FACTORY_PAUSED == 'false'))", " || true"),
                                     "only when FACTORY_RELEASE_AUTO is true"),
            "a cut under a Pause": (LIVE.replace(" && (vars.FACTORY_PAUSED == '' || vars.FACTORY_PAUSED == 'false')", ""),
                                    "only when FACTORY_RELEASE_AUTO is true"),
            "one cancelling another": (LIVE.replace("cancel-in-progress: false", "cancel-in-progress: true"),
                                       "never cancels one in progress"),
            "an input more": (LIVE.replace("      to:\n", "      force:\n        required: false\n        type: string\n"
                                                         "      to:\n"), "runs on workflow_dispatch, with the inputs"),
            "a version required": (LIVE.replace("      version:\n        required: false\n",
                                                "      version:\n        required: true\n"),
                                   "runs on workflow_dispatch, with the inputs"),
            "a command more": (LIVE.replace("          - rollback\n", "          - rollback\n          - promote\n"),
                               "runs on workflow_dispatch, with the inputs"),
            "a command more past a blank line": (LIVE.replace("          - rollback\n",
                                                              "          - rollback\n\n          - promote\n"),
                                                 "runs on workflow_dispatch, with the inputs"),
            "a command more past a comment": (LIVE.replace("          - rollback\n",
                                                           "          - rollback\n          # more\n          - promote\n"),
                                              "runs on workflow_dispatch, with the inputs"),
            "a machine of its own": (LIVE.replace("runs-on: ubuntu-24.04", "runs-on: linux-1"),
                                     "runs on GitHub's own runner"),
            "a longer run": (LIVE.replace("timeout-minutes: 15", "timeout-minutes: 120"), "runs on GitHub's own runner"),
            "another schedule": (LIVE.replace('"41 6 * * 1-5"', '"41 * * * *"'), "runs on workflow_dispatch, with the inputs"),
            "another name": (LIVE.replace("name: sf-release", "name: factory"), "it holds name: sf-release"),
            "a step with a key more": (LIVE.replace("      - run: python3 -m release.move\n",
                                                    "      - run: python3 -m release.move\n        shell: bash\n"),
                                       "its step step has exactly"),
            "the mint named otherwise": (LIVE.replace("      - id: mint\n", "      - id: token\n"),
                                         "its mint step has exactly"),
        }
        for why, (text, words) in sorted(cases.items()):
            with self.subTest(why=why):
                self.assertNotEqual(text, LIVE, why)
                self.assertTrue(caught(check_workflows.release_problems(text), words),
                                (why, check_workflows.release_problems(text)))

    def test_only_release_yml_names_the_release_jobs_environment_key_token_or_step(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            for rel in (".github/workflows", "examples/workflows", "docs/standards", "config"):
                (root / rel).mkdir(parents=True)
            for rel in ("examples/workflows/verify.yml", ".github/workflows/verify.yml", "docs/standards/workflows.md",
                        "config/defaults.json", ".github/workflows/release.yml"):
                (root / rel).write_text((ROOT / rel).read_text())
            planted = (ROOT / ".github" / "workflows" / "verify.yml").read_text().replace(
                "      - run: make verify\n", "      - run: make verify\n        env:\n"
                "          RELEASE_TOKEN: ${{ secrets.X }}\n", 1)
            (root / ".github" / "workflows" / "verify.yml").write_text(planted)
            found = [p for p in check_workflows.run(root) if "release.yml's alone" in p]
            self.assertEqual(len(found), 1, check_workflows.run(root))


class Version(unittest.TestCase):
    def test_a_cut_asked_with_no_version_is_of_the_next_patch_or_the_majors_first(self):
        refs = {"factory/v0.1.0": "a" * 40, "factory/v0.2.3": "b" * 40, "factory/v1.0.0": "c" * 40,
                "factory/v0-next": "b" * 40}
        self.assertEqual(cut.next_version("factory/v1-next", refs), "factory/v1.0.1")
        # A later major's Release exists: no cut of v0 is newer than it, so none is named.
        self.assertIsNone(cut.next_version("factory/v0-next", refs))
        refs.pop("factory/v1.0.0")
        self.assertEqual(cut.next_version("factory/v0-next", refs), "factory/v0.2.4")
        self.assertEqual(cut.next_version("factory/v0-next", {}), "factory/v0.1.0")
        self.assertEqual(cut.next_version("factory/v2-next", refs), "factory/v2.1.0")
        for name in ("factory/v0.2.3", "main", None):
            with self.subTest(name=name):
                self.assertIsNone(cut.next_version(name, refs))


if __name__ == "__main__":
    unittest.main()
