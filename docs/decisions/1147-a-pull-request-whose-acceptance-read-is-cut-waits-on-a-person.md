# 1147. A pull request whose acceptance read is cut waits on a person

Status: accepted. Extends decision 0234 with its rule for a pull request's acceptance read, as "adapters: bound the acceptance port's issue timeline read to ten pages" (issue 986) asks, part 1 of 2: the Kernel's rule and the fact it reads, as the Factory Builder ruled on 2026-11-20 (A, the fact optional, absent read as not cut). The port bounds the read in part 2. Decision 0234 stands as it is.

## Decision

| What | Decided | Because |
|---|---|---|
| A cut acceptance read | `acceptance_bounded` in `facts/1` says the acceptance port cut the timeline of an issue the pull request closes, or that its branch binds it to, at its bound. The port gives it in every snapshot, false until it bounds that read, in the part after this one. Facts without it, read before it or an eval set's, read as not cut, and a value that is no truth value is a gap in acceptance. The Kernel defers a pull request so cut on its own code, `acceptance_bounded`, before any list read short and whatever `complete.acceptance` claims, and calls a person; a queued one is taken out, as for any read short | Read short and said no more, the pull request would wait in silence on a read that more comments never mend, and anyone can comment (the Claude and security reads of the bound, the Factory Builder's ruling (A) of 2026-11-20) |

## Why

Decision 0234 bounds the issues port's reads. The acceptance port reads the timeline of each issue a pull request closes with no bound, and anyone can comment on an issue. A bound alone would leave the pull request read short at every pass, waiting in silence; so a cut read gets its own code and calls a person, as an issue's cut timeline does.

## Boundaries

| Boundary | Check |
|---|---|
| The pull request's Kernel defers a pull request whose acceptance read was cut, `acceptance_bounded`, before any list read short and whatever `complete.acceptance` claims, calls a person, and takes it out of the queue; not cut, or absent, its read short defers as `facts_incomplete`, calling no one, and read whole it converges; a flag present but no truth value is a gap in acceptance; a merged or closed one is what it is. The snapshot always says it; a value in words is no fact | `tests/test_decide.py::test_an_acceptance_read_cut_at_its_bound_defers_on_its_own_code_and_calls_a_person`, `tests/test_adapters.py::test_a_snapshot_says_whether_its_acceptance_read_was_cut`, `examples/invalid/facts.a-cut-acceptance-in-words.json`, `kernel/derive.py`, `kernel/decide.py`, `adapters/facts.py`, mutant: "a cut acceptance read calls no one", mutant: "a cut acceptance read defers as any read short", mutant: "a cut acceptance read is read after the lists read short", mutant: "a cut acceptance read names no evidence", mutant: "any truthy flag is a cut acceptance read", mutant: "a cut flag that is no truth value is read as not cut", mutant: "an absent cut flag is a gap", mutant: "the snapshot leaves out whether the acceptance read was cut" |
