# 1222. A push reads its tree whole within a bound, and each code has an owner

Status: accepted. 2026-11-25, the Solution Architect; issue 838. Extends the patch guard's record and decision 0188.

## Decision

`adapters/push.py` reads the tree a patch lands on: its listing (`listed`), the files to read (`to_read`), their bytes (`read_whole`). Each gives everything or a code, never part. A listing must rebuild into the tree asked for, by git's names. Bytes are read in order, stopping at the first code.

| Code | Whose |
|---|---|
| `push_reads_too_large`: more than 1,000 files, or 64 MiB in all, by the listing or by the bytes read | the Role's attempt |
| `push_tree_unreadable`: a listing truncated, in no shape or of another tree; a file too large for the transport's 64 MiB answer; a blob refused or of other bytes | a person's Hold |
| `push_tree_unfetched`: no answer, a 5xx, or a 401, 403 or 429 | the port's, an environment fault |

`WHOSE` names the owner of every code of the guard and of the port, with no default. A person's code waits on a Kernel Hold, a pull request of its own, merged before the Harness's push step calls the guard. That step's hand pull request may not map a person's code to any existing outcome fault.

Limits: any 401 or 403 is the port's, wider than decision 1138's rate limit, since `send` drops headers. Sizes are not in git's names, so bytes read are bounded again.

## Why

A patch could name enough files to exhaust a Run, and a partial read lets the guard judge a tree it never saw whole. A file never returned fails every attempt alike: as the environment's it would pause the Factory, as the Role's spend attempts that cannot succeed. So it holds the item for a person.

## Boundaries

| Boundary | Check |
|---|---|
| A listing is taken whole: none cut short, of another tree, missing an entry, or with one not read here | `tests/test_adapters.py::test_a_trees_listing_is_taken_whole_or_not_at_all`, `adapters/push.py`, mutant: "a listing GitHub cut short is taken" |
| Past 1,000 files or 64 MiB the read is the Role's attempt; a blob the transport never takes is a person's | `tests/test_adapters.py::test_a_push_reads_whole_within_its_bound_and_past_it_is_the_roles_attempt`, `adapters/push.py`, mutant: "one file more than the bound is read" |
| Every code of the guard and the port names its owner, and a read in no shape is a person's | `tests/test_adapters.py::test_every_code_of_the_patch_guard_and_the_port_names_whose_it_is`, `adapters/push.py`, mutant: "a read in no shape is the Role's attempt" |
