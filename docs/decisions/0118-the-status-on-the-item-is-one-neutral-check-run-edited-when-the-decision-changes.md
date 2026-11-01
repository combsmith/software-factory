# 0118. The status on the item is one neutral check run, edited in place when the Decision changes

Status: accepted. The Factory Builder's ruling of 2026-10-31 to build step 8 of the audit of "Epic: slice 1, first approval. A Release on next reviews a pull request to this repo, and the machine user's approval stands" (issue 182) from trial P-12. It builds ruling 6 on "Controller: one pass reads, decides, records, dispatches, writes the view and raises the reconciliation alert" (issue 193), which decision 0051's row "Not built yet" left waiting on that trial.

## Decision

| What | Decided | Because |
|---|---|---|
| Where | One check run by the Controller's App, named `status_on_item` from the configuration, on the head read beside the pull request's facts. `pass/1` gains an optional `head`, carried only where a status goes | It describes the content the Decision was made on, even if the pull request has moved since |
| When | The App's check runs of that name on the head are listed, `filter=all`. The latest of them carrying this Decision's `external_id`, `completed` and `neutral`: nothing is sent, `already_applied`. Anything else: it is edited in place. None: one is made. A list that is not whole, a full page among it, writes nothing, `checks_unreadable` | GitHub holds the key, so a status that once failed to write is not stale for ever (decision 0002); P-12: of two, the later is the one GitHub shows, and `latest` lists only it |
| The key | `external_id` is `d` and the first 32 hex digits of the SHA-256 of the Decision's canonical JSON, so any change to it changes the key | Any change a person would read writes again, and none other |
| Its conclusion | Always `completed` and `neutral`. The Controller's token may send no other, and no other field, name, head, key or output form | It says neither pass nor fail. GitHub counts a neutral check as met, so what keeps it from being a gate is its name, which is no required Lens's, and that no ruleset names it |
| Its text | The title is `<state>: <reason>`. The summary holds the attention, outcome, action, `next_actor`, `content_id`, pass, Release and evidence. An evidence item is shown only if it matches the form of an identifier, at most 20, in at most 4096 characters; the rest are counted. `details_url` is the pass's run when one can be read. The whole output is sent every time | No text from outside reaches it; P-12: an edit with no output keeps the title and empties the text |
| On which items | An open pull request read with a commit, served, and not one a person left hands-off, which the Kernel's `left_alone` reads from the facts because `derive` reads a draft and an incomplete read first. Where the label events cannot be read, none: a later pass that reads them writes it. An issue gets none | Hands-off is never acted on, whatever else is true of the item; what is ended or not served gets no change; and an issue has no commit |
| Under a Pause | It is written | It is no act, and it is how a person sees why nothing moves |
| The bound | At most `max_status_writes` in `config/controller.json`, 50, sent in item order. Every write sent counts, whatever GitHub answered; one found already there does not, and the rest are `refused`, `status_bounded`, which is no fault and waits for the next pass | A first pass or a Pause changes every status at once, and GitHub limits requests that create content |
| Read back | `applied` only when the answer is the App's, of that name, head and key, `completed` and `neutral`, of the run edited, with a node id `written/1` can hold, which is its key there. Anything else is `failed`, `not_read_back` | Reconciliation matches a check run by its node id; P-12: GitHub answers a 200 that may not hold what was sent |
| A refused token | A 401 or 403 on a status ends the pass's statuses, each later one `refused`, `token_refused`. The tracking issue still asks for itself | Decision 0051's rule, for this credential; but a 403 may be GitHub's limit, and an alert is not lost to one |
| The order | Each status goes after the dispatches and before the tracking issue | So that the tracking issue can say one failed |

## Why

Ruling 6 is the Maintainer's way to see from a pull request what the Factory decided and why. P-12 has run, so nothing keeps it waiting. P-12's recorded bodies hold no node id. The port reads one because the check-runs read `adapters/seen.py` matches holds it as the key, and a first live write that answers without one fails as `not_read_back`, which says so.

## Boundaries

| Boundary | Check |
|---|---|
| A status is written only when the Decision changes, edited in place, the later of two, and another name's or App's is not the status | `tests/test_effects.py::test_the_status_is_written_only_when_the_decision_changes` |
| What is not read back, or a list that is not whole, is failed and says so | `tests/test_effects.py::test_what_is_not_read_back_fails_and_says_so` |
| It is sent and answered as P-12 recorded | `tests/test_effects.py::test_the_status_reads_p12s_answers_as_they_stand` |
| It neither passes nor fails, and the token may send nothing else | `tests/test_effects.py::test_the_status_neither_passes_nor_fails` |
| It carries codes and identifiers alone, within its bounds | `tests/test_effects.py::test_the_status_carries_codes_and_identifiers_alone` |
| `kernel.decide.left_alone`: a person's hands-off, whatever stands before it, or label events that cannot be read; not a label no person placed | `tests/test_decide.py::test_an_item_is_left_alone_for_a_persons_hands_off_or_labels_that_cannot_be_read` |
| None on an item left hands-off, even a draft or one read in part, ended, not served, whose label events cannot be read, with no head, or on an issue; the plan is the record's | `tests/test_effects.py::test_no_status_is_written_on_an_item_left_alone` |
| It is written under a Pause; the bound waits with no fault; a refused token ends the Controller's writes | `tests/test_effects.py::test_a_status_is_written_under_a_pause_and_a_pass_writes_at_most_its_bound` |
| A pass carries the head read beside the facts, a commit's alone | `tests/test_effects.py::test_a_pass_carries_the_head_read_beside_the_facts_and_only_a_commit`, `examples/invalid/pass.a-head-that-is-no-commit.json` |
| The bound is required and at least one | `examples/invalid/controller.a-bound-on-the-status-of-none.json`, `examples/invalid/controller.no-bound-on-the-status.json` |
| Each status goes after the dispatches and before the tracking issue | `tests/test_effects.py::test_the_writes_go_in_their_order` |
| The step gives it its name, App and run | `tests/test_effects.py::test_the_step_gives_the_status_its_name_its_app_and_its_run` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
