# 9999. A stopped push names its code, and each code says whose it is

Status: accepted. 2026-11-26, the Solution Architect; issue 838. Extends decision 1221 and the push port's `WHOSE` (pull request 1222).

## Decision

`guards/push.py` gives a code wherever it stops, never None alone, and sets each code itself: one for each class of stop. This pull request sets the first; later parts set the rest.

| Code | When | Whose |
|---|---|---|
| `push_not_permitted` | A push told wrongly, changes in no shape `applied` gives, or a request not permitted next | A person's: the Factory described its own push wrongly |
| `push_branch_moved` | The work branch is not where the Decision admitted it, or a ref write is refused as moved | The fault `superseded`: the next pass derives afresh, with no attempt spent |
| `push_answer_refused` | A write's 4xx, or a read-back that is not what was made | A person's |
| `push_unanswered` | No answer to a write, or a 5xx | The port's, an environment fault |

Each input and key is held to its exact type, as in the patch guard. The state keeps a copy of what it was told. A file may become a directory, or a directory a file, as `applied` allows.

Once pull request 1222 is merged, `WHOSE` names each code here: this pull request adds its own if it merges second, else the follow-on that pins the push port's person code does. Push part 2's `seen` takes the port's accepted listing, refuses one not marked whole, and holds only the order, the commit and the branch.

Limits: until `WHOSE` holds a code, no test reads its owner. The cost ceiling alone bounds a branch that keeps moving.

## Why

A stop with no code leaves the Harness to guess whose it is, and a wrong guess spends attempts or pauses the Factory for nothing. One code for each step, mapped in the Harness's hand pull request, was rejected: the guard alone knows which step stopped.

## Boundaries

| Boundary | Check |
|---|---|
| A push told wrongly begins nothing and gives `push_not_permitted` | `tests/test_guards.py::test_a_push_is_told_whole_or_begins_nothing`, `guards/push.py`, mutant: "a push told wrongly gives no code" |
| Changes in no shape, or of a type that only looks right, give `push_not_permitted` | `tests/test_guards.py::test_a_pushs_changes_are_what_applied_gives_path_by_path`, `guards/push.py`, mutant: "changes may hold a key more, or one of another kind" |
| A key is held to its type before any key is compared, and the state keeps a copy | `tests/test_guards.py::test_a_push_is_told_whole_or_begins_nothing`, `guards/push.py`, mutant: "keys are compared before their type is held" |
