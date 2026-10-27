# 0073. The release step reads its facts and the eval gate through the release App's token, writes each tag and reads it back

Status: accepted. PR 2a of "Release: cut an immutable tag, move next, and roll back in one action" (issue 197), under
its rulings 4′, 4″ and 5′ and the orchestrator's split of 2026-10-26. It builds the live side of `release/move.py`, which
decision 0071 left to plan alone, and leaves decision 0071 as it is.

## Decision

| What | Decided | Because |
|---|---|---|
| The step | `python3 -m release.move` with no argument is the release job's one step: it takes its inputs from the job's environment and the release App's token, reads the factory/ tags, plans by `release/cut.py`, sends each write, reads the tags again after it, and records each move of `next` as a Deployment on `factory-next`. It prints codes alone, and exits 1 by the code that stopped it | Ruling 4′: every step but the mint and the checkout is `python3 -m release.move`; a workflow's run line is a module and nothing else |
| The cut's commit | Named `RELEASE_CUT_COMMIT`, never `RELEASE_COMMIT`, which is the Run's own checkout | One term, one meaning |
| A commit's facts | `adapters/candidate.py`: on `main` by GitHub's comparison of the commit with `main`'s head, read by its branch's ref, never a name a tag could share; `verify` as GitHub Actions' one success on the commit; and the eval gate. Each fails closed | Ruling 4: the cut's rules read these, and a fact not read is no fact |
| The eval gate | The eval job's one successful dispatch on the commit, its `eval-report` artifact read within `STORED`, and the set's manifest at that commit read through the transport, judged by `harness.eval.verdict` for the Release asked. Anything not read whole, deep JSON included, closes it, which `cut.plan` reads as `eval_gate_closed` | Ruling 4″; nothing of the commit is executed to judge it |
| The writes | `adapters/tags.py`'s `write`: a Release created, never one that exists; `next` created once and moved with `force` after; `stable` and a Release are never moved. Each is read back, once more if need be, on its commit as the one Release planned, or the step stops there | Ruling 3 holds a Release immutable; a write is claimed only from what was read back |
| A rollback | Reads no fact of the commit it moves to | Ruling 5′: it works while the Factory is broken |
| A cut with no version | Is of the next patch of the Channel's major | The schedule's cut names none (ruling 4′) |

## Why

The first pull request of the story held the cut's rules pure and the plan alone; the workflow that runs the step is PR 2b's. Every answer GitHub
gives the step is held on replays here, since no release step can run before the App is registered and the eval set
holds cases.

## Boundaries

| Boundary | Check |
|---|---|
| The step sends each write, reads it back and records each move of `next` | `tests/test_release_step.py::test_a_cut_creates_the_release_moves_next_reads_each_back_and_records_the_deployment` |
| It stops at the first write refused or not read back as planned | `tests/test_release_step.py::test_a_write_not_read_back_stops_the_step_there` |
| The eval gate is closed by anything not read whole or not passed for the commit and Release | `tests/test_release_step.py::test_the_eval_gate_is_closed_by_anything_not_read_whole_or_not_passed` |
| `verify` counts only as GitHub Actions' one success on the commit | `tests/test_release_step.py::test_verify_counts_only_as_github_actions_one_success_on_the_commit` |
| A commit is on `main` only by comparison with `main`'s head, read by its ref | `tests/test_release_step.py::test_the_facts_of_a_commit_on_main_verified_and_judged` |
| A move forward is gated for the Release it moves to; a rollback reads no fact | `tests/test_release_step.py::test_a_move_forward_reads_the_facts_of_the_release_it_moves_to`, `tests/test_release_step.py::test_a_rollback_reads_no_fact_and_moves_next_back` |
| A Release is never written twice; `next` alone is moved, with force | `tests/test_release_step.py::test_a_release_is_created_and_a_channel_created_once_then_moved_with_force` |
| A Deployment counts only of the commit moved to, its status success | `tests/test_release_step.py::test_a_deployment_of_next_is_recorded_with_its_status` |
| The step prints codes alone; a step that cannot be read asks nothing | `tests/test_release_step.py::test_the_step_prints_codes_alone_and_exits_by_them`, `tests/test_release_step.py::test_a_step_that_cannot_be_read_asks_nothing` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
