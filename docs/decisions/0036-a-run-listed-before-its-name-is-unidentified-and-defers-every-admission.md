# 0036. A Run listed before its name is unidentified, and defers every admission

Status: accepted. Taken as a working ruling on 2026-10-18, which the Maintainer may overturn in review, for
"Design: a Run is identified before its run-name is listed (P-17 failed)" (issue 161).

## Decision

Which run records count is settled without the name (§3.10): a run of the Factory's own workflow file, on the
default branch, started by a schedule or a dispatch, in the Factory repo. Which item a counted Run is on, and its
Intent, Role and content, come from its run-name alone. P-17 found that for up to 3.7 s after a dispatch the list
shows a run under the workflow's name, and nothing else listed in that window says whose it is.

1. A counted run record whose name is not yet a Factory run-name is an unidentified Run. The records port reports it
   apart from the Runs it can name, with its GitHub run id, whether or not it has completed. A completed record whose
   name cannot yet be tied to an item is unidentified too: read as no one's, it would fall out of its item's attempts
   and its Run ceiling, which count only the Runs tied to the item, and a later pass could admit again past them. The
   run-name is fixed at the dispatch, so GitHub lists a completed run's name too, within P-17's window, and the record
   is then counted. Only a record started by a `workflow_dispatch` of a Role's workflow, with an item in its input, can
   be unidentified, and only while its name is not yet listed. A run started by a schedule, a successor pass
   dispatched with no item, and the pass's own run are the poller's, not a Run on an item: they never take a
   run-name, and are never unidentified. Otherwise every pass would list its own run, and every admission would defer
   for ever.
2. An unidentified Run defers every admission in the pass's scope. It reaches the Kernel as a context fact,
   `unidentified_runs`, a list of run ids beside `paused` and `active_runs`. If it is not an empty list, or is not a
   list at all, every Run the pass would admit defers with the reason `run_unidentified`, on a pull request and on an
   issue, and so does an approval, which is a Run. It is asked where capacity and concurrency are, after the brakes
   and before admission: every Hold still shows, and an act that stops work, an enqueue and an issue's `accept` go
   ahead. `run_unidentified` is one of the deferrals of the whole scope: one cause, reported once, and never stale.
3. The port waits out the window, once. When a pass's list holds an unidentified Run, the port reads the list again
   5 s later and reports only what is still unidentified. A Run's own re-checks, at its start (I-38) and in `apply`
   (I-21), each read the list once more before asking the Kernel, and a Run that still sees an unidentified Run ends
   `superseded` before any model spend. A pass deferred by `run_unidentified` is not "due sooner than the next tick"
   (§7.3): the next pass comes at the next tick or nudge.
4. The port keeps no HTTP cache, and reads with the standard library, which keeps none. It sends
   `Cache-Control: no-cache` on every read of runs, and may send `If-None-Match`. It keeps each response's `date` and
   `age` in the pass record; a non-zero `age` is a stale read, counted in P-8's report. Neither header reaches the
   Kernel.

Invariant I-46 states the rule. §3.10, §6's row for P-17 and §7.3 say so. I-21 and I-38 keep their words.

## Why

The name is the only listed field that ties a Run to its item, so an unidentified Run may be the Run in flight on any
item. Admitting while one is listed acts on a fact that cannot be read, which the Kernel never does (I-13): two Runs
dispatched seconds apart could each start inside the other's window, see no other Run, and both run their Engine.
I-38 and I-21 stop a duplicate's Effects, not always its model spend. Matching on what the dispatch sets, the branch,
the event and the time, is not taken: every Factory Run shares them, and telling which dispatch made which run needs
a memory of what was dispatched, kept between passes, which decision 0002 forbids. The cost of deferring is small: the
window is under 4 s, and the port's second read turns almost every such pass into a normal one. A record still
unnamed after it is not the normal lag, so a chain of passes waiting on it would feed itself without bound (W-7).
A completed run still unnamed is deferred on in the same way, not dropped: dropped, it would leave its item's counts
short, and a later pass could admit past them (§3.10). Its name is fixed at the dispatch, so the wait for it is the same
window, not the 90 days its record is kept. A read up to 60 s old, which the list's `cache-control` allows, is as long as P-22's
whole bound, so nothing on the Factory's side may cache it.

