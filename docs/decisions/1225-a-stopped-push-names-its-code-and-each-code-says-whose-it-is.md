# 1225. A stopped push names its code, and each code says whose it is

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

The push port's `WHOSE` names each code as a part sets it: this pull request adds `push_not_permitted`. Push part 2's `seen` takes the port's accepted listing, refuses one not marked whole, and holds only the order, the commit and the branch.

Limits: until `WHOSE` holds a code, no test reads its owner. The cost ceiling alone bounds a branch that keeps moving.

## Why

A stop with no code leaves the Harness to guess whose it is, and a wrong guess spends attempts or pauses the Factory for nothing. One code for each step, mapped in the Harness's hand pull request, was rejected: the guard alone knows which step stopped.

## Boundaries

| Boundary | Check |
|---|---|
| A push told wrongly begins nothing and gives `push_not_permitted` | `tests/test_guards.py::test_a_push_is_told_whole_or_begins_nothing`, `guards/push.py`, mutant: "a push told wrongly gives no code" |
| Changes in no shape, or of a type that only looks right, give `push_not_permitted` | `tests/test_guards.py::test_a_pushs_changes_are_what_applied_gives_path_by_path`, `guards/push.py`, mutant: "changes may hold a key more, or one of another kind" |
| A key is held to its type before any key is compared, and the state keeps a copy | `tests/test_guards.py::test_a_push_is_told_whole_or_begins_nothing`, `guards/push.py`, mutant: "keys are compared before their type is held" |
| Each read leaves once and in order | `tests/test_guards.py::test_a_push_reads_its_branch_commit_tree_and_files_once_each_in_order`, `guards/push.py`, mutant: "the commit is read again" |
| A listing not marked whole, or read at another tree, gives `push_not_permitted` | `tests/test_guards.py::test_a_listing_the_port_did_not_mark_whole_or_read_at_another_tree_is_refused`, `guards/push.py`, mutant: "a listing of any tree is taken" |
| A read's branch moved gives `push_branch_moved`; no answer, a 5xx, 401, 429 or the branch's 403, `push_unanswered`; any other refusal, `push_answer_refused` | `tests/test_guards.py::test_each_read_says_whose_a_stop_is`, `guards/push.py`, mutant: "a branch gone is a refusal" |
| The admitted tree's files a push changes or removes are named for the rule on tests | `tests/test_guards.py::test_the_paths_apply_is_asked_about_are_the_paths_that_land`, `guards/push.py`, mutant: "a file the push adds is an existing one" |
| Nothing is written before the branch and the listing were read, and nothing is read once a write began | `tests/test_guards.py::test_nothing_is_written_before_the_branch_and_the_listing_were_read`, `guards/push.py`, mutant: "a write leaves before the listing is read" |
| A blob of each written content once, one name to each content | `tests/test_guards.py::test_a_blob_is_made_once_of_each_written_content`, `guards/push.py`, mutant: "a blob is made twice of one content" |
| One tree of exactly the changes, landing only what the admitted tree can hold | `tests/test_guards.py::test_the_one_tree_names_exactly_the_changes_by_the_blobs_made`, `guards/push.py`, mutant: "a push may write what the admitted tree cannot hold" |
| A write's 4xx gives `push_answer_refused`; no answer or a 5xx, `push_unanswered` | `tests/test_guards.py::test_each_write_says_whose_a_stop_is`, `guards/push.py`, mutant: "a write's 4xx is no answer" |
| The tree is read back, one commit of it made and read back, the branch written once and never by force, then read again | `tests/test_guards.py::test_a_push_lands_its_commit_and_branch_read_back`, `guards/push.py`, mutant: "a commit is made before its tree is read back" |
| A read back not of what was made gives `push_answer_refused`; a branch write refused as stale, or the branch read again elsewhere, `push_branch_moved` | `tests/test_guards.py::test_each_read_back_and_branch_write_says_whose_a_stop_is`, `guards/push.py`, mutant: "a branch write refused as stale is a refusal" |
