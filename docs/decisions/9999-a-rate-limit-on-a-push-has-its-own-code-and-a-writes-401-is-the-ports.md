# 9999. A rate limit on a push has its own code, and a write's 401 is the port's

Status: accepted. 2026-11-26, the Solution Architect; issue 838. Narrows decision 1225's write 4xx and decision 1222's `push_tree_unfetched`, by name.

## Decision

`guards/push.py` gives `push_rate_limited` for a 429 on any read or write of a push. `adapters/push.py` gives it for a 429 on the listing or a blob. `WHOSE` names it the port's: no attempt of the item's, and no Hold. No owner names it capacity, so nothing maps it to the model's fault.

`send` reports a rate limit's 403, as decision 1138 tells one, as status "429". That status is the port's; GitHub sent a 403.

A write's 401, a token expired, is `push_unanswered`, the port's. Every other 4xx on a write stays `push_answer_refused`, a person's, a protection's 403 among them.

So decision 1225's "a write's 4xx" no longer holds a 401 or a 429, nor its reads' `push_unanswered` a 429. Decision 1222's `push_tree_unfetched` no longer holds a 429 or a rate limit's 403.

Limits: until a fault of its own lands, deferring only the Runs that push until GitHub's reset, a rate-limited push is run again, bounded only by the cost ceiling. A rate limit's 403 with neither header is read as any 403.

## Why

A rate limit is the same fact on a read and a write, and nothing on the item mends it: as a person's, it held the item for nothing. A code of its own lets a later fault take it by name. Mapping it to the model's capacity was rejected: one push would defer every model Run for five hours. A 401 is an answer, but a fresh token mends it.

## Boundaries

| Boundary | Check |
|---|---|
| A 429 on a read or a write gives `push_rate_limited` | `tests/test_guards.py::test_each_read_says_whose_a_stop_is`, `tests/test_guards.py::test_each_write_says_whose_a_stop_is`, `guards/push.py`, mutant: "a rate limit is no answer of its own" |
| A write's 401 gives `push_unanswered`; any other write 4xx, `push_answer_refused` | `tests/test_guards.py::test_each_write_says_whose_a_stop_is`, `guards/push.py`, mutant: "a write's 401 is a refusal" |
| `send` gives a rate limit's 403 as a 429 | `tests/test_adapters.py::test_a_rate_limits_403_is_no_answer_and_a_blobs_other_403_is_a_persons`, `adapters/push.py`, mutant: "a rate limit's 403 is an answer" |
| The listing's 429 is `push_rate_limited`, never a person's | `tests/test_adapters.py::test_a_trees_listing_is_taken_whole_or_not_at_all`, `adapters/push.py`, mutant: "a rate limit on the listing is a person's" |
| A blob's 429 is `push_rate_limited` | `tests/test_adapters.py::test_a_push_reads_whole_within_its_bound_and_past_it_is_the_roles_attempt`, `tests/test_adapters.py::test_a_rate_limits_403_is_no_answer_and_a_blobs_other_403_is_a_persons`, `adapters/push.py`, mutant: "a blob's 429 is a person's" |
| `push_rate_limited` is the port's in `WHOSE` | `tests/test_adapters.py::test_every_code_of_the_patch_guard_and_the_port_names_whose_it_is`, `adapters/push.py`, mutant: "a rate limit is a person's" |
