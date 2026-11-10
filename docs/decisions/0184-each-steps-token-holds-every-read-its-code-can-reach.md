# 0184. Each step's token holds every read its code can reach

Status: accepted. The Factory Builder's ruling of 2026-11-10. Slice 1's third dry run, on v0.1.3, got past the reader and the model, and then stopped in `apply` as `pause_unreadable`. The Builder asked for a sweep, so that the next dry run does not stop at the next such gap.

## Decision

| What | Decided | Because |
|---|---|---|
| The gap | `apply` reads the Pause again, through the Role App's token, and `harness/apply.py`'s `READS` asked for no grant of it. It now asks for `read:pass.pause`, `actions_variables: read`, which `config/apps.json` already gives the review App | The token was minted from a list kept by hand, apart from the reads it serves |
| The sweep | For each step that mints a token (the reader, `apply`'s read again, the queue App's act, the pass and the pass's writes step, `adapters/effects.py`), a test walks the step's code statically from its entry, through every function and class of `adapters/`, the Harness and the Controller it calls, to each function that builds a request of GitHub's itself. It holds the token, minted from `config/apps.json` as the step mints it, to every permission those requests take, each at its level | A list of needs drifts from the code it serves; a walk of the code does not |
| What a request takes | A table the test holds, by each function that builds a request, as GitHub's documentation names each endpoint's permission and level, with how many requests that function builds. A function the walk reaches that builds a request no table names fails it, wherever it is, and so does one more request in a function already classed. The walk follows every import's form, a dotted one included | A read added anywhere a step reaches is classed before it ships |
| What is minted | Each step's mint as the step asks for it: the reader's `wanted`, and the pass's; `apply`'s `READS` and the queue's `NEEDS`, which their own step tests pin as asked (`test_apply_reads_with_reads`, `tests/test_queue.py`); and the writes step's, observed at its mint | The sweep holds the reads to what is asked for, and each step's test holds what is asked for to the mint |
| What it leaves out | A Role's writes, minted per Effect from that Effect's own need; the approving act, which mints no App's token, by any way, and reads through the machine user's; and a request a step makes through another token, named beside the step with that token | Each has its own token, which this step does not mint |
| What is owed | The queue App's act reads the pull request with no `pull_requests` grant, and the App holds none: "queue_step mints no pull_requests read, and the queue App holds none" (issue 711). While `accounts.queue` is null, the test holds the gap as owed, exactly. Once it is set, the gap fails the test | The queue App is not live, and no trial has run with its grant changed |

## Why

Each dry run so far has stopped at one more read a token could not make: the reader's view of a private App, then `apply`'s view of the Pause. Each was found by spending a Release. The walk finds them all at the desk, before the next.

## Boundaries

| Boundary | Check |
|---|---|
| Each live step's token holds every read its code can reach; a read no table names fails the walk; the walk reaches each step's known reads; the approving act mints nothing | `tests/test_token_needs.py::test_each_step_mints_every_permission_its_reads_take`, `tests/test_token_needs.py::test_every_read_a_step_can_reach_is_named`, `tests/test_token_needs.py::test_the_walk_reaches_the_reads_each_step_is_known_to_make`, `tests/test_token_needs.py::test_the_approving_act_mints_no_token`, `tests/test_token_needs.py::test_a_write_is_held_at_its_level`, `tests/test_token_needs.py::test_each_classed_function_builds_the_requests_it_was_classed_for`, `tests/test_token_needs.py::test_a_request_through_a_dotted_import_is_reached`, `tests/test_steps.py::test_the_controller_mints_from_its_key`, `harness/apply.py`, `harness/read.py`, `controller/__main__.py`, `adapters/effects.py`; mutant: "apply's token holds no grant for the Pause"; mutant: "the reader's token holds no grant for the issues"; mutant: "the pass's token holds no grant for the Pause"; mutant: "the effects step's token cannot read the Pause" |
