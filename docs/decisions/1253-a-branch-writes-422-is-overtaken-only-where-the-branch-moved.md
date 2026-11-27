# 1253. A branch write's 422 is overtaken only where the branch moved

Status: accepted. 2026-11-26, the Solution Architect; issue 838. Narrows decision 1225's `push_branch_moved` for a branch write, by name.

## Decision

A branch write that GitHub refuses with a 422 does not stop the push at once. `guards/push.py` permits one more read of the branch and judges by it:

- moved since the Decision, present where it admitted none or away from its head: `push_branch_moved`, the Run overtaken;
- still where the Decision admitted it: `push_answer_refused`, a person's, whatever GitHub's reason;
- no answer: `push_unanswered`, the port's, never overtaken; a 429, `push_rate_limited`.

No branch write leaves after a 422. So decision 1225's "a ref write refused as moved" holds only a write that the branch read again shows moved.

Limits: a branch moved and moved back between the write and the read reads as a refusal. GitHub's reason is never read. A branch rewound to an ancestor before the move takes it: REST has no compare-and-swap. A blob's and a submodule's names are GitHub's own, never read back.

## Why

GitHub's refs API answers 422 when the branch moved, and also when a ruleset or a protection refuses the write. Read as moved, such a rule on the work branches was overtaken on every pass, bounded only by the cost ceiling, and no person was called. Reading GitHub's message was rejected: no text from outside reaches a decision. The branch itself says which it was.

## Boundaries

| Boundary | Check |
|---|---|
| A 422, then the branch moved, gives `push_branch_moved` | `tests/test_guards.py::test_each_read_back_and_branch_write_says_whose_a_stop_is`, `guards/push.py`, mutant: "a branch write refused as stale is a refusal" |
| A 422, then the branch where the Decision admitted it, gives `push_answer_refused` | `tests/test_guards.py::test_each_read_back_and_branch_write_says_whose_a_stop_is`, `guards/push.py`, mutant: "every 422 on a branch write is moved" |
| A 422, then no answer, gives `push_unanswered` | `tests/test_guards.py::test_each_read_back_and_branch_write_says_whose_a_stop_is`, `guards/push.py`, mutant: "no answer after a 422 is read as the branch" |
| No branch write leaves after a 422 | `tests/test_guards.py::test_each_read_back_and_branch_write_says_whose_a_stop_is`, `guards/push.py`, mutant: "a branch is made again after a 422" |
