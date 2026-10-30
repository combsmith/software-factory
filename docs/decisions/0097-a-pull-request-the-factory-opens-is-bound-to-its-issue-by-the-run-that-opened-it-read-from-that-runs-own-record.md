# 0097. A pull request the Factory opens is bound to its issue by the Run that opened it, read from that Run's own record

Status: accepted. The Factory Builder's ruling of 2026-10-30 on "Acceptance: a pull request the Factory opens is bound to its issue by the Run that opened it" (issue 342): option (a), the opening Run's own `applied/1` holds the binding, as a Lens's holds its Findings. It holds what decision 0068's row "The Run record" left waiting, and the Run-record half of decision 0047's binding.

## Decision

| What | Decided | Because |
|---|---|---|
| The record | The opening Run's own `applied/1` names the pull request it opened, in an `open_pull_request` Effect keyed by the pull request's number as read back. `applied/1`'s Effect types gain it, beside `approve`, as one no Result asks for yet | A Run record names the issue it served, its run-name's item, and never the pull request it made; its own record of what it wrote joins the two, as the Lenses' records join their threads (decision 0069) |
| The reader | `adapters/applied.py`'s `opened` reads, once a pass, each completed Run of the Role the configuration names for `open-pull-request`, of that Intent, on an issue of the home repo: the pull request each one's landed `open_pull_request` Effect names, by number, with the issue it served. An issue whose opening Run cannot be read, is named by more than one GitHub run, names more than one pull request, or names a number that is none, is unreadable; the list is whole only when the run list was read whole. With no Role named, nothing is read | What cannot be read is never read as none (I-13) |
| The binding | A pull request the opener's App authored, on a branch of the Factory's shape, is bound to the issue its branch names when the Runs that name it agree: one that names it for another issue, two that name it, or an unreadable opening Run of the branch's issue, leaves it not read whole, and the Kernel defers. Where no Run names it, the branch alone binds it, as decision 0068 has it. A person's pull request keeps its closing references' reading | Where both are present they must agree, as the issue asks; an opening Run that pushed to another issue's branch is caught by its own record |
| Where it is read | Wherever a snapshot is: the pass, the Run's read step and `apply`'s read again each read the opening Runs and hand them to the snapshot, which takes them as a required argument, so no caller can leave them out. Handed none, the opener's pull request is never bound | The binding is read wherever the ask is |
| The writer | `apply`'s open Effect, which writes the record, lands in slice 2 with the push Effect, as decision 0070's refusal waits on push. No Role opens pull requests in slice 1, so none is bound yet, and nothing is read | The Factory Builder's ruling: build the record, the reader and the binding now |
| The lookup's grant | The bound issue's lookup under the Controller App's grant is a trial the release builder runs, before a Role opens pull requests on a private repo (decision 0068) | It is a trial, not this change |

## Why

Decision 0068 bound a pull request the Factory opens by its branch, and named its own limit: anyone who may write the repo can rename a head branch, so an opening Run that names another issue's branch answers to that issue. The Run's own record of the pull request it opened closes that gap without reading the body.

## Boundaries

| Boundary | Check |
|---|---|
| A Run that names the pull request binds it where its issue and the branch's agree; one of another issue, two, an unreadable opening Run of the branch's issue, or a list not read whole, leave it not whole; none, the branch alone binds it; a person's pull request is read by its closing references | `tests/test_adapters.py::test_a_pull_request_the_factory_opens_is_bound_by_its_opening_run_as_well` |
| An opening Run's record names the pull request it opened; one that opened none, or whose open Effect did not land, names none; two named, a number that is none, a record that cannot be read, or a Run named twice, is unreadable; another Role's, Intent's, an unfinished one, or one on a pull request or in another repo is not read | `tests/test_adapters.py::test_what_an_opening_run_recorded_names_the_pull_request_it_opened` |
| The opening Runs are read for the Role the configuration names, none in slice 1, and handed to the acceptance read as given | `tests/test_adapters.py::test_the_role_that_opens_pull_requests_is_the_configurations`, `tests/test_adapters.py::test_a_snapshot_reads_the_ask_of_the_openers_pull_request_by_its_branch` |
| applied/1 records open_pull_request beside effect/1's types and approve | `tests/test_approve.py::test_an_approval_is_an_effect_apply_records_and_no_result_may_ask_for` |
| `apply` writes the record when a Role opens a pull request | waiting on `harness/push.py` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
