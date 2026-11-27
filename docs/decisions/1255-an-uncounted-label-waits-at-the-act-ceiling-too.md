# 1255. An uncounted label waits at the act ceiling too

Status: accepted. 2026-11-26, the Solution Architect; issue 1251. Reverses one line of decision 1244, and narrows decision 0003: removing an uncounted label is not an act that stops work.

## Decision

Removing another App's label that does not count, `factory:ready` or `factory:triage`, is braked as any act. While the act count is spent or cannot be read, the removal waits. The issue then reads as it will once the label is removed, so the label starts nothing (`kernel/issue.py`, `_decide`, `_removed`). It admits no Run that would add that same label, such as a readiness Run beside another App's `factory:ready`: it defers on the brake's code (`_adds`). Under the Pause the removal is stopped as before, whether the count can be read or not.

A removal that stops work still passes the ceiling, as decision 0003 says: unmerged closes past their bound place their Hold.

This reverses the line of decision 1244 that read: "The act ceiling is not such a Hold. It never stops an act that stops work, so the label is still removed at that ceiling."

Limits: while the removal waits, the label stays on GitHub, where a tool reading raw labels may take it as counted. A Run the issue admits once the label is gone is admitted beside it, even with the count unread.

## Why

An issue held at the act ceiling in new read `new` for the pass that removed another App's label. Only a person may move an issue out of held. Bounding only the Hold the Run wanted was not enough. The removal still ran past the ceiling in triage and ready, and for `factory:triage` in new, and the issue world's I-8 allows only a Hold there. Bounding every act that stops work was rejected: the Factory must always be able to stop. Reading the label as never added was rejected: the readiness App's own label is its verdict, and a verdict would be asked for again.

## Boundaries

| Boundary | Check |
|---|---|
| At or past the act ceiling, in new, triage and ready, the removal waits and makes no act; one act below, it is removed | `tests/test_issue.py::test_an_uncounted_label_waits_at_the_act_ceiling`, `kernel/issue.py`, mutant: "an uncounted label is removed at the act ceiling" |
| With the act count unread the removal waits too | `tests/test_issue.py::test_an_uncounted_label_waits_at_the_act_ceiling`, `kernel/issue.py`, mutant: "an uncounted label is removed with the act count unread" |
| With the writer's time unread, the acts since it cannot be counted: the removal waits and the issue defers on that time | `tests/test_issue.py::test_a_waiting_label_with_the_writers_time_unread_defers`, `kernel/issue.py`, mutant: "a waiting label's removal counts acts since a writer's time unread" |
| Under the Pause alone the removal is stopped, as any act that stops work, on the label | `tests/test_issue.py::test_an_uncounted_label_waits_at_the_act_ceiling`, `kernel/issue.py`, mutant: "the Pause alone makes an uncounted label's removal wait" |
| While it waits the issue admits what it admits once the label is gone, but for a Run that adds it | `tests/test_issue.py::test_an_uncounted_label_waits_at_the_act_ceiling`, `kernel/issue.py`, mutant: "a waiting removal stops what the issue admits once the label is gone" |
| A waiting label reads as removed, not as never added, so no verdict is asked for again | `tests/test_issue.py::test_an_uncounted_label_waits_at_the_act_ceiling`, `kernel/issue.py`, mutant: "a waiting label is read as never added" |
| While the label waits, no Run that adds it is admitted; once it is removed, the Run is | `tests/test_issue.py::test_no_run_that_adds_a_waiting_label_is_admitted`, `kernel/issue.py`, mutant: "a Run that adds a waiting label is admitted" |
