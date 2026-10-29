# 0092. An external Lens's approval never counts, and no Role resolves another reviewer's thread

Status: accepted. The Maintainer adopted, in full, "CodeRabbit's approval follows from its threads being resolved, so it is never counted as a review, and no Role resolves another reviewer's thread" (issue 366) on 2026-10-29, after P-25 failed with CodeRabbit's approve-when-resolved feature on and passed with it off. The Factory Builder gave the rulings on what holds each half.

## Decision

| What | Decided | Because |
|---|---|---|
| (a) In the Kernel | An approval counts only as the machine user's (`standing_approval`) or as a person's judgement (`judged_by_a_person`). An external Lens's or any other App's approval, with write access and of this content, neither stands, nor judges a change to a model Lens's input, nor answers a person's request for changes. The Kernel already read it so; a boundary test now holds it | CodeRabbit approves once its last thread is resolved, by whoever resolves it, an App among them (trials/P-25.json, its first run on the canary) |
| (a) Toward the `main` ruleset | `main` counts no approval today. When it counts one, as "The ruleset switch: main requires the machine user's approval of the most recent commit, and slice 1's event is recorded" (issue 198) will make it, the approval must be a code owner's, of the last push. `.github/CODEOWNERS` must also name, on every line with a catch-all among them, only `@combsmith/org-leads`, the team through which the machine user is a code owner (issue 198's ruling 2). `tools/check_rulesets.py` holds this | An App is never a code owner, so no external Lens can meet such a ruleset. A blanket refusal of a counting ruleset would block that switch |
| (b) No Role resolves | No Role resolves any thread, since decision 0086: `resolve_thread` is no Effect a Role may name or `apply` may write, and the effects port sends none. A Lens's thread, or an external reviewer's that its category's owner accepted, is resolved only by the Kernel's act, which the queue App carries out, and only on an `accepted` ruling: a `rejected` one, or none, resolves nothing (decision 0086's rows "When a Lens's thread is closed" and "The act") | A Role that resolved another reviewer's thread could manufacture that reviewer's approval. The Kernel's act may resolve an external reviewer's accepted thread: `main` holds a merge on any thread left open |
| The reviewer's configuration | Each repo the Factory serves holds CodeRabbit's configuration with `reviews.auto_approvals.enabled: false` (design section 4.2), as this repo's `.coderabbit.yaml` does. The readiness check refuses a repo without it, and a ruleset that would count an external approval. That check is not built: "Readiness check: each Consumer repo against its entry" (issue 401) | P-25 passed with the feature off, in its second run on the canary, whose fixture the trials lane brings. A configuration can be changed by anyone who can push, so (a) stays as the backstop |

## Why

P-25 showed that whoever resolves CodeRabbit's last thread turns its request for changes into an approval. Nothing on `main` counts that approval, and nothing may: not the Kernel, not the ruleset, not a Consumer's. No Role may resolve another reviewer's thread to make one.

## Boundaries

| Boundary | Check |
|---|---|
| An external Lens's or App's approval, with write access and of this content, neither stands, nor judges a change to a model Lens's input, nor answers a person's request | `tests/test_decide.py::test_an_external_lenss_approval_never_counts` |
| A `main` ruleset that counts an approval asks for a code owner's, of the last push | `tests/test_tools.py::test_an_approval_counts_only_a_code_owners_of_the_last_push` |
| Then `.github/CODEOWNERS` names only the machine user's team on every line, a catch-all among them; a ruleset that counts none reads no code owners | `tests/test_tools.py::test_the_code_owners_are_the_machine_users_team_on_every_path` |
| No Result asks a thread resolved, no Role may name it, and no Role write of it is sent | `tests/test_apply.py::test_the_owners_decisions_are_its_rulings_and_no_result_resolves_a_thread`, `tests/test_tools.py::test_each_effect_type_is_requested_by_its_own_list`, `tests/test_apply.py::test_no_role_write_resolves_a_thread` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
