# 9999. An uncounted label waits at the act ceiling too

Status: accepted. 2026-11-26, the Solution Architect; issue 1251. Reverses one line of decision 1244, which it extends.

## Decision

The act ceiling's Hold now stands over an uncounted label, as every other Hold on the Run wanted does. The removal waits for the release, and the label counts for nothing while it waits (`kernel/issue.py`, `_run_holds`).

This reverses the line of decision 1244 that read: "The act ceiling is not such a Hold. It never stops an act that stops work, so the label is still removed at that ceiling."

Limits: unmerged closes past their bound still place a Hold at the act ceiling. They are read before the label and before any Run wanted.

## Why

An issue held at the act ceiling while its State was new read `new` for the pass that removed another App's label. Only a person may move an issue out of held. A removal is itself an act, so it must not run past the act ceiling anyway. Making the removal under a held Decision was rejected, as in decision 1244: no issue Decision acts while held.

## Boundaries

| Boundary | Check |
|---|---|
| At the act ceiling the issue reads held, with or without the label, and makes no act; one act below, the label is removed | `tests/test_issue.py::test_an_uncounted_label_waits_at_the_act_ceiling`, `kernel/issue.py`, mutant: "an uncounted label is removed at the act ceiling" |
