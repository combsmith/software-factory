# 0128. Each queue act is a dispatched Run of the queue workflow, once it is named

Status: accepted. The Factory Builder's ruling of 2026-11-03 on the queue step of "A narrow queue App, combsmith-sf-queue, enqueues and dequeues with contents and pull-request write alone (P-2)" (issue 381), part of "Epic: slice 1, first approval. A Release on next reviews a pull request to this repo, and the machine user's approval stands" (issue 182): its first part, the Controller's and the Kernel's, of three. It changes the design's line that an enqueue and a dequeue are the Controller's and have no run record, and that the Controller's App makes the dequeue.

## Decision

| What | Decided | Because |
|---|---|---|
| The shape | An enqueue, a dequeue and a resolution are each a dispatched Run of the queue App's workflow, as an approval is a Run of the approval workflow: named by run-name/1 under the owner Role, with an Intent of its own, `enqueue-merge`, `dequeue-merge` or `resolve-thread`, a Run id minted beside the Decision, and the pass job's token dispatching it with the three inputs a Run takes | The queue App's key is held by its step alone, and a Run's record is what counts a resolution (decision 0127) |
| Until it is named | `config/controller.json` gains `workflows.queue`, null. While it is null, no Run id is minted for these acts, each is recorded `not_built` as before, the pass job's token may not dispatch the file, and its runs are not read | The workflow, its job and the queue step are the next two parts; nothing is dispatched to a file that does not exist |
| Once it is named | The pass dispatches each act as `dispatch_queue`, a write of `writes/1` and `written/1`, held to its record as every dispatch is, stopped by a person's Pause as every dispatch is, and the records port reads the file's runs beside the run and approval files | The same path as an approval's, so nothing new is trusted |
| A landed enqueue or dequeue | Outside the Run ceiling, as a landed approval is: each is on the timeline and counted there among the acts | Counted once, not twice |
| A failing enqueue | Held by its own jobs alone: those failing for the item at `max_attempts`, and every one that did not land at `max_runs_per_item`. The Runs other Intents spent never hold it | An approved item's enqueue spends no model, and goes ahead at the Run ceiling (FR-39); a job that keeps failing is still never dispatched for ever |
| A failing dequeue | Not braked: it is an act that stops work, never refused, and only a Pause stops it | The design's rule for an act that stops work; a dequeue that cannot land leaves the item for the Maintainer to see |
| What is not built | The queue step that mints the App's token from `QUEUE_APP_KEY`, reads the item again and makes the one write, with `enqueuePullRequest` bound to the decided head by `expectedHeadOid`; the workflow files; `accounts.queue`, which waits on the users read P-39's re-read records; and reconciliation's matching of the queue App's writes to the queue job's own record | The second and third parts, and the Release lane's trial |

## Why

The queue App alone may enqueue, dequeue and resolve another's thread, and its key is read only by its step. Carrying out each act as a dispatched Run gives that step a record the Kernel counts from, as the approving act has.

## Boundaries

| Boundary | Check |
|---|---|
| Once named, each queue act gets a Run id and is dispatched under its Intent's run-name; unnamed, each stays `not_built`; an act the queue App does not make stays one | `tests/test_controller.py::test_a_queue_act_gets_a_run_id_and_a_dispatch_once_its_workflow_is_named` |
| The pass job's token may dispatch the queue file only once it is named; the plan dispatches it as `dispatch_queue`, held to its record, stopped by a person's Pause | `tests/test_effects.py::test_a_queue_act_is_dispatched_to_the_queue_workflow_once_it_is_named` |
| The queue file's runs are read once it is named | `tests/test_controller.py::test_the_queue_workflows_runs_are_read_once_it_is_named` |
| A landed enqueue or dequeue spends no Run; a failing enqueue is held by its own attempts and Runs, never by others' | `tests/test_decide.py::test_each_landed_resolution_counts_toward_the_act_ceiling` |
| The records port reads the two Intents as a pull request's, which ask for no contract | `tests/test_adapters.py::test_every_intent_a_lifecycle_runs_is_ruled_on_whether_it_asks_for_a_contract` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
