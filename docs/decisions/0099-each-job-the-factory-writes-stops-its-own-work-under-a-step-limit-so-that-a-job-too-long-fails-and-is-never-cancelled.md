# 0099. Each job the Factory writes stops its own work under a step limit, so that a job too long fails and is never cancelled

Status: accepted. The orchestrator's ruling (a) of 2026-10-29 on issue 388, "A job stopped at its timeout concludes cancelled, so neither a required check nor a Run reads it as timed_out", once its trial read `failure`. The Maintainer may overturn it in review. It builds on `docs/decisions/0091-a-job-stopped-at-its-timeout-concludes-cancelled-a-steps-own-timeout-fails-and-coderabbit-with-auto-approval-off-does-not-approve.md`, whose fixtures it rests on.

## Decision

| What | Decided | Because |
|---|---|---|
| What a job too long concludes | Each job the Factory writes stops its own work first: each `run:` step sets its own `timeout-minutes`, and the `run:` steps of a job are given together at most the job's minutes less two, the margin its other steps keep. A step past its limit then concludes `failure`, and its job and check run with it, before GitHub stops the job | GitHub concludes a job it stops at its own `timeout-minutes` `cancelled`, and its check run and run with it, never `timed_out` (`trials/P-42.json`). A required check `cancelled` is read as giving no verdict, and needs the Maintainer; a Run `cancelled` with no outcome is no attempt. A step stopped at its own limit concludes `failure`, its job with it, and a later `if: always()` step still runs (`trials/P-42.step-timeout.json`): `failure` is what the Kernel reads as a failing check and as an attempt |
| Which jobs | Every job with steps in every workflow here: the Run's and the approving act's, the pass, each Lens the Factory runs, the eval gate, the release job and the secret scan. A `uses:` step needs no limit of its own | The rule is the workflows', not one Role's: any required check stopped at its job's timeout would land on the Maintainer. A `uses:` step does no work of the Factory's; its job's limit still ends it |
| Who holds it | `tools/check_workflows.py`'s `timeout` rule, on every workflow, and each workflow's own shape check, which now allows a `run:` step its `timeout-minutes` and nothing more. `continue-on-error`, which turns a step's timeout into `success`, was refused already | A rule is held by a check, and a counter-example breaks it alone |
| The limits | The margin is two minutes: in 116 jobs of the required checks' runs to 2026-10-29, the set-up, `uses:` and post steps took at most 8 s together. Each job's limit is unchanged but the checks job's, 25 to 28 minutes, whose `make verify` took up to 23: its step has 26. The eval job keeps its 120 minutes and its `BUDGET`, no case started past 110 minutes of the plan; its run step has 110, which its cases end within, since the plan, the fetch and the install go before it. The Run's Engine step has 20 of 30, beyond the longest tier's 900 seconds and its two reads of the CLI's version | A limit below what the step needs would fail work that was going to finish, and a margin too small would let the job's own timeout cut a step first |
| What the Kernel reads | Unchanged: `failure` and `timed_out` stay failing checks, and a Run that ran and concluded either with no outcome stays an attempt (decision 0049). Nothing GitHub sends for a job is `timed_out`, but a check run another App posts may be | No code reads text; only the conclusions change, and the Kernel reads them already |
| The simulator | A killed Run concludes `failure`, its outcome left or not, or now and then `cancelled` with none: never `timed_out`. Its rule, `a_run_past_its_limit_fails`, is asked by P-18 and stays unverified until P-18 has a fixture, since P-42's row asks of a required check | A rule is grounded only by a trial whose row asks it |

## Why

P-42 failed on `timed_out` alone: a job GitHub stopped at its timeout concluded `cancelled`. The ruling chose to have each job stop itself, if a step's own timeout concluded `failure`, which its trial showed it does. A Lens that runs too long is then a failing check that goes back to the author, and a Run that runs too long an attempt the attempts bound counts, not a Hold for the Maintainer or a Run only the ceiling stops.

## Boundaries

| Boundary | Check |
|---|---|
| Each `run:` step has its own `timeout-minutes`, and a job's `run:` steps together at most its minutes less `MARGIN`, two; a `uses:` step needs none | `tests/test_tools.py::test_each_run_step_stops_under_a_limit_of_its_own_below_its_jobs`, `examples/workflows/invalid/timeout.a-run-step-with-no-limit-of-its-own.yml`, `examples/workflows/invalid/timeout.a-step-limit-that-leaves-no-margin.yml` |
| Every workflow here holds to it | `tests/test_tools.py::test_the_example_passes_and_every_rule_has_been_tripped` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
