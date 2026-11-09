# 0177. A read GitHub did not answer is named by its stage and the snapshot's part, never by one code for every read

Status: accepted. The Factory Builder's ruling of 2026-11-09, after slice 1's dry run on pull request 688 stopped twice in the reader with one code, `facts_unreadable`, before any model call. It amends 0110's row "An issue's text, live", whose short read stopped the step as `facts_unreadable`: that read now stops as `issue_texts_unreadable`.

## Decision

| What | Decided | Because |
|---|---|---|
| The code | A read GitHub did not answer is named by the stage that made it, `<stage>_unreadable`, and a snapshot's by its part too, `snapshot_<part>_unreadable`, by `unread` in `harness/shared.py`. A read no stage names stays `facts_unreadable` | The dry run's two Runs said only that some read failed. Replayed as the Maintainer, all 34 answered, so the read is one the reader App's token is refused or the transport refuses, and only the Run can say which |
| The stages | The reader's: `release_refs`, `pass_record`, `run_records`, `lens_records`, `opened_records`, `snapshot`, `pull`, `change`, `issue_texts`. The read again's: `run_records`, `lens_records`, `opened_records`, `snapshot`, `pause` | One for each read a step makes, so no two reads share a code |
| The parts | `pull`, `base`, `push`, `diff`, `paths`, `timeline`, `reviews`, `writer`, `labels`, `checks`, `acceptance`, `threads`, `edits`, `unchanged`, `schema`, set by `adapters/facts.py` before each read starts | A snapshot is a dozen reads, and the timeline's is not the reviews' |
| A pull request that moved | The reader stops `pull_moved`; apply and the approving act keep `superseded`, `head_moved`. A Moved is given no part | It is a change under the Run, never the environment's, as 0172 reads it in the pass |
| Where a code goes | The reader prints it, a code and nothing else (`run` in `harness/steps.py`). Apply and the approving act record it as the outcome's reason, which `outcome/1` holds to `^[a-z_]+$`: so the part joins with `_` and never `:` | No text from GitHub reaches a log, a record or a Decision. Nothing reads a reason beyond the outcome's kind, so no Decision moves |

## Why

A fault the Factory cannot locate costs a Release to find. With one code for every read, the dry run could only be replayed from outside, and the replay could not stand in for the reader's own token. A code for each stage makes the next Run say which read it was, from its log alone.

## Boundaries

| Boundary | Check |
|---|---|
| The reader stops by the code of the read GitHub did not answer, a snapshot's with its part, a moved pull request apart, a read no stage names as `facts_unreadable` | `tests/test_steps.py::test_the_reader_fails_closed`, `harness/read.py`; mutant: "a pull request that moved is read as one not answered"; mutant: "the reader reads the issue texts unnamed"; mutant: "the reader names a read no stage named by no code" |
| A stage's code keeps the snapshot's part, and a read is told its stage | `tests/test_steps.py::test_the_reader_fails_closed`, `harness/shared.py`; mutant: "a stage's code drops the snapshot's part"; mutant: "a read is told no stage"; mutant: "a read no stage named is named one" |
| A snapshot names the part GitHub did not answer, each of its fifteen, and a Moved none | `tests/test_adapters.py::test_a_snapshot_names_the_part_github_did_not_answer`, `adapters/facts.py`; mutant: "a snapshot names no part GitHub did not answer"; mutant: "a snapshot names a writer's read as the reviews'"; mutant: "a pull request that moved is named a part" |
| The read again names each of its stages | `tests/test_steps.py::test_the_item_is_read_again`, `harness/reread.py`; mutant: "the read again names the opening Runs' records as the Lenses'"; mutant: "the read again reads the Pause unnamed" |
| Apply and the approving act record the stage's code | `tests/test_steps.py::test_apply_reads_with_reads`, `harness/apply_step.py`; mutant: "apply names no read it could not make" |
