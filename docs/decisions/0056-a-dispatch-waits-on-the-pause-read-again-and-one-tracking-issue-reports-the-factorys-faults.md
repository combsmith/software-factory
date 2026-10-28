# 0056. A dispatch waits on the Pause read again outside the Kernel, and one tracking issue reports the Factory's faults

Status: accepted. A working ruling of 2026-10-21 for "Controller: one pass reads, decides, records, dispatches, writes the view and raises the reconciliation alert" (issue 193), its PR 3, rulings 7 and 8 and the Maintainer's point (d), which he may overturn in review. It adds to `docs/decisions/0051-the-controllers-writes-go-through-one-credential-each-and-every-one-is-recorded.md`, whose plan it extends, and to `docs/decisions/0003-one-controller-admits-every-run.md`, whose Pause it reads once more.

## Decision

| What | Decided | Because |
|---|---|---|
| The Pause, read again | Before any dispatch, `adapters/pause.py` reads `FACTORY_PAUSED` on the org and on the home repo and every repo a dispatch acts in, with the Controller's token. No dispatch is sent, the successor's among them, unless every scope reads exactly `false`. A scope that reads `true` stops them as `paused`. One unset, unanswered or read as anything else stops them as `pause_unreadable`. A status and the tracking issue are no act, and are written under a Pause | A brake outside the Kernel holds if the Kernel does not (0003), and it reads both scopes where the shim sees one value. A Pause that cannot be read stops what a Pause stops (I-13) |
| What a refusal costs | A dispatch refused as `paused` is no fault and does not fail the step, since a person set it. One refused as `pause_unreadable` is, and does | A Pause the Maintainer set is his act, and a run that fails each pass while he holds it would hide every real fault |
| One tracking issue | Planned in every pass, last but one. Its causes are the pass record's alerts, which `pass/1` now keeps, less `paused`, plus `write_failed` when a write before it failed or was refused but for a Pause or an act no write serves. It is found again among the home repo's open issues by its author's account id and type, `accounts.controller`, never by a title or a label | The Factory's faults reach a person in one place, and a title or a label anyone can set must not decide which issue it is |
| Open, edit, close | With causes and none open, it is opened, `Factory alerts`, with the Maintainer assigned, `accounts.maintainer`, which notifies him once. With causes and one open, its body is edited only when its causes change, which notifies no one, or when it does not list him, which assigns him again and notifies him. With none and one open, it is closed as completed. Two open are written to by no one, `tracking_issue_twice`, and the step fails. Each write is sent once, through a transport that may send only these, and is `applied` only on what GitHub's answer reads back: the state, the number and the body asked, `completed` for a close, and the Maintainer among the assignees, by id and login, for an issue open. One open that does not list him is `failed`, `assignee_dropped`. An answer that refuses it fails the step, `write_refused` | "One tracking issue" and "notified once" (§4.7). A comment for each new cause would be the one write with no recovery key (§3.6) |
| Its body | A fixed first line, one line for each cause code, sorted, and the pass that wrote it, with its time and its Release. Codes and identifiers alone | No text from outside reaches the Factory's own writes |
| Dormant by data | While `accounts.controller` or `accounts.maintainer` is null, no issue is written: `uncounted`, a fault, when there is a cause to report, and `no_account`, none, when there is not. The App's bot account waits on the trial that records it. Until the Maintainer grants the Controller's App the variables' read and `issues: write`, the Pause reads unreadable and nothing is dispatched | Nothing runs on a grant or an account no trial has recorded |

## Why

0051 sent the dispatches and left the Pause's second reading and the tracking issue for their grants. Both are buildable now, to the point their trials take over. The brake must exist before the first live dispatch, and the tracking issue is how a fault reaches the Maintainer at all. The reads no trial has recorded, the variable's answer and the open issues by creator, wait `@pending`. The writes are held to P-46's answers for an issue opened and closed.

## Boundaries

| Boundary | Check |
|---|---|
| No dispatch is sent unless the Pause reads exactly `false` on every scope, each repo's org the home's; a person's Pause is no fault | `tests/test_effects.py::test_no_act_or_run_is_sent_unless_the_pause_reads_exactly_not_paused_on_every_scope`, `tests/test_effects.py::test_the_persons_own_pause_opens_no_tracking_issue` |
| A Pause not answered as a variable is unreadable, and a scope that could name another path is not asked | `tests/test_effects.py::test_a_pause_not_answered_as_a_variable_is_unreadable` |
| One tracking issue is opened with the Maintainer assigned, edited as its causes change and closed when clear, applied on what is read back | `tests/test_effects.py::test_one_tracking_issue_is_opened_once_edited_in_place_and_closed_when_clear` |
| An assignment GitHub dropped fails the step and is made again; a close for another reason is not applied | `tests/test_effects.py::test_one_tracking_issue_is_opened_once_edited_in_place_and_closed_when_clear` |
| Two open are written to by no one; an App or a Maintainer unnamed writes nothing | `tests/test_effects.py::test_a_second_open_tracking_issue_is_never_written` |
| A person's own Pause opens no tracking issue | `tests/test_effects.py::test_the_persons_own_pause_opens_no_tracking_issue` |
| The open issues are the App's, told by its account, never by a title, and of those the one this port wrote | `tests/test_effects.py::test_the_open_issues_are_the_apps_own_told_by_its_account` |
| The Controller's token sends only the Pause's reads and the tracking issue's writes | `tests/test_effects.py::test_the_controllers_token_sends_only_the_pause_and_the_tracking_issue` |
| The pass record keeps its alerts | `tests/test_controller.py::test_the_pass_record_keeps_its_alerts_for_the_tracking_issue` |
| The Pause is read as GitHub holds the variable | `tests/test_effects.py::test_the_pause_is_read_as_github_holds_the_variable` |
| The open tracking issues are read by their author as GitHub lists them | not held yet: `tests/test_effects.py::test_the_open_tracking_issues_are_read_by_their_author` |
