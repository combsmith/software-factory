# 0028. An issue's State is derived in a module of its own

Status: accepted. Taken as a working ruling for "Kernel: derive an issue's State from its facts"
(issue 41) on 2026-10-17, which the Maintainer may overturn in review.

## Decision

An issue's State comes from one function, `derive(facts, runs, config)` in `kernel/issue.py`. It
returns `{state, reason, evidence}`, as the pull request's does, and reads only the issue's own
facts. `kernel/decide.py`, `kernel/derive.py`, `kernel/terms.py` and `kernel/gate.py` are not
edited. When the Controller is built it picks the function by the item's type; if one Kernel entry
is wanted later, the smallest change is a dispatch at the top of `decide.decide`, decided with it.

`kernel/issue.py` imports five names and changes none of them: `is_time`, `runs_on`, `in_progress`
and `standing_labels` from `kernel/derive.py`, and `is_person` from `kernel/gate.py`. There is one calendar, and
one reading of "what a person placed, only a person ends". The pull request's work treats these
five as a contract. Once both are built, the readers they share move into one module.

An issue's facts are `issue-facts/1`, in `schemas/issue-facts.schema.json`. Its author is an actor,
with a kind, a name and write access: only a person who opened it accepts it by authorship, never
an App or the machine user, whatever their access. Its control labels are
`label_events`, as on a pull request: label, action, who and when. Each linked pull request carries
its number, its class as the port gives it, its opener, whether it is open or a draft, when it
merged and closed, whether its diff was empty, and its own `label_events`. The Hold, hands-off and
whether a person once admitted it are read from those, with the pull request's own reading.
`factory:triage` and `factory:ready` count from their latest add, and any removal at or after it
ends them: they let work go, so a removal stops it. The flags of `complete` are `timeline`,
`linked` and `runs`. Section 3.3 of the design is corrected to these shapes.

`config/defaults.json` gains one block, `issues`: `served_from`, `left_out_labels`,
`left_out_types`, and `label_apps`, the App whose `factory:triage` and whose `factory:ready` count.
Every value is null or empty: no issue is served, and only a person's label counts, until the
Maintainer turns issues on.

A list read short defers with `facts_incomplete`, and a state, a label event or name, a linked pull
request, the issue's life, its content, its type or the `issues` block that cannot be read defers
with a code of its own, before row 1, for a closed issue too. In the same second the reading that
stops work wins: a merge at the start of a life is `done`, a label added at an edit or a reopening
does not count, and of two adds in one second each must count, whatever their order.

A `factory:ready` the Factory added counts only if the latest Run of the readiness Intent,
`judge-readiness`, that started no later than the label completed for the issue's present content.
One still running, or none, as once its record has expired, means nothing shows the content was
judged: the label does not count, and the issue stays in `triage`. The Intents an issue's State
reads, `judge-readiness` and the opening Run's `open-pull-request`, are codes in `kernel/issue.py`,
which the issue's decision adopts.

Which pull requests are linked is read from the `class` the port gives each, as for a pull request:
the port must get the class right, and the Kernel does not check it against the opener.

The Run ceiling of row 4 is not derived here. The brakes count it (decision 0003), and the issue's
decision will ask them, as the pull request's does.

## Why

The derivation reads nothing of a pull request's facts, so a module of its own lets the issue's
work and the pull request's run side by side without touching the same lines; the same holds for
the mutants, which sit in a list of their own above the pull request's. Importing the readers,
rather than copying them, keeps one calendar and one reading of who placed a label (L-17). The
event shapes let the pull request's tested reading serve the Hold, hands-off and admission. The
defaults are null because the Consumer entry has no fields for issues yet (design §9.9), and null
fails closed. The Run ceiling stays with the brakes because they count it and nothing else does.

## Boundaries

