# 0180. On a pull request the mutant shards decline, and on a merge group each runs in full

Status: accepted. The Factory Builder's ruling of 2026-11-09, pre-approved by the Maintainer 2026-11-08, on the measurement of the runners' throughput that followed the move to GitHub Team. It changes where `tools/mutants.py` runs in CI, as decision 0166 declines `tools/untested.py` on a merge group, and it amends decision 0008's "two commands, `make verify` and then `python3 -m tools.mutants`, run locally exactly what the required check runs": the desk runs `make checks` and the mutants of the files a change touches, and `make verify` and every shard are CI's.

## Decision

| What | Decided | Because |
|---|---|---|
| A pull request | `tools/mutants.py` declines on a pull request: it reads no shard and no mutant, says so, and exits 0, so each shard job passes in seconds | On 2026-11-09 the shards were 77% of the runner minutes, about three quarters of them on pull requests. In 94 pull-request runs they caught what the tests did not in 3, and 49 ran on a baseline already red. On the day before, the factory workflow's pull-request runs took 6,409 runner minutes, 84% of them in the shards |
| A merge group | Every shard runs in full, as before, so no merge reaches main without every mutant killed | The rule "every Kernel rule has a boundary test, and a mutant that the test kills" is held where the merge is made |
| What stays | The shard jobs still start on a pull request, so the matrix, `SHARD_KEYS`, `tools/needs_passed.py` and decision 0008's one required check are unchanged | A job that does not report would leave `verify` waiting or skipped |
| The event | Read from the runner's own `GITHUB_EVENT_NAME`. The shard job's env is held to `MUTANTS_SHARD` and `MUTANTS_SHARDS` alone, and a step's env is refused, so no workflow can set it otherwise | The workflow names no event, and its shape stays as `tools/check_workflows.py` holds it |
| The desk run | A builder still owes `make checks` and `python3 -m tools.mutants` on the files a change touches before a change is finished, but for a file more than 40 mutants target, which a filtered run refuses and the merge group runs, and no longer runs `make verify`, whose answer is CI's: AGENTS.md's Verify says so (the Maintainer, 2026-11-09) | The residual: what a pull request's shards would have caught, 3 runs in 94, is now found at the merge group, which ejects the entry, or at the desk |
| The cost | Runner minutes for each merged pull request, from the day to 2026-11-09 13:40Z: 521 before, about 236 after (the pull-request runs' 6,409 less their 5,359 in the shards, plus 0.4 a declining leg, with the merge groups' 2,970, over 18 merged) | Measured from the runs' jobs; the after is an estimate until a day of runs under this rule is read |

## Why

The shards cost most of the runners and caught little on a pull request that the merge group does not catch again. Declining them there keeps the gate where it holds a merge, and frees the runners for the merge queue.

## Boundaries

| Boundary | Check |
|---|---|
| On a pull request nothing runs and the run passes, a shard it cannot read included; on a merge group, and at a desk where no event is set, the shard runs; from the front door too | `tests/test_tools.py::test_on_a_pull_request_the_mutants_decline_and_on_a_merge_group_every_shard_runs`, `tools/mutants.py`, mutant: "mutants run in full on a pull request", mutant: "mutants decline on a merge group too", mutant: "a declined pull request fails" |
