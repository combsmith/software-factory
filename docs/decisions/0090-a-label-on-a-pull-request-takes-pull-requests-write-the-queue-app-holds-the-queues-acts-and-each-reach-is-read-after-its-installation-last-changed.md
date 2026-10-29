# 0090. A label on a pull request takes pull_requests: write, a label on an issue issues: write, the queue App holds the queue's acts, and each App's reach is read after its installation last changed

Status: accepted. The second machine-user window's P-41, its label case run again on 2026-10-29, and P-39 read again
for the controller's new grant and the queue App, under the orchestrator's rulings of 2026-10-28 and 2026-10-29. It
adds to decision 0035, whose fixtures P-39 keeps, and to decision 0081.

## Decision

| What | Decided | Because |
|---|---|---|
| P-41 | `trials/P-41.json`, pass: a person's request for changes stood after an App's push until the pr-review App dismissed it; a person with write access dismissed the machine user's approval; the timeline named each dismisser, typed, and the state before; the controller added and removed a label on a pull request, each event naming it | The Kernel's reading of reviews, dismissals and labels holds as the design wrote it |
| A label's permission | A label on a pull request maps to `pull_requests: write` (`effect:add_label`, `effect:remove_label`), held by the controller. A label on an issue maps to `issues: write` under the new need `write:issue_label`, for the issue Lifecycle | P-41: the label was refused with `issues: write` and `pull_requests: read`, and made with `pull_requests: write` alone. One need maps to one permission, and the two places take two |
| The controller's grant | `pull_requests: write`, as the Maintainer granted it and P-39 read it again on 2026-10-29 | The data is held to what GitHub granted (decision 0035) |
| P-39's reach | Each App's reach is read no earlier than its installation last changed, and a time that cannot be read is refused | A reach read before a change holds what the installation reached then, not now |
| The queue App | Required in the data. `combsmith-sf-queue` ("A narrow queue App, combsmith-sf-queue, enqueues and dequeues with contents and pull-request write alone (P-2)", issue 381) holds `contents: write` and `metadata: read`, and nothing else. `effect:enqueue_merge` and `effect:dequeue_merge` map to `contents: write`, held by it alone. Its key is kept in `factory-queue`, the queue step's, never `apply`'s. P-39 reads its registration, installation and reach, and the reach script takes its key | Window 3 (`trials/P-2.queue-app.json`, decision 0089): its enqueue and dequeue each needed `contents: write` alone, and the Maintainer removed `pull_requests` from it (2026-10-29) |
| The fake's rules | `a_request_for_changes_survives_a_push`, `an_app_can_dismiss_a_review`, `a_writer_can_dismiss_an_approval` and `an_app_can_label` are grounded on P-41, each read by the timeline port from the fixture. `an_actor_has_a_kind` stays unverified: P-41 typed every actor on its reviews, dismissals and labels, but met no thread | A rule is grounded only where the port reads the fixture as the fake assumes it (L-51) |

## Why

The second window and window 3 asked what each of the Factory's writes takes on GitHub, and what an App's read
of its own reach is worth once its installation changes. The data now says the least that was granted and read.

## Boundaries

| Boundary | Check |
|---|---|
| Each grant serves a need the table maps, and the data agrees with P-39's reads | `tools/check_apps.py`, `tests/test_tools.py::test_the_data_is_held_to_what_github_granted_each_app` |
| A reach read before its installation last changed is refused | `tests/test_tools.py::test_a_reach_read_before_its_installation_last_changed_is_caught` |
| The queue App's key is kept in `factory-queue` alone | `tests/test_tools.py::test_each_apps_key_is_kept_in_the_environment_of_the_job_that_holds_it` |
| The table names `write:issue_label` | `examples/invalid/apps.the-table-leaves-out-the-issue-label.json` |
| P-41's rules are read by the port as the fake assumes them | `tests/test_adapters.py::test_the_port_reads_each_grounded_rule_as_the_fake_assumes_it` |
