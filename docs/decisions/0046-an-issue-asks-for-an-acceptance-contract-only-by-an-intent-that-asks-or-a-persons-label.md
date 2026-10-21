# 0046. An issue asks for an acceptance contract only by an Intent that asks, or a person's `factory:contract` label

Status: accepted. The Maintainer's rule of 2026-10-21, adopted on "Facts port: one snapshot of a pull request from GitHub, with its completeness flags" (issue 191), and built for "Facts port: an issue asks for an acceptance contract only by its Intent or a person's factory:contract label; acceptance read whole when none asks" (issue 290). It adds to `docs/decisions/0025-acceptance-is-read-from-its-reporter-against-the-contract-a-person-approved.md`, whose contract is read from the issue a pull request closes, and says when that issue asks for one.

## Decision

| What | Decided | Because |
|---|---|---|
| When an issue asks for a contract | Only when its item's Intent is one that asks, `fix` or `implement`, or when a person adds the `factory:contract` label (`kernel/terms.py`) to it. The label is read as the Kernel reads a control label (`standing_labels`): it binds from when it is added until a person removes it, so what a person placed only a person ends (L-17), and a removal in the same second reads as placed. It asks only where a person, with write access and no App acting for it, placed it. The labels GitHub lists on the issue must agree with its timeline | A contract is a person's statement of what done means; no rule said when one is owed, so every pull request deferred on a contract that could never be read |
| Slice 1 | No Lifecycle runs an Intent named `fix` or `implement`: `fix-findings` fixes a pull request's Findings, not an issue's item. Every Intent a Lifecycle runs is named in a test, so a new one is ruled on before it runs | The first approval must not wait on a contract no story in slice 1 writes |
| A pull request that closes no issue, or whose issues none ask | `acceptance` is null, read whole | Nothing asked for a contract, so there is none to read |
| An issue that asks | The contract is read; until the part of the port that reads it is built, the read is not whole, and the Kernel defers | A contract asked for and not read is never read as no contract |
| What is not whole | A list of closing references longer than its page, one of another repo, one named twice, an issue whose labels are more than a page or disagree with its timeline, an issue's timeline read short, and a pull request to a base other than the default branch, which carries no closing reference (P-33) | A read that cannot say every issue was read cannot say none asked |
| The known limit | The closing references are the pull request's own, which its author writes: an author who removes "Closes" before a pass removes the ask. Binding a pull request to its issue by its Run record or its branch, never its body, is "Acceptance: a pull request is bound to the issue it serves by its Run or branch, not by its author's closing link" (issue 295) | The rule says when an issue asks; which issue a pull request answers to is its author's to say until a Run opens the pull request itself |

## Why

Design sections 3.13 and 4.8 make the acceptance contract the item's, read from the issue the pull request closes, but say only that the Kernel reads `acceptance` null "when the issue the pull request closes asks for none". Without a rule for asking, the port could never read `acceptance` whole, and the Kernel, rightly, deferred on every pull request. The label is a person's act on the issue, read by account and never by name (decision 0005); the Intents are the ones whose work a contract describes.

## Boundaries

| Boundary | Check |
|---|---|
| An issue asks only by the `factory:contract` label a person placed, which only a person ends; none asks, and `acceptance` is null and whole; one asks, and it is not whole | `tests/test_adapters.py::test_an_issue_asks_for_a_contract_only_by_a_persons_label` |
| An issue whose labels disagree with its timeline, or whose timeline is short, is not whole | `tests/test_adapters.py::test_an_issue_whose_labels_and_timeline_disagree_or_are_short_is_not_whole` |
| Closing references read short, of another repo, or named twice are not whole | `tests/test_adapters.py::test_closing_references_are_whole_only_of_this_repo_and_every_one_counted` |
| A pull request to another base than the default is not whole on its contract | `tests/test_adapters.py::test_a_pull_request_to_another_base_than_the_default_is_not_read_whole_on_its_contract` |
| Every Intent a Lifecycle runs is ruled on whether it asks | `tests/test_adapters.py::test_every_intent_a_lifecycle_runs_is_ruled_on_whether_it_asks_for_a_contract` |
| A snapshot reads `complete.acceptance` true where no closing issue asks, and false where one does | `tests/test_adapters.py::test_a_snapshot_holds_every_part_of_the_facts_and_the_title_beside_them`, `tests/test_adapters.py::test_a_snapshot_whose_closing_issue_asks_for_a_contract_is_not_read_whole_on_it` |
| A pull request is bound to the issue it serves by its Run or branch, not by its author's closing link | waiting on `adapters/binding.py` |
| The contract asked for is read | waiting on `adapters/contract.py` |
