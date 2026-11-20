# 0240. The checks that hold a trust boundary are protected paths

Status: accepted. The Solution Architect's ruling of 2026-11-20 on "A workflow on push beside a secret is not held to the base, and the check that holds workflows is no protected path" (issue 907), relayed by the Factory Builder.

## Decision

| What | Decided | Because |
|---|---|---|
| Which checks | `tools/check_workflows.py`, `tools/commits_are_the_maintainers.py`, `tools/check_writes.py` and `tools/check_repo.py` join `config/hooks.json`'s `protected` list, each at its own path | Each holds a boundary a Role's push could otherwise move: what a workflow beside a secret may read of a head, that every commit a pull request carries names the Maintainer, that only the callers it lists reach a GitHub write, and that nothing is installed or fetched and no secret written down (the Factory Builder's ruling, adding the fourth on Astra's and Kimi's reads). A push that edits one can blind it to a later change, though the edit exposes nothing by itself |
| What follows | `apply` refuses a Role's push that changes, renames or copies one (decision 0188), a session is asked before an edit, and a change to one is read by every model Lens. Each stays an input of `verify` | The checks are a person's to change, as the workflows and the protected list already are |
| What stays | The other checks under `tools/` stay `verify`'s inputs, pushed and read by every Lens, `tools/check_authority.py`, `tools/check_lifecycle.py` and `tools/check_purity.py` among them | Those are edited often by ordinary lane work, and a prompt on each edit would cost more than it guards; each is still read by `verify` and every model Lens's review |
| When | After decision 0225's pull request merges, so that it is not asked again mid-flight | A protected edit asks for the Maintainer's approval |

## Why

Decision 0225's limit row named `tools/check_workflows.py` as no protected path, read by `verify` and every model Lens's review and not refused; this changes that part of it alone. 0225 held a workflow on `pull_request` beside a secret to protected settings or the base, and named its own check as no protected path, a limit. The security read of 0225's pull request found that the check could be edited by a Role's push and so blinded; the Solution Architect ruled that the checks that hold a trust boundary are a person's.

## Boundaries

| Boundary | Check |
|---|---|
| `tools/check_workflows.py`, `tools/commits_are_the_maintainers.py`, `tools/check_writes.py` and `tools/check_repo.py` are on the repo's own protected list, and a Role's push of any of them is refused; no other check is | `tests/test_apply.py::test_the_checks_that_hold_a_trust_boundary_are_on_the_repos_own_list`, `tests/test_hooks.py::test_every_protected_path_asks_for_every_edit_tool_in_every_tree`, `tests/test_decide.py::test_a_lens_input_counts_like_a_protected_path`, `config/hooks.json`, mutant: "the check that holds the workflows is pushed by a Role", mutant: "the check of whose commits a pull request carries is pushed by a Role", mutant: "the check of who reaches a GitHub write is pushed by a Role", mutant: "the check that nothing is fetched and no secret written is pushed by a Role", mutant: "every check under tools/ is protected" |
