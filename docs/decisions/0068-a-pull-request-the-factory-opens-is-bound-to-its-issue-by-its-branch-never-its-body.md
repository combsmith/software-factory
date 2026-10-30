# 0068. A pull request the Factory opens is bound to its issue by its branch, never its body

Status: accepted. Taken as working rulings on 2026-10-26, which the Maintainer may overturn in review, for "Acceptance: a pull request is bound to the issue it serves by its Run or branch, not by its author's closing link" (issue 295). It closes the known limit of `docs/decisions/0047-an-issue-asks-for-an-acceptance-contract-only-by-an-intent-that-asks-or-a-persons-label.md`, whose closing references a pull request's author writes, and gives the design's work branch, "named from the issue's number and the count of pull requests the Factory has ever opened for it" ("The hand-over"), its form. Decision 0047 is not edited; its Boundaries row now names the test.

## Decision

| What | Decided | Because |
|---|---|---|
| The branch | `factory-work/issue-<N>-<k>`, `kernel/terms.py`'s `WORK_BRANCH`: N the issue, k the count of pull requests the Factory has opened for it, each a whole number from 1 with no leading zero, and nothing after k. It is matched whole, in the pull request's own repo | One spelling, read strictly, is one issue. Not under the prefix the Release and Channel tags use: a branch that shares a short name with a tag makes `git checkout` ambiguous |
| Whose pull request is bound | One whose author is the App of the Role `config/defaults.json` names for `open-pull-request`, that App read from `config/apps.json` by the Role's name and its account from `config/controller.json`'s `roles`, never a login in code (`adapters/facts.py`'s `opener_of`). No Role opens one in slice 1, so none is bound | The Factory's own App made the branch; a person's branch name is the person's to choose and binds nothing |
| What it is bound to | The issue its branch names. The ask is read from that issue, its labels and timeline as a closing issue's are read. Closing references that leave it out are no fault; closing references that name any other issue, or that cannot be read whole, make `complete.acceptance` false, and the Kernel defers, `facts_incomplete` | The body is the author's to write and the branch is the Factory's: a removed "Closes" removes no ask, and an added one cannot point the pull request at another issue |
| What is not whole | The opener's pull request on a branch of another shape or in another repo; and, where the Role is named but its App or account cannot be told (`acceptance.UNTOLD`), any pull request on a branch of the Factory's shape, since it cannot be told for a person's. A bound issue that is a pull request, or cannot be read, is refused | A binding that cannot be read is never read as none |
| A person's pull request | Keeps decision 0047's reading, by its closing references, on a branch of the Factory's shape or not | Which issue a person's change answers to is the person's to say |
| The grant | The bound issue's labels are read by `GET /repos/{repo}/issues/{n}`, which GitHub documents under `Issues: read` alone, a grant the Controller's App does not hold, though any token reads a public repo's. A refused read raises, the snapshot is not read and the Kernel defers. Before a Role opens pull requests on a private repo, a trial reads this lookup under the App's grant, "Acceptance: a pull request the Factory opens is bound to its issue by the Run that opened it" (issue 342) | The read fails closed; whether it needs a grant is GitHub's to show |
| The known limit | The branch is the one the opening Run names, and anyone who may write the repo can rename a head branch: until the Run that opened a pull request is read as well, an opening Run that names another issue's branch, and closes nothing, answers to that issue. Which branch an opening Run pushes to is the Harness's to hold to the issue it was admitted on | The branch binds by what the Factory's own App wrote, which the author's body never was; it is not yet held to the Run that wrote it |
| The Run record | Binding by the Run that opened a pull request waits on `open_pull_request` recording its Run: the opening Run's run-name names the issue, never the pull request it made, "Acceptance: a pull request the Factory opens is bound to its issue by the Run that opened it" (issue 342) | Nothing yet joins the two |

## Why

Decision 0047 read the ask from the issues a pull request closes, and its author writes those. A pull request whose
issue asks for a contract will be opened by the Factory's own Roles; its branch is theirs, made by the opening Run, and
is bound here before any Role opens one.

## Boundaries

| Boundary | Check |
|---|---|
| The opener's pull request is bound to the issue its branch names, and the ask is read from it whether its closing references name it or not | `tests/test_adapters.py::test_a_pull_request_the_factory_opens_is_bound_to_the_issue_its_branch_names` |
| Closing references that name another issue than the bound one, or are read short, are not whole | `tests/test_adapters.py::test_closing_references_that_name_another_issue_than_the_bound_one_are_not_whole` |
| A branch of another shape or another repo binds nothing, and the opener's pull request on one is not whole | `tests/test_adapters.py::test_a_branch_of_another_shape_binds_nothing_and_the_openers_pull_request_is_not_whole` |
| A person's pull request, and every one in slice 1, keeps its closing references; with the opener untold, one on a branch of the Factory's shape is not whole | `tests/test_adapters.py::test_a_pull_request_no_opener_opened_keeps_its_closing_references` |
| The opener is read from the configuration by its Role, and is none in slice 1 | `tests/test_controller.py::test_the_app_that_opens_pull_requests_is_read_from_the_configuration_by_its_role` |
| The Controller and the harness's reads again tell each snapshot the opener, and the snapshot tells the acceptance read | `tests/test_controller.py::test_each_snapshot_is_read_with_the_configured_accounts_and_kept`, `tests/test_steps.py::test_the_reader_writes_the_tasks_inputs`, `tests/test_steps.py::test_the_item_is_read_again`, `tests/test_adapters.py::test_a_snapshot_reads_the_ask_of_the_openers_pull_request_by_its_branch` |
| A pull request the Factory opens is bound by the Run that opened it, "Acceptance: a pull request the Factory opens is bound to its issue by the Run that opened it" (issue 342) | waiting on `adapters/binding.py` |
| A bound issue whose read is refused, or that is a pull request, is refused by the acceptance read, which raises as for any read it cannot answer | `tests/test_adapters.py::test_a_pull_request_the_factory_opens_is_bound_to_the_issue_its_branch_names` |
| The bound issue's lookup is read under the Controller App's grant before a Role opens pull requests on a private repo, "Acceptance: a pull request the Factory opens is bound to its issue by the Run that opened it" (issue 342) | waiting on `adapters/binding.py` |
| The grant the Decision's row "The grant" says the Controller's App does not hold, it has held since the grants of 2026-10-27 (record 0077), as `issues: write`; a token narrowed to `issues: read` reads the lookup, and GitHub names `issues=read` as what it accepts | `tools/check_apps.py`, `tests/test_adapters.py::test_the_bound_issues_lookup_is_read_under_the_controllers_grant` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
