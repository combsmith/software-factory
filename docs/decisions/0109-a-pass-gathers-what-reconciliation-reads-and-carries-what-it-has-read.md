# 0109. A pass gathers what reconciliation reads, and carries what it has read

Status: accepted. The Factory Builder's rulings of 2026-10-31 on wiring the live pass, an item of the audit of "Epic: slice 1, first approval. A Release on next reviews a pull request to this repo, and the machine user's approval stands" (issue 182). It builds what `docs/decisions/0061-every-write-a-factory-identity-makes-is-matched-to-a-recorded-effect-and-one-that-is-not-raises-one-alert.md` left waiting on the pass's entry, and adds to it how a Run is read once.

## Decision

| What | Decided | Because |
|---|---|---|
| What the entry gathers | `controller/__main__.py` hands each snapshot a `kept`, and hands what it kept to `adapters/seen.py` for each open pull request, with each one the last record served that has left, read as left, and the machine user's pushes. It reads each snapshot's first answer for its date and age, as `facts_reads`. The window is a day and `not_run_seconds` back from the read | Every live pass read short before this, and raised `reconciliation_unreadable` |
| What it reads of what was recorded | Each completed Run the records port lists in the window has its `applied/1` read (`adapters/applied.py`'s `effects`), and each completed pass of the poller its `written/1` (`adapters/passes.py`'s `written`). One whose record cannot be read is not counted read, so a later pass reads it again, and reconciliation is short until then | A record any job could upload could cover a stolen credential's write, so only a listed Run is read (0061) |
| Read once | `pass/1` gains `reconciled`: the Runs and passes read, each Effect's key, each write matched by its item with its count, and each dispatch, each stamped with when it was read, dropped once older than the window. Reconciliation matches what this pass read and what the last record carried. A last record that cannot be read, or holds none, reads everything in the window again | 0061 says each is read once and its keys kept. A record keeps what the Effects said, not the records. Read each pass, a window of thirty hours costs about two reads for every pass and Run in it. It changes `pass/1`, never `facts/1`, so no held-out case moves |
| The accounts | `accounts.controller` and `roles.pr-review` are set to the bot accounts GitHub's users API answers, each with its login, id and type, recorded in `trials/P-39.accounts.json`. `tools/check_trials.py` lets the org's fixture read a Factory App's bot account by the one form its login takes, and no other account | Reconciliation is short while any writing identity's account is not known (0061), so the Controller's alone would not do |
| What setting them turns on | Tracking-issue writes (decision 0060), which wait on `accounts.controller`, and the Controller's acts are read as the Factory's. Nothing runs until the workflow that calls the pass exists | The Factory Builder's ruling |
| The comments read | Built regardless. Whether `pull_requests: read` serves a pull request's comments is still a trial's, and if GitHub refuses, every pass raises `reconciliation_unreadable`, which is loud and admits nothing wrongly | The Factory Builder's ruling |

## Why

Reconciliation was built and tested and nothing fed it, so the one alert that says a Factory identity wrote what it did not record could only ever say it could not read. This feeds it, at a cost that does not grow with the window.

## Boundaries

| Boundary | Check |
|---|---|
| The entry hands each snapshot's `kept` to the seen port, each item once, reads one that left as left, reads the pushes, and reads each facts read's date and age; what it cannot read is short, and fails no pass | `tests/test_controller.py::test_the_entry_gathers_what_reconciliation_reads` |
| A pass in the window is read once; one that lists no record is read; one that cannot be read is read again, and what was read stands; a list that cannot be read, or runs past its pages, is not whole | `tests/test_adapters.py::test_each_pass_in_the_window_is_read_once_and_what_cannot_be_read_is_read_again` |
| A listed Run in the window is read once; one running or older is not; one whose record cannot be read is read again; a list not whole reads nothing | `tests/test_adapters.py::test_each_run_in_the_window_is_read_once_and_only_a_listed_one` |
| What a pass read matches a write in the passes after it, for the window, a dequeue as many times as it was recorded | `tests/test_reconcile.py::test_what_a_pass_read_matches_a_write_in_the_passes_after_it_for_the_window` |
| What is older than the window is dropped, and matches nothing | `tests/test_reconcile.py::test_what_is_older_than_the_window_is_dropped_and_matches_nothing` |
| A record that holds none reads everything again; what cannot be read carries on what was held; `reconciled` is held to its shape | `tests/test_reconcile.py::test_a_record_that_holds_none_is_read_again_and_what_cannot_be_read_is_carried_on` |
| The accounts are what GitHub answered, and known | `tests/test_reconcile.py::test_each_identity_is_told_by_its_account_from_the_configuration` |
| A Factory App's bot account alone is the org's fixture's to read | `tests/test_tools.py::test_a_fixture_of_the_org_asks_by_rest_of_this_org_alone_and_climbs_nowhere` |
| The workflow that calls the pass runs it | waiting on `.github/workflows/poller.yml` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
