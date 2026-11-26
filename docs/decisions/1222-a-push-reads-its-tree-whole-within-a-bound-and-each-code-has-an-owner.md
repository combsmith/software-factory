# 1222. A push reads its tree whole within a bound, and each code has an owner

Status: accepted. 2026-11-25, the Solution Architect; issue 838. Extends decisions 1221 and 0188.

## Decision

`adapters/push.py` reads the tree a patch lands on: its listing (`listed`), the files to read (`to_read`), their bytes (`read_whole`). Each gives everything or a code, never part. A listing must rebuild into the tree asked for, by git's names. Bytes are read in order, stopping at the first code. Where a person's code and the Role's both apply, the person's wins.

| Code | Whose |
|---|---|
| `push_reads_too_large`: more than 1,000 files, or 64 MiB in all, by the listing or by the bytes read | the Role's attempt |
| `push_tree_unreadable`: a listing truncated, in no shape or of another tree; a file too large for the transport's 64 MiB answer; a blob refused, a 403 among them, or of other bytes | a person's Hold |
| `push_tree_unfetched`: no answer, a 5xx, a 401 or 429, a 403 on the listing, or a rate limit's 403 | the port's, an environment fault |

`WHOSE` names every code's owner, with no default. A person's code waits on a Kernel Hold, its own pull request, merged before the Harness's push step calls the guard. That step's hand pull request may not map a person's code to any existing outcome fault.

A blob is read after its listing, by the same token, so a 403 on it alone will come again. `send` drops a rate limit's 403 as decision 1138 tells one.

Limits: a listing's 403 is the port's, wider than decision 1138's rate limit. Sizes are not in git's names, so bytes read are bounded again.

## Why

A patch could name enough files to exhaust a Run, and a partial read lets the guard judge a tree it never saw whole. A file never returned fails every attempt alike: as the environment's it would pause the Factory, as the Role's spend attempts that cannot succeed. So it holds the item for a person.

## Boundaries

| Boundary | Check |
|---|---|
| A listing is taken whole: none cut short, of another tree, missing an entry, or with one not read here | `tests/test_adapters.py::test_a_trees_listing_is_taken_whole_or_not_at_all`, `adapters/push.py`, mutant: "a listing GitHub cut short is taken" |
| Past 1,000 files or 64 MiB the read is the Role's attempt; a blob the transport never takes is a person's | `tests/test_adapters.py::test_a_push_reads_whole_within_its_bound_and_past_it_is_the_roles_attempt`, `adapters/push.py`, mutant: "one file more than the bound is read" |
| Every code of the guard and the port names its owner, and a read in no shape is a person's | `tests/test_adapters.py::test_every_code_of_the_patch_guard_and_the_port_names_whose_it_is`, `adapters/push.py`, mutant: "a read in no shape is the Role's attempt" |
| No answer, a 5xx, 401 or 429 is the port's; a blob's 403, a refusal or other bytes a person's; reading stops at the first code | `tests/test_adapters.py::test_a_push_reads_whole_within_its_bound_and_past_it_is_the_roles_attempt`, `adapters/push.py`, mutant: "a refused blob is the port's" |
| A rate limit's 403, with no request left or a time to wait, is no answer; any other 403 is an answer | `tests/test_adapters.py::test_a_rate_limits_403_is_no_answer_and_a_blobs_other_403_is_a_persons`, `adapters/push.py`, mutant: "a rate limit's 403 is an answer" |
