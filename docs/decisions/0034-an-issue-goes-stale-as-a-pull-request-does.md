# 0034. An issue goes stale as a pull request does

Status: accepted. Taken as a working ruling for "Kernel: an issue goes stale as a pull request does" (issue 165) on
2026-10-18, which the Maintainer may overturn in review. It decides one sentence of decision 0031 otherwise: an
issue's stale times are applied now, and `kernel/issue.py` imports one name more than decision 0031 lists, `stale`.

## Decision

An issue's wait past its State's limit shows `stale`, as a pull request's does (§4.1, I-1). `decide` in
`kernel/issue.py` wraps `_decide`, as `kernel/decide.py` does. When the attention is one that may go stale, the reason
is no deferral of the whole scope, and the wait has run past its State's limit, while passes ran, the attention becomes
`stale`; the State, the reason, the outcome and any act or admission stay as they were. No reason code is new. On an
issue only a `ready` wait goes stale: `new` with acceptance due, `triage` and `ready` with a Run or an act due, a
deferral that is not the whole scope's, and `in_progress` with a linked draft. `needs_you`, `working` and `none` never
do, nor a Pause, the model provider's deferral or the org's concurrency. `kernel/issue.py` imports `stale` from
`kernel/derive.py`, the one test of a wait against its limit, and `kernel/decide.py` is not edited.

The wait counts from when the issue last moved, `moved_at`, read from the issue's own facts, and no earlier than
`passes_since`. An issue moves when its present life begins, its content changes, a person with write access acts or
comments, a person with write access or any App that `issues.label_apps` names adds or removes a control label, a Run
on it starts, or a linked pull request of the Factory's (`agent`) or of a person with write access (`maintainer`)
opens or closes. Nothing else moves it: not a Role's comment, whose Run is counted already, nor an App named nowhere,
nor a label the Kernel does not read, nor a pull request of any other class, an admitted outsider's or a dependency
bot's among them. A time that is no real moment, or is later than `now`, is passed over. A `now` that is no moment
gives no time, and a context that is no mapping says nothing of the passes.

The limits are read from `lifecycle/issue.json` alone, given with the configuration as its `lifecycle`, never from
`config/defaults.json`. A Lifecycle that is not a mapping whose `work_item` is `issue`, or whose limit for the State is
no finite number of minutes, missing, null, a string, a bool, NaN or infinite, reads the wait as past its limit. An end
the Lifecycle declares never goes stale. As the Lifecycle declares, an issue in `in_progress` goes stale after a day
with no movement, whoever opened its draft.

Each pull request in `linked`, in `issue-facts/1`, says when it opened, `opened_at`: a new fact, read whole, or the
issue defers with `linked_unreadable`.

A draft's own pushes, and a person converting it back to draft, are not in `issue-facts/1`. Until the hand-over brings
them, an issue whose draft is busy may read stale; that shows more, never less.

## Why

§4.1 decided that an issue's stale times apply, and how an item's movement is read: the newest time a writer, a Lens or
the Factory moved it. This reads that from an issue's own facts. Only a person with write access, an App the
configuration names, or the Factory moves an issue, so no stranger can keep one from showing. An admitted outsider's
pull request moves nothing, since its author could close and reopen it each day and keep the issue quiet for ever.
One calendar and one test of the limit are kept, imported and not copied, as decision 0028 says. Whatever cannot be
read, the Lifecycle, its limit, `now` or the context, shows more and never less, and a pure function does not crash
on it. Without `opened_at`, an issue that waited days in `ready` would read stale the moment its draft opened. A
deferral of the whole scope is one cause, reported once (§4.6). `in_review` stays quiet: its pull request's own
staleness shows it.

## Boundaries

| Boundary | Check |
|---|---|
| An issue's wait past its State's limit in `lifecycle/issue.json`, given with the configuration, shows `stale`: only the attention changes, only on a `ready` wait, and never under a deferral of the whole scope; a Lifecycle not the issue's shows such a wait as stale | `tests/test_issue.py::test_a_wait_past_its_states_limit_shows_stale_and_changes_nothing_else`, `tests/test_issue.py::test_a_person_a_run_nobody_or_a_deferral_of_the_whole_scope_is_never_stale`, `tests/test_issue.py::test_a_wait_counts_no_earlier_than_the_chain_of_passes`, `tests/test_issue.py::test_a_lifecycle_not_the_issues_shows_every_wait_as_stale` |
| An issue moves when its life begins, its content changes, a writer acts or comments, a person or an App the configuration names adds or removes a control label, a Run on it starts, or the Factory's or a writer's linked pull request opens or closes, and at nothing else | `tests/test_issue.py::test_an_issue_moves_at_what_its_own_facts_say_moved_it_and_at_nothing_else` |
| A linked pull request's opening time is read whole, or the issue defers | `tests/test_issue.py::test_a_link_with_no_opening_time_defers`, `examples/invalid/issue-facts.a-link-with-no-opening.json` |
| An issue's Lifecycle whose limit for the State is no finite number of minutes shows the wait as stale; an end the Lifecycle declares never goes stale | `tests/test_issue.py::test_a_lifecycle_whose_limit_cannot_be_read_shows_the_wait_as_stale`, `tests/test_issue.py::test_an_end_never_goes_stale` |
| Any App `issues.label_apps` names moves an issue by any control label it adds or removes; an App named nowhere moves nothing | `tests/test_issue.py::test_any_app_the_configuration_names_moves_an_issue_by_any_control_label` |
| Only the Factory's or a writer's linked pull request moves an issue by opening or closing; an outsider's, even one admitted, moves nothing | `tests/test_issue.py::test_an_outsiders_pull_request_moves_nothing_even_once_admitted` |
| A `now` that is no moment raises nothing on an issue, and shows a wait as stale | `tests/test_issue.py::test_a_now_that_is_no_moment_shows_a_wait_as_stale_and_raises_nothing` |
| A context that cannot be read raises nothing on an issue, and says nothing of the passes, as an unreadable `passes_since` does not | `tests/test_issue.py::test_a_context_that_cannot_be_read_says_nothing_of_the_passes` |