The trade-off: an unidentified Run is missing from the Runs the Kernel reads, so in the window an item whose own Run is
in flight but not yet named reads as having none. An enqueue, or an issue's `accept`, can then go ahead beside that
Run, where the Kernel otherwise decides no act while a Run of the item waits. Neither admits a Run nor spends a model,
and the Run in flight asks the Kernel again at its start and in `apply` (I-38, I-21): if the act changed what it was
admitted for, it ends superseded.

## Boundaries

| Boundary | Check |
|---|---|
| A pull request awaiting review with one unidentified Run defers with `run_unidentified` and attention `review`; with none it admits the review | `tests/test_decide.py::test_an_unidentified_run_defers_a_run_on_a_pull_request` |
| A list of unidentified Runs that is missing, null or not a list defers a Run, and an approval | `tests/test_decide.py::test_a_list_of_unidentified_runs_that_cannot_be_read_defers`, `tests/test_decide.py::test_a_list_of_unidentified_runs_that_cannot_be_read_defers_an_approval` |
| At the Run ceiling the Hold shows, and under a Pause the Pause defers, before an unidentified Run | `tests/test_decide.py::test_an_unidentified_run_is_asked_after_the_brakes` |
| A converged item due an approval defers with `run_unidentified`; spent approvals still hold it | `tests/test_decide.py::test_an_unidentified_run_defers_an_approval` |
| An enqueue and a dequeue go ahead while a Run is unidentified | `tests/test_decide.py::test_an_unidentified_run_stops_no_enqueue_and_no_dequeue` |
| An issue in triage wanting an investigation defers with `run_unidentified`, and on a list that cannot be read; the Pause and spent attempts are read first | `tests/test_issue.py::test_an_unidentified_run_defers_an_issues_run` |
| An issue's `accept`, and a Hold placed for unmerged closes past their bound, go ahead while a Run is unidentified | `tests/test_issue.py::test_an_unidentified_run_stops_no_acceptance_and_no_hold` |
| A deferral by an unidentified Run is never stale, on a pull request or an issue | `tests/test_decide.py::test_a_deferral_of_the_whole_scope_is_never_stale`, `tests/test_issue.py::test_a_person_a_run_nobody_or_a_deferral_of_the_whole_scope_is_never_stale` |
| In the simulator no pass admits a Run or issues an approval while a Run is listed unnamed, and the seeds reach that window | `tests/test_simulator.py::test_a_run_listed_unnamed_admits_nothing`, `tests/test_simulator.py::test_an_approval_listed_unnamed_is_not_issued_again`, `tests/test_simulator.py::test_the_seeds_list_a_new_run_unnamed` |
| The records port reports as unidentified only a counted run record started by a `workflow_dispatch` of a Role's workflow with an item in its input, whose name is not yet a Factory run-name, whether or not it has completed, so that a completed one is never dropped from its item's counts; never a scheduled run, a pass dispatched with no item, or the pass's own run. It reads the list once more 5 s later, and keeps no cached read | `tests/test_adapters.py::test_a_run_listed_under_its_workflows_name_is_unidentified_after_one_more_read`, `tests/test_adapters.py::test_a_run_named_by_the_second_read_is_a_record`, `tests/test_adapters.py::test_only_a_dispatch_of_a_role_workflow_from_the_default_branch_in_this_repo_counts`; that every Role dispatch carries an item, and that the pass's own run is no Role's, is the workflows' to hold, waiting on `.github/workflows/run.yml` |
| A Run's start and its `apply` read the list once more before asking the Kernel, dropping the Run's own `GITHUB_RUN_ID` from it, and end superseded while a Run is unidentified | waiting on `harness/` |
| A pass deferred by an unidentified Run starts no successor | `tests/test_controller.py::test_a_successor_starts_only_for_an_item_due_at_the_end` |
