# 9999. A push reads its tree whole within a bound, and each code has an owner

Status: accepted. 2026-11-25, the Solution Architect; issue 838. Extends the patch guard's record and decision 0188.

## Decision

The push port reads the tree a patch lands on in three steps: the listing (`listed`), the files to read (`to_read`) and their bytes (`read_whole`). Each step gives everything or a code, and nothing is cut short. All three are in `adapters/push.py`.

| Code | Whose |
|---|---|
| `push_reads_too_large`: more than 1,000 files, or 64 MiB in all, by the listing or by the bytes read | the Role's attempt |
| `push_tree_unreadable`: a listing GitHub truncated, or one in no shape; a file over the blob API's 100 MB; a blob GitHub refused or answered with other bytes | a person's Hold |
| `push_tree_unfetched`: no answer, a 5xx, or a 403 or 429 | the port's, an environment fault |

`WHOSE` names the owner of every code of the guard and of the port, with no default. A person's code waits on a Kernel Hold, a pull request of its own, merged before the Harness's push step calls the guard. That step's hand pull request may not map a person's code to any existing outcome fault.

Limits: a 403 is read as a rate limit or a missing grant, never as a blob refused for good.

## Why

A patch could name enough files to exhaust a Run, and a partial read would let the guard judge a tree it never saw whole. A file the API never returns fails every attempt the same way. Counted as the environment's, one such file would pause the Factory. Counted as the Role's, it would spend attempts that cannot succeed. So it holds the item for a person.

## Boundaries

| Boundary | Check |
|---|---|
| A listing is taken whole: none cut short, of another tree, or of an entry not read here | `tests/test_adapters.py::test_a_trees_listing_is_taken_whole_or_not_at_all`, `adapters/push.py`, mutant: "a listing GitHub cut short is taken" |
| Past 1,000 files or 64 MiB the read is the Role's attempt; a blob the API never gives is a person's | `tests/test_adapters.py::test_a_push_reads_whole_within_its_bound_and_past_it_is_the_roles_attempt`, `adapters/push.py`, mutant: "one file more than the bound is read" |
| Every code of the guard and the port names its owner, and a read in no shape is a person's | `tests/test_adapters.py::test_every_code_of_the_patch_guard_and_the_port_names_whose_it_is`, `adapters/push.py`, mutant: "a read in no shape is the Role's attempt" |
