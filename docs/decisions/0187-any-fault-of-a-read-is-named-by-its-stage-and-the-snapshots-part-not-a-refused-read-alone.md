# 0187. Any fault of a read is named by its stage and the snapshot's part, not a refused read alone

Status: accepted. The Factory Builder's ruling of 2026-11-10, after slice 1's fifth and sixth dry runs, on pull request 688, "AGENTS.md: say what is built; drop the model claim no check holds", stopped in the approving act with one code, `facts_unreadable`, the sixth after the Maintainer had widened the machine user's token. It amends 0179's rows "The code", "The stages" and "The parts".

## Decision

| What | Decided | Because |
|---|---|---|
| The fault | Any fault a read raises is told its stage, and a snapshot's its part: a read GitHub did not answer, as 0179 held, and a fault of the read's own code, such as an answer an adapter did not expect. `staged` in `harness/shared.py` and `snapshot` in `adapters/facts.py` tell it | The approving act records every fault of the read again as the environment's, so that no Run dies with no outcome (`harness/approve.py`). A fault it could not name was one no log could find: the reader fails loudly on such a fault, and the act hid it |
| The stages | The read again gains `context`: the context built from what the reads gave, which reads nothing itself | A fault there was no read's, and so no stage's |
| The parts | A sixteenth, `assembly`: the facts put together after the last read | A fault there would be named as the last read's, `unchanged` |
| A part not as its schema holds it | The approving act names a part of the item read again that is not as its schema holds it by the read that gave it, the first in the order they are read: `run_records_unreadable`; `snapshot_unreadable`, for the facts or the head; `context_unreadable`, for a context that is none; `pause_unreadable`, for a Pause that is no boolean, which the Pause's port hands back unread and never raises | One guard gave `facts_unreadable` for all of them, and the Pause's port raises nothing a stage could name |
| What stays | `facts_unreadable` is a fault no stage named. The reader stops by a code for a read GitHub did not answer alone, and fails as it did on any other fault. A Moved is told apart first, and given no part. The outcome's kind does not change, so no Decision moves | Only the reason's code is finer |

## Why

Two dry runs each spent a Release to learn that some part of the read again failed, and nothing more. The first guess, a grant the machine user's token lacked, was acted on, and the next run stopped at the same code. A step that catches every fault must say where each one was, or it turns a traceback into one word.

## Boundaries

| Boundary | Check |
|---|---|
| Any fault a stage raises is told its stage, the context's building among them | `tests/test_steps.py::test_the_item_is_read_again`, `harness/shared.py`, `harness/reread.py`; mutant: "a stage names a read GitHub refused and no other fault"; mutant: "the read again builds the context unnamed" |
| A snapshot names the part of any fault, and a fault in putting the facts together by a part of its own | `tests/test_adapters.py::test_a_snapshot_names_the_part_github_did_not_answer`, `adapters/facts.py`; mutant: "a snapshot names the part of a read GitHub refused and of no other fault"; mutant: "a snapshot names a fault in putting the facts together as the last read's" |
| The approving act records a fault's stage and part, and names a part not as its schema holds it by its read, the first as they are read | `tests/test_approve.py::test_each_fault_of_the_act_is_classed_as_the_design_classes_it`, `tests/test_steps.py::test_an_approving_run_finds_its_act_by_its_run_name_and_approves`, `harness/approve.py`; mutant: "the approving act names an unreadable Pause as no read's"; mutant: "the approving act names unreadable run records as no read's"; mutant: "the approving act names an unreadable snapshot as no read's"; mutant: "the approving act names a context that is none as no stage's"; mutant: "the approving act names the snapshot before the run records"; mutant: "the approving act names the Pause before the snapshot"; mutant: "the approving act reads a Pause of nought or one as read" |
