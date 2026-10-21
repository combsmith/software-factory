# 0046. An issue asks for an acceptance contract only by an Intent that asks, or a person's `factory:contract` label

Status: accepted. The Maintainer's rule of 2026-10-21, adopted on "Facts port: one snapshot of a pull request from GitHub, with its completeness flags" (issue 191), and built for "Facts port: an issue asks for an acceptance contract only by its Intent or a person's factory:contract label; acceptance read whole when none asks" (issue 290). It adds to `docs/decisions/0025-acceptance-is-read-from-its-reporter-against-the-contract-a-person-approved.md`, whose contract is read from the issue a pull request closes, and says when that issue asks for one.

## Decision

| What | Decided | Because |
|---|---|---|
| When an issue asks for a contract | Only when its item's Intent is one that asks, `fix` or `implement` (`kernel/terms.py`'s `CONTRACT_INTENTS`), or when a person adds the `factory:contract` label to it: the label as it stands after the issue's last event for it, a `labeled` by a person, never by an App or the machine user | A contract is a person's statement of what done means; no rule said when one is owed, so every pull request deferred on a contract that could never be read |
| Slice 1 | No Lifecycle runs an Intent that asks, so only the label asks; a test fails when such an Intent is added before the port reads an item's Intent | The first approval must not wait on a contract no story in slice 1 writes |
| A pull request that closes no issue, or whose issues none ask | `acceptance` is null, read whole | Nothing asked for a contract, so there is none to read |
| An issue that asks | The contract is read; until the part of the port that reads it is built, the read is not whole, and the Kernel defers | A contract asked for and not read is never read as no contract |
| What is not whole | A list of closing references longer than its page, one of another repo, one named twice, or an issue's timeline read short | A read that cannot say every issue was read cannot say none asked |

## Why

Design sections 3.13 and 4.8 make the acceptance contract the item's, read from the issue the pull request closes, but say only that the Kernel reads `acceptance` null "when the issue the pull request closes asks for none". Without a rule for asking, the port could never read `acceptance` whole, and the Kernel, rightly, deferred on every pull request. The label is a person's act on the issue, read by account and never by name (decision 0005); the Intents are the ones whose work a contract describes.

## Boundaries

| Boundary | Check |
|---|---|
| An issue asks only by the `factory:contract` label a person added, as it stands after its last event; none asks, and `acceptance` is null and whole; one asks, and it is not whole | `tests/test_adapters.py::test_an_issue_asks_for_a_contract_only_by_a_persons_label` |
| Closing references read short, of another repo, or named twice are not whole | `tests/test_adapters.py::test_closing_references_are_whole_only_of_this_repo_and_every_one_counted` |
| No Lifecycle runs an Intent that asks before the port reads an item's Intent | `tests/test_adapters.py::test_no_intent_that_asks_for_a_contract_runs_yet` |
| A snapshot whose pull request closes no issue that asks reads `complete.acceptance` true | `tests/test_adapters.py::test_a_snapshot_holds_every_part_of_the_facts_and_the_title_beside_them` |
| The contract asked for is read | waiting on `adapters/contract.py` |
