# NNNN. The simulator's world dates an approval by the act's Run that read the description, and the Kernel's anchor takes the records always

Status: accepted. The Factory Builder's story of 2026-11-08, issue 608, "The simulator's world reads the description's anchor from the act's Run, and the Kernel's default goes", on the ruling of 2026-11-07 that decision 0158 records. It amends 0158's row "The simulator" and its boundary row for an approval measured with no records given.

## Decision

| What | Decided | Because |
|---|---|---|
| The world's anchor | `sim/world.py`'s `edited_since_approval` dates each machine approval by `read_at`, in the world's own words. That is the start of the latest approving act's Run on its content that started no later than it. Failing that, it is the approval's own time where a run of the item started no later. Failing that, it is before every time | It is how `kernel/derive.py`'s `approval_anchor` dates one (decision 0158), so the world's merge objects to an edit exactly where the Kernel holds it |
| The Kernel's records | `description_anchor` takes `runs` by name with no default, and `approval_anchor` has no branch for records not given. Each caller gives the records, an empty list included | The default measured each approval from its own time, the anchoring 0158 rules out. It was kept only for the world's test, which now gives the world's records |
| The world's own runs | The world's act starts in its approval's own second, so every seed reads as before | Nothing the simulator checks moves |

## Why

Decision 0158 kept the default because the world, whose act's Run starts in its approval's own second, read the old anchor. That kept a reading the ruling rules out alive in the Kernel for one caller. Giving the world the Kernel's reading, from its own records, lets the default go.

## Boundaries

| Boundary | Check |
|---|---|
| The world's reading of an edit after the approval is the Kernel's from the same reviews and records: an act that started before the approval reaches back; the latest act on its content counts, and no Run of another intent or content does; with no act, a Run as old as the approval dates it at its own time, and with none, before every time | `tests/test_simulator.py::test_the_worlds_reading_of_an_edit_after_the_approval_is_the_kernels`, `sim/world.py`, mutant: "the world dates a machine approval by its own time", mutant: "the world takes the earliest act", mutant: "the world takes any Run as the act", mutant: "the world takes an act on other content", mutant: "the world takes an act that started after the approval", mutant: "the world dates an approval no record is as old as at its own time", mutant: "the world dates each approval by its own time still" |
| `derive` gives the anchor this item's records | `tests/test_decide.py::test_an_approval_is_anchored_at_the_act_that_read_the_description`, `kernel/derive.py`, mutant: "derive reads the description's anchor without the records", mutant: "another item's records reach back before an approval" |
