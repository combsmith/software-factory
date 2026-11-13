# 0220. A Lens's review that ends while a conflict waits at the Run ceiling holds the item, and the explorer reads a conflict at once

Status: accepted. The Factory Builder's ruling of 2026-11-13 on "The transitions explorer reads a conflict only two moves after a head that merges, and one move finds a Hold the Lifecycle does not declare" (issue 811): a real gap in the Lifecycle is declared, a ruled change. Trial P-40 found it ("Trial P-40: a move of the base alone makes GitHub work out mergeable again, for a pull request that still merges and for one the move makes conflict", issue 809), and record 0214 left it out by name.

## Decision

| What | Decided | Because |
|---|---|---|
| The Hold | `addressing -> held` by a Lens, bound `max_runs_per_item`, is declared in `lifecycle/pull_request.json`, beside the same Hold by the Factory and by the platform. An item at the Run ceiling with a review Run in flight reads `addressing` once a conflict is read. When the Lens's review passes, that Run has ended, and the conflict asks for a fix Run the ceiling forbids, so the item reads `held` with `run_ceiling`. The Lens's review is the change that gave the Hold, so the Lifecycle names the Lens as its maker | The Kernel made this Hold before this record, three moves deep: the base moves, GitHub works out it conflicts, a Lens's review passes. The explorer walks two, so nothing found it. The Hold is the Run ceiling's own, with the counter that bounds every lap of it, so the Lifecycle still terminates |
| The bound apart | No such Hold by a Lens at `max_environment_runs_per_item` | A Lens's review that passes spent model time and is never counted apart (decision 0202). Its ending leaves the bound apart where it was, so only a Factory Run that failed before its Engine step reaches it, and that Hold is declared |
| The explorer | `tests/test_transitions.py` gains the move "the base moves and GitHub works out at once that it conflicts": from a head that merges, straight to a conflict, and out of the queue, with no unknown between. The slow way, through unknown, stays | Within seconds of a base move a read can still give `mergeable` as it was, and a conflict is worked out within three (`trials/P-40.at-once.json`). So two passes a few seconds apart can read true and then false. With this one move, the explorer reads what follows a conflict |

## Why

Each Hold no person makes must name the counter that bounds it, or a cycle through it could run without end. This one was made and bounded, but not declared, because the explorer could not see that far. One move found it, as the issue showed. It is declared rather than changed: a review that ends at the ceiling, with a conflict to fix, has nothing left the Factory may do, which is what the ceiling's Hold means.

## Boundaries

| Boundary | Check |
|---|---|
| Every Hold no person makes is declared with its bound, the Run ceiling's Hold that a Lens's review makes from `addressing` among them; the explorer reads a conflict at once after a head that merges, reaches that Hold through it two moves deep, and gives the same readings the slow way through unknown | `tests/test_transitions.py::test_a_hold_no_person_makes_names_what_bounds_it`, `tests/test_transitions.py::test_a_conflict_worked_out_at_once_is_explored`, `lifecycle/pull_request.json`, `tools/mutants.py`, mutant: "the Run ceiling's Hold a Lens's review makes from addressing is undeclared" |
