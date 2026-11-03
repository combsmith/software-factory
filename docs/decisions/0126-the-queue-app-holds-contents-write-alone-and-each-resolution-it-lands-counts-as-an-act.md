# 0126. The queue App holds contents: write alone, and each resolution it lands counts as an act

Status: accepted. The Factory Builder's assignment of 2026-11-03 on "A narrow queue App, combsmith-sf-queue, enqueues and dequeues with contents and pull-request write alone (P-2)" (issue 381), part of "Epic: slice 1, first approval. A Release on next reviews a pull request to this repo, and the machine user's approval stands" (issue 182). It carries out window 3's reading that the App's least permission is `contents: write`, and builds the count decision 0086's row "Counting it" waited on. It changes decision 0086's rows "The needs", where the resolve act waited on the queue App, and "Counting it", whose count was still to come.

## Decision

| What | Decided | Because |
|---|---|---|
| The App's grant | `combsmith-sf-queue` holds `contents: write` and `metadata: read`, and nothing else. GitHub's public answer for the App, read on 2026-11-03, holds exactly those: the Maintainer has removed `pull_requests: write` | Window 3 ran all three of its acts, enqueue, dequeue and resolving another's thread, on a token of those two alone; `pull_requests: write` served none |
| Its needs | `config/apps.json` maps `effect:enqueue_merge`, `effect:dequeue_merge` and `effect:resolve_thread` to its `contents: write`. The resolve act no longer waits on the App | Each write belongs to one App (`tools/check_apps.py`), and the queue App is the one that may resolve another's thread (decisions 0082 and 0086) |
| No write left unmade | `tools/check_apps.py` refuses a write the table maps to a permission that no App holds. Before, mapping the resolve act and forgetting to give it to the queue App would have passed | A need belongs to one App; until now only a need held by two was refused |
| Its key | In the environment `factory-queue`, secret `QUEUE_APP_KEY`, read only by the queue step; `tools/check_apps.py` holds that step as its holder | Already in the data from window 3; unchanged here |
| Counting a resolution | A resolution is no timeline event, so the port's `acts_since_writer` never sees one. Each resolution the queue App's job landed, a Run of Intent `resolve-thread` that succeeded since a writer last acted, in the writer's own second too as the timeline port counts an act, is added to it from the run records at every call, and the sum is held to `max_acts_per_item` in `kernel/brakes.py`. The records port reads that Intent as a pull request's Run | Every act that moves work on is bounded (I-8), and state is derived from the run records at every call, never stored |
| The Run ceiling and attempts | A landed resolution spends no model, so the Run ceiling does not count it, as it does not count a landed approval. One that did not land is no act: before the Kernel decides the act again, its failed jobs are held to `max_attempts` as the item's, and every Run to the Run ceiling, as an approval's are | The same split as the approving act's, for the same reason: a job that keeps failing is never dispatched for ever |
| What is not built | The queue step that dispatches the job and lands a resolution, and the dispatch of an enqueue or a dequeue through the App. The Controller records each `not_built` until it lands, so none goes uncounted. That step must run as a workflow the records port reads and be named by run-name/1, or its resolutions go uncounted. The simulator's queue App records each resolution as a landed Run, as the port will, and its settle gives the person five rounds of confirmation where it gave three: a resolution held at the Run ceiling, as an approval is, takes seed 140 one more lap, and each fix push needs a fresh confirmation. P-39's read of the App again, and its fixture, are the Release lane's | This builds what needs nothing more from the Maintainer |

## Why

Decision 0086 made resolving a Lens's thread the Kernel's act, through the one App that may, and held the act unbuilt until each landed resolution could be counted. The count is now read from the run records, as an approval's is, so the step can land resolutions without any going uncounted.

## Boundaries

| Boundary | Check |
|---|---|
| Each landed resolution since a writer last acted, in its second too, counts toward the act ceiling, for every act; one that did not land, one before the writer, or another Intent's counts nothing; one running holds the item | `tests/test_decide.py::test_each_landed_resolution_counts_toward_the_act_ceiling` |
| A landed resolution is outside the Run ceiling, and one that did not land is inside it; a resolution failing for the item meets its attempts; each for the resolve act as for an approval | `tests/test_decide.py::test_each_landed_resolution_counts_toward_the_act_ceiling` |
| The records port reads Intent `resolve-thread` as a pull request's Run, which asks for no contract | `tests/test_adapters.py::test_every_intent_a_lifecycle_runs_is_ruled_on_whether_it_asks_for_a_contract` |
| The queue App's grant holds each of its writes, and the resolve act is no Role's; a write no App holds is refused, one that waits is not | `tests/test_tools.py::test_a_write_need_no_app_holds_is_caught`, `tests/test_apply.py::test_no_role_write_resolves_a_thread` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