| Boundary | Check |
|---|---|
| The situations the reviews of the issue Lifecycle found derive as the design says | `tests/test_issue.py::test_the_situations_the_reviews_found_derive_as_the_design_says` |
| Every State the function derives is declared in the Lifecycle, and every declared State has a code | `tests/test_issue.py::test_every_state_is_declared_and_every_declared_state_has_a_code` |
| The module that derives an issue's State is held pure | `tests/test_issue.py::test_the_kernel_module_that_derives_an_issue_is_held_pure` |
| A list read short defers, a closed issue's too | `tests/test_issue.py::test_a_list_not_read_in_full_defers` |
| A label event, a linked pull request, a life or a content that cannot be read defers, in that order | `tests/test_issue.py::test_what_cannot_be_read_is_read_in_its_order` |
| No issue is served until the Maintainer turns issues on, and no App's label counts until it is declared | `tests/test_issue.py::test_no_issue_is_served_until_the_maintainer_turns_issues_on`, `tests/test_issue.py::test_no_app_counts_until_it_is_declared` |
| A merge at the start of a life is done, and a label at an edit or a reopening does not count | `tests/test_issue.py::test_a_merge_at_the_start_of_a_life_is_done_and_one_before_it_is_not`, `tests/test_issue.py::test_triage_and_ready_count_only_in_the_present_life` |
| A merge that landed after a person closed the issue, after anyone but a person with write access reopened it, or while a Hold stood, whoever placed it, or hands-off a person did not place, on the issue or its linked draft, is never done: the State stays, and the reason names the contradiction, `merged_while_declined` or `merged_while_held`, which needs a person. Each is placed by time against the first such merge: the first close of this life before the merge's second is a person's, by anyone who may close the issue, and no later close or reopening by anyone moves it; a reopening or a Hold in that second wins; a Hold placed later changes nothing. A person's hands-off that stood at the merge, with a Hold beside it or not and lifted since or not, a Hold a person released and an outsider's reopening after the merge leave it done. The facts carry no closer: an outside author's close of their own issue before the merge reads as a person's, once, "Kernel: a merge read while an issue is held or declined is a Hold, not done" (issue 237), from the Maintainer's ruling on "Design: does a merge end a held or a declined issue? The issue world met it on seeds 20, 22 and 99" (issue 227) | `tests/test_issue.py::test_a_merge_read_while_a_person_closed_or_held_the_issue_is_never_done` |
| An issue's facts carry when its present life was first closed, null while it has not been, a time no earlier than the life began while closed and, while open, only where anyone but a writer reopened it last, no later than that reopening; and when it was last reopened by anyone, null if never, a writer's at the start of the life it began and anyone else's no earlier; one that cannot be read whole defers, as the state or the life | `tests/test_issue.py::test_a_close_or_a_reopening_without_its_time_cannot_be_read`, `examples/invalid/issue-facts.a-close-time-in-words.json`, `examples/invalid/issue-facts.a-reopening-time-as-a-number.json` |
| The issue Lifecycle serves the default branch's pull requests alone, as GitHub enforces for the keywords in a description: one to another base carries no closing reference from them, as `trials/P-33.json` shows, and the port reads a pull request as linked only while its base is the default branch, a link made by hand among them; the port's reading of the join from each pull request's own references alone, "Design: what P-33 and P-34 showed of closing references, an issue's content time and a timeline's count" (issue 240) | `tests/test_tools.py::test_the_issue_fixtures_hold_what_grounds_the_four_rules`; the port's reading is waiting on `adapters/issues.py` |
| A timeline is read whole when its last page's `hasNextPage` is false, never by `totalCount`, which counts every item whatever types were asked, nor by a page shorter than was asked (P-33); the fixture of a timeline read short is owed by the facts port | waiting on `adapters/issues.py` |
| An issue's `content_changed_at` is the newer of its `lastEditedAt` and the timeline's last rename, or its creation while neither has moved, and no list of the body's edits is read (P-34) | waiting on `adapters/issues.py` |
| Any removal at or after the latest add ends `factory:triage` and `factory:ready` | `tests/test_issue.py::test_any_removal_at_or_after_the_latest_add_ends_ready_and_triage` |
| Adds in one second are read the way that stops work, whatever their order | `tests/test_issue.py::test_adds_in_one_second_are_read_the_way_that_stops_work_whatever_their_order` |
| Only a completed readiness Run of this content lets the Factory's `factory:ready` count; an expired record does not | `tests/test_issue.py::test_only_a_readiness_run_judges_and_only_once_it_has_completed`, `tests/test_issue.py::test_a_factory_ready_whose_run_record_has_expired_does_not_count` |
| A state, label names, a type or an `issues` block that cannot be read defers | `tests/test_issue.py::test_an_unreadable_state_defers`, `tests/test_issue.py::test_unreadable_label_names_defer`, `tests/test_issue.py::test_an_unreadable_type_defers`, `tests/test_issue.py::test_an_issues_block_that_cannot_be_read_defers` |
| Acceptance lapses only once it held and work began in this life | `tests/test_issue.py::test_acceptance_lapses_only_once_it_held_and_work_began_in_this_life`, `tests/test_issue.py::test_a_closed_link_is_work_begun_only_in_the_life_it_closed_in` |
| Only a person who opened an issue accepts it by authorship | `tests/test_issue.py::test_an_insiders_issue_is_accepted_and_an_outsiders_is_not`, `tests/test_issue.py::test_an_unreadable_author_defers` |
| The world's seeds reach a stranger's pull request, a reopening by another and an expired record, and the State is as the rows say | `tests/test_issue_simulator.py::test_the_seeds_reach_each_fault` |
| Every change of State the issue world makes, the exploration of every change finds, and what it finds that the world never makes is named with why | `tests/test_issue_simulator.py::test_invariants_hold_under_faults`, `tests/test_transitions.py::test_an_issue_explored_is_held_to_the_issue_lifecycle` |
| A merge is read as it stood at the merge, never from the pull request's references as they stand now: it is done only where the issue's timeline names it the closer of the issue's close, or where it landed while a person had the issue closed; one the timeline names no close for, of an issue still open, defers for a person, `merged_without_closing`, whether GitHub has not closed the issue yet or an edit after the merge added the reference, as `trials/P-46.json` showed one can, "Kernel: a merged pull request's closing reference is read as it stood at the merge (P-46 failed)" (issue 267) | `tests/test_issue.py::test_a_merge_counts_only_where_the_issues_timeline_names_it_the_closer` |
| Each linked pull request carries `closed_issue_at`, the time of the issue's close it is the closer of, or null; one only of a merge, no earlier than it, read whole, or the issue defers | `tests/test_issue.py::test_a_close_of_the_issue_that_cannot_be_read_defers` |
| The port reads each closer in the timeline read beside `closed_first_at`, and lists as linked each pull request the timeline names the closer of in the present life, whatever its references say now | waiting on `adapters/issues.py` |
