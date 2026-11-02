# 0108. The machine user holds write on every repo through an org role on the code owners' team, and is a code owner of every path

Status: accepted. The Maintainer's answers of 2026-10-31, as the Factory Builder relayed them, on "Redesign the machine user's permissions: approve everywhere, own no rules" (issue 89). It corrects the eight-repo reading of his answer of 2026-10-21, given on "The ruleset switch: main requires the machine user's approval of the most recent commit, and slice 1's event is recorded" (issue 198). The Factory Builder ran the change on his word, with his approval by hand, on 2026-11-01.

## Decision

| What | Decided | Because |
|---|---|---|
| The role | Write, on every repo, "via org level settings, not repo" (the Maintainer). The team `org-leads` holds the org role `all_repo_write` and no longer `all_repo_maintain`. Approving needs write; maintain adds settings powers it never uses (FR-60) | A read of 2026-10-31 found the bot's maintain comes from that org role, on all 15 active repos. One `PUT` a repo on eight repos, as the ruling on the switch first had it, would have left the org role standing, and maintain with it |
| The team's repo grants | Removed, on the 7 repos that have one, so the org role alone governs. **This is the Factory Builder's reading of his words, not his words**: he did not say it in those terms | He does not want it managed repo by repo. A grant left at maintain would keep maintain there |
| The order | Write on, then maintain off, then the grants off, each read back, then a canary approval read | A team must itself have write to count as a code owner. A team's org role counts: this repo and the canary have no grant of their own, `codeowners/errors` is empty, and the bot's approval counted there (`trials/P-7.json`). It counts at write: with the change made, the bot's approval on the canary's "The machine user at write: does its approval still count?" (pull request 80) read `APPROVED` and `CLEAN` |
| The teams | `org-leads`, which makes it a code owner, and `organization-members`, as every member is. Nothing is granted to it directly | As the ruling on the switch had it |
| The paths | Every path, through `* @combsmith/org-leads`, unchanged. `.github/CODEOWNERS` stays the org's word for word, and the org's `repo-template` does not change | The Maintainer's answer. Rule paths to him alone would refuse the bot's approval (`trials/P-24.json`) on changes he authors, which GitHub refuses him too, so each would need a bypass; and the org's standard forbids a person as an owner. What stops the Factory approving a change to its own rules is `apply` (decisions 0004, 0005), whose refusal decision 0004 says is still to be built, and, while he authors every change, his authorship, which alone holds today |
| The other repos | The role changes on them, and nothing else: no file, ruleset or template. Their rulesets and code owners stay | "Write everywhere". Whether the bot's other work there needs more than write is unproven: three days of its activity fit write |
| The data | `config/machine-user.json`, `machine-user/1`, which holds the role as `write`, never `maintain` or `admin`. `tools/machine_user_drift.sh` compares it with GitHub by hand, as `tools/rulesets_drift.sh` does: the org role's name and every team that holds it, who is in the code owners' team, that the bot is a plain member of each of its teams, each recorded repo's role, that each is still active, and how many active repos go unrecorded. The canary and the proof of concept's repo are counted and not named: `tools/check_trials.py` and `tools/check_repo.py` keep their names out of this file. The org role holds there too | So that a change of role, team or code owner is visible |
| Its limits | A direct grant on a repo the file does not name, and a team the bot joins that raises no role on a recorded repo, read as no drift | The script reads the recorded repos and the named teams, and counts the rest |
| The second writer | Joaolfelicio stays as is: write, through `organization-members` | The Maintainer's answer. With code-owner review on, their approval merges nothing |

## Why

The story asked for the machine user's least privilege, reconciled with section 5.1. Section 5.1 already said code ownership does not keep the Factory from approving a change to its own rules, so the reconciling is done: only the role was left, and the read found it held at a different level from what the rulings assumed.

The org-level change is the Maintainer's. All 15 active repos read write for the bot and push for the team after it, and `config/machine-user.json` holds that read: `tools/machine_user_drift.sh` answered no drift.

## Boundaries

| Boundary | Check |
|---|---|
| The machine user holds write, never maintain or admin, on every repo recorded, and the team has no grant of its own | `examples/invalid/machine-user.maintain-somewhere.json`, `examples/invalid/machine-user.a-grant-repo-by-repo.json` |
| It is a member of the code owners' team | `examples/invalid/machine-user.not-in-the-code-owners-team.json` |
| The team may not be at maintain on a repo, nor the org role be maintain, nor another repo go unnamed | `examples/invalid/machine-user.a-team-at-maintain-on-a-repo.json`, `examples/invalid/machine-user.an-org-role-of-maintain.json`, `examples/invalid/machine-user.another-repo-left-out.json`, `tests/test_tools.py::test_what_the_machine_user_may_never_hold_has_a_counter_example` |
| The record is of the approver the configuration names, by login and id, the team is the one the code owners file names, and that team has write on this repo | `tests/test_tools.py::test_the_machine_user_is_the_approver_and_a_code_owner_with_write_here` |
| What the file records is compared with what GitHub answers, by hand, and no answer is kept unredacted or inside the repo | `tests/test_tools.py::test_the_machine_users_live_role_is_compared_whole`, `tests/test_tools.py::test_the_machine_users_script_keeps_each_answer_redacted_and_compares_them`, `tests/test_tools.py::test_the_machine_users_script_refuses_a_scratch_directory_inside_the_repo` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
