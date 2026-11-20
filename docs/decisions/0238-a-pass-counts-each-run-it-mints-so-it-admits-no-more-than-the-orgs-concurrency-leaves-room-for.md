# 0238. A pass counts each Run it mints, so it admits no more than the org's concurrency leaves room for

Status: accepted. The Factory Builder's ruling of 2026-11-20, after the first review Runs under the Release cut that day all ended `not_admitted` at their `apply`: of the two fixes the diagnosis named, the pass-side count, not the apply-side widening. It adds to decision 0039, which has the pass record hold what the Kernel was given; the rest of 0039 stands.

## Decision

| What | Decided | Because |
|---|---|---|
| The gap | The pass built one context, and asked the Kernel about every item with it: its `active_runs` was the count read from the records port's list before any item was asked. So one pass could admit any number of Runs, each against the same count, however many it had admitted before. Each Run's `apply` asks the Kernel again with only its own Run left out, and finds the others the same pass admitted active beside it: at `org_max_active_runs` or more of them it defers on `concurrency`, and `apply` ends the Run `not_admitted` | Pass `p_2KAMC4FTKGNX4C3GSMN2` of 2026-11-20 admitted seven review Runs; every one that reached its `apply` while four others ran ended `not_admitted`. The cut that moved every open pull request's content id made the burst, and while five or more items wanted a Run at once nothing would have cleared it |
| The count | Each item is asked with the context's `active_runs` and each Run the pass minted before it, the pull requests first and then the issues, in the order the record holds them. A minted Run is any the pass dispatches: an admission, an approval, or a queue act once its workflow is named, each of which the records port lists as active once dispatched. So the pass admits no more Runs than `org_max_active_runs` minus `active_runs`, and each item after that defers on `concurrency` | The Runs a pass dispatches are counted against the limit as the Runs before it are, so a Run, asked again at its `apply`, finds no more beside it than the limit allowed |
| A count that is not whole | A context whose `active_runs` is not a whole number, null for a list read short, stays as read for every item, and the Kernel defers each on it, as before | No count is made up from one that could not be read |
| The record | Each `pass/1` entry, a pull request's or an issue's, holds `active_runs`: the count its Decision was made with. A replay asks the Kernel with the record's context and that count in place of the context's (`controller.pass_.given`). The context keeps the count read from the list | Decision 0039: the record holds what the Kernel was given, and replays every Decision |
| A record from before | The entry's `active_runs` is optional in the schema: a record written before this one holds none, and each of its entries was asked with the context's count, which `given` reads for it | Pass records before are read by every later pass; they stay valid |
| Not changed | The Kernel, `apply`'s check and `org_max_active_runs` are as they were. A Run's `apply` still asks again with its own Run left out | The Builder's ruling: the pass-side fix, not a widening of what `apply` admits |

## Why

The org's concurrency is a bound on Runs running at once, and the pass is the one place that admits them (decision 0003). Counting only the Runs it read, and none it minted, let one pass admit past the bound, and each Run then found the bound broken at its own `apply`. Counting each Run as it is minted keeps the bound where it is decided, and recording the count per entry keeps every Decision replayable.

## Boundaries

| Boundary | Check |
|---|---|
| Each item is asked with the context's count of active Runs and each Run the pass minted before it, the issues after the pull requests; past the limit each item defers on `concurrency`; a count that is not whole stays as read; each entry holds its count, and replays by it; an entry with none replays by the context's; an entry's count is never below zero | `tests/test_controller.py::test_a_pass_admits_no_more_runs_than_the_orgs_concurrency_leaves_room_for`, `tests/test_controller.py::test_the_pass_record_holds_what_the_kernel_was_given_and_replays_it`, `tests/test_tools.py::test_the_example_pass_record_replays`, `tools/check_examples.py`, `examples/invalid/pass.an-entrys-count-of-active-runs-below-zero.json`, `controller/pass_.py`, mutant: "a pass counts no Run it minted", mutant: "an entry holds the context's count", mutant: "a replay is given the context's count" |
