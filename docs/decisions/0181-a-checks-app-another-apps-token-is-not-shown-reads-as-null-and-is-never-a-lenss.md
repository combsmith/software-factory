# 0181. A check's App another App's token is not shown reads as null, and is never a Lens's

Status: accepted. The Factory Builder's ruling of 2026-11-10. Slice 1's second dry run, at v0.1.2, stopped in the reader as `snapshot_checks_unreadable`. The Builder ruled that this one fix covers both readings of that stop, a null App and a refused one, with no probe first: v0.1.3's run is the probe.

## Decision

| What | Decided | Because |
|---|---|---|
| A null App | A check run whose suite's App GitHub gives as null is read with `app_id` null | The Factory's Apps are private, and the head's rollup holds the Controller's own status. Another App's token is not shown a private App, and the reader's read of the rollup was refused where the Controller's own read was whole |
| A refused App | So is one GitHub refuses at exactly that check run's `checkSuite.app`, with `FORBIDDEN`, its App given null | GitHub's GraphQL refuses a field a token may not read, and nulls that field alone |
| Anything else | Any other error type, an error at any other place, a refusal outside the page, or a refused App the rollup gives anyway, refuses the read, as every error did before | Only the one field is known not to be shown. A read that went wrong anywhere else is still unread (I-13) |
| `facts/1` | `app_id` is an integer or null | A fact the port could not be shown is told as such, never invented |
| The Kernel | Unchanged. A null App is no Lens's App: under a required Lens's check name it is `<lens>:from_app:unreadable`, a deferral; on any other check, the Controller's status or a Role App's own, it changes no Decision | Nothing becomes admittable that was not before |
| A result's check | Still refused where its App is null | No result is taken as reported by an App that cannot be named |
| Reconciliation | A check run whose App is null, or has no id that can be read, leaves what was seen short | It could be any App's, a Factory one's among them: short, never silent (0061, 0063) |

## Why

The reader reads the same rollup the pass reads, through its own App. The pass sees the Controller's App on its own status, and the reader cannot. Once the review Role posts a check of its own, the Controller's pass would be in the same place. A refusal of the one field no token can be shown cannot be a fact the Kernel needs: no Lens is read from it, and each required Lens is pinned to a public App.

## Boundaries

| Boundary | Check |
|---|---|
| A null or refused App reads as null; another error, place or page, or a refused App the rollup gives, refuses the read | `tests/test_adapters.py::test_a_check_whose_app_github_does_not_show_reads_as_no_app`, `adapters/checks.py`; mutant: "a check whose App GitHub gives null is refused"; mutant: "any error is taken for a refused App"; mutant: "a refusal at any place in a check run is taken for its App's"; mutant: "a refusal in another commit's rollup is taken for an App's"; mutant: "a refused App the rollup gives anyway is read"; mutant: "a refused App with no rollup is read"; mutant: "a refusal before the page's first check is read"; mutant: "a refusal at a place that holds no object is read"; mutant: "a refused App of a status context is read"; mutant: "a place's parts are matched by value alone"; mutant: "a check run's place may be any whole number, false among them" |
| A check run whose App is not shown leaves reconciliation short, never silent (decisions 0061, 0063), a left item's read over REST as well | `tests/test_reconcile.py::test_a_list_that_cannot_be_read_whole_leaves_what_was_seen_short`, `tests/test_reconcile.py::test_an_item_that_left_the_open_list_has_its_timeline_read_here`, `adapters/seen.py`; mutant: "a check run whose App is not shown leaves what was seen whole"; mutant: "a check run whose App id cannot be read leaves what was seen whole" |
| A result's check with no App is refused | `tests/test_adapters.py::test_a_results_check_is_read_as_any_check_and_a_created_one_is_foreign_to_its_reporter`, `adapters/acceptance.py`; mutant: "a result is reported by an App no one can name" |
| A null App on a check no Lens names changes no Decision | `tests/test_decide.py::test_a_check_no_lens_names_whose_app_is_not_shown_changes_no_decision`, `kernel/derive.py`; mutant: "a check no Lens names is foreign where its App is not shown" |
| A null App under a required Lens's name defers | `tests/test_decide.py::test_a_check_from_another_app_is_unreadable_for_its_lens`, `kernel/derive.py`; mutant: "a null App is taken for a Lens's" |
