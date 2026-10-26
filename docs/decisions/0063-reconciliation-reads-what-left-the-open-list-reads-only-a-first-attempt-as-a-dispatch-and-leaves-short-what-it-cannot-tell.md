# 0063. Reconciliation reads what left the open list, reads a dispatch by its run's making, and leaves short what it cannot tell

Status: accepted. The follow-ups of decision 0061, from Codex's reads of
"Controller: reconciliation, every write by a Factory identity matched to a recorded Effect (I-33)" (pull request 326):
"Reconciliation: three reads left whole that should be short" (issue 328) and
"Reconciliation: five more, the applied/1 download bound first" (issue 329), each title as it stands less the pull request it names.
It extends decision 0058, on who starts a Run, and decision 0061, on reconciliation, and leaves both as they are.

## Decision

| What | Decided | Because |
|---|---|---|
| A Run's `applied/1` | Its archive is held to an outcome's bound and downloaded under `STORED`; only the file in it may be larger, 256 KiB | `PASSED` is a pass record's alone (`adapters/AGENTS.md`), and JSON zipped fits |
| A dismissed review | Read as what it was before it was dismissed, from the timeline's dismissal, paired by a positive id and a state that is a word: a Role's review as a review, an approval as an approval. One whose state before cannot be read leaves what was seen short | A Role's recorded review, dismissed, is still the write its Effect recorded; reading every dismissal as an approval alarmed on it |
| An item that left the open list | A pull request the pass before served and that is no longer open, merged or closed between the passes, has its timeline, comments, reviews, threads and the check runs on its head read by the seen port (`seen.LEFT`): its close by a Factory identity alarms, and its merge is read for an Override. One whose timeline names no close or merge in the window is not one that left, and is short | No snapshot reads it, so its last writes were never read |
| A dispatch and a re-run | The run record keeps when its run was made, `dispatched_at`, which a re-run keeps, and on a re-run whether the dispatcher's own account re-ran it, `rerun_by_dispatcher`, from GitHub's `triggering_actor`. A dispatch is read by when its run was made; a re-run by the pass job's token is a write no Effect records, and alarms. A run whose attempt, or a re-run whose re-runner, cannot be read is null there, and reconciliation is short | A re-run runs nothing (decision 0058). A person's re-run of an old Run read as a new dispatch alarmed falsely; reading only first attempts let the token hide its own dispatch behind its own re-run, since GitHub lists a run's latest attempt alone |
| The activity's period | GitHub's shortest period that covers the window an hour over, at the port's clock: a day, a week, four weeks, 89 days or 364 days for a month, a quarter or a year. GitHub's own `Date` decides what it covered, where it gives one. A window older than a year, or a clock before the window, is read for the year, and short | A fixed week left writes before it unread while the read said whole; the shortest lengths and the hour are for clocks apart |
| What cannot be told | An event no Factory write makes, by an account that cannot be read; an event of no name; a review of no state GitHub gives; a thread's resolver of no positive id; and two configured identities of one account, neither of which is then attributed, each leave reconciliation short | Each may be a Factory identity's write that cannot be told from another's |

## Why

Codex read the pull request after its last fix round, taken under the token pause. Its findings were filed, not fixed there,
since none makes the merged code act: each is a write missed, a read left whole where it should be short, or a false
alert. Nothing calls the seen port or `applied()` live until the collector, the poller workflow, gathers the pass's
reads, so each is fixed before it reads.

## Boundaries

| Boundary | Check |
|---|---|
| A Run's `applied/1` is never downloaded under a pass record's bound | `tests/test_adapters.py::test_a_runs_applied_record_is_read_whole_or_not_at_all` |
| A dismissed review is read as what it was before; one whose state before is not read is short | `tests/test_reconcile.py::test_each_identitys_writes_are_read_by_its_account_never_its_login` |
| An item that left the open list is read whole by the seen port, or short | `tests/test_reconcile.py::test_an_item_that_left_the_open_list_has_its_timeline_read_here` |
| The collector reads, with `seen.LEFT`, each item the pass before served that is no longer open | waiting on `.github/workflows/poller.yml` |
| The run record keeps when its run was made, and whether its dispatcher re-ran it | `tests/test_adapters.py::test_a_run_named_by_the_second_read_is_a_record` |
| A dispatch is read by when its run was made, and a re-run by the pass job's token alarms | `tests/test_reconcile.py::test_a_dispatch_is_matched_by_its_run_to_the_pass_that_sent_it` |
| The activity is asked for a period that covers the window | `tests/test_reconcile.py::test_the_activity_is_asked_for_a_period_that_covers_the_window` |
| What cannot be told leaves reconciliation short | `tests/test_reconcile.py::test_a_list_that_cannot_be_read_whole_leaves_what_was_seen_short` |
| Two identities of one account are not known | `tests/test_reconcile.py::test_each_identity_is_told_by_its_account_from_the_configuration` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
