# 0206. The required check's pull-request run gives way to a newer push's, and a merge group's run is never cancelled

Status: accepted. The Factory Builder's rulings of 2026-11-09 and 2026-11-13 on issue 681, a Lens's cancelled run beside a later one on the same head: its plan's step 4, the cancel of a pull request's run a newer push outdates, with the points of the Claude review of "CI: a newer push cancels its pull request's verify run, and a merge group's run is never cancelled" (pull request 679). It amends decision 0014's row "A concurrency group on CI", where it says none on the required check; the rest of the row stands.

## Decision

| What | Decided | Because |
|---|---|---|
| The group | `.github/workflows/verify.yml` has one top-level concurrency: its group `${{ format('factory-pr-{0}', github.event.pull_request.number \|\| github.run_id) }}` and its `cancel-in-progress` `${{ github.event_name == 'pull_request' }}`. A pull request's run gives way to the run a newer push to the same pull request starts | On 2026-11-09, 13 of a day's 47 pull-request runs ran on after a newer push: about 870 runner-minutes, 14% of that day's pull-request runner time, on the Free plan's 20 runners |
| A merge group's run | Never cancelled, and it cancels nothing: its group is its own run's id, unlike any other's | A cancelled merge group's run would eject its entries from the queue |
| Why 0014's reason no longer forbids it | 0014 kept the required check out of any group because a group evicts a waiting run, which once lost work (`docs/lessons.md`, "A request existed only as a queued run"). A pull request's run is no request: the run a newer push starts judges the newer head, and what is evicted judged content no longer the head. Each Run's lane keeps its own group, which never cancels the Run in progress | The lesson stands for every workflow that carries a request |
| The cancelled run's check | A cancelled run's `verify` concludes `failure` under `if: always()`, its suite `cancelled` (`trials/P-65.json`). On the head it ran on, beside a later run of the file, it is passed over (decision 0203); on an older head nothing reads it | Step 3 lands first, so the cancel cannot fail a Lens on content a later run passed |
| Only the required check's workflow | `tools/check_workflows.py` allows the two expressions in `.github/workflows/verify.yml`'s top-level concurrency alone, and names them in its rule `expression`; in any other workflow each is an expression where text from outside could stand | The Claude review of "CI: a newer push cancels its pull request's verify run, and a merge group's run is never cancelled" (pull request 679) |
| What remains | The secret scan's `.github/workflows/ci.yml` has no group, so its superseded runs still run to the end. A person's cancel, a reopening and a re-run of an older run on the same head each leave a cancelled run beside a later one, which decision 0203 reads | Named; the secret scan's runs take under a minute |

## Why

Decision 0014 kept the required check out of any concurrency group for a reason that holds for a request and not for a
pull request's run. Once decision 0203 reads a cancelled run beside a later one, the run a newer push outdates can give
way, and only the merge group's run, which the queue needs whole, is kept out of every group but its own.

## Boundaries

| Boundary | Check |
|---|---|
| The required check's workflow holds that concurrency, or none, and no other; a merge group's run is never cancelled nor cancels another's; the two expressions stand there alone, and in any other workflow are refused | `tests/test_tools.py::test_only_a_superseded_pull_request_run_is_cancelled`, `tests/test_tools.py::test_a_rule_with_no_counter_example_is_caught`, `tools/check_workflows.py`, mutant: "the required check's concurrency may be anything", mutant: "a pull request's lane is no expression the check allows", mutant: "any top-level concurrency expression is allowed", mutant: "a pull request's lane stands in any workflow", mutant: "the required check's workflow is linted as any other" |
