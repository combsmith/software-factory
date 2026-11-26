# 1255. An uncounted label waits at the act ceiling too

Status: accepted. 2026-11-26, the Solution Architect; issue 1251. Reverses one line of decision 1244, which it extends.

## Decision

Where the issue Kernel reads the act ceiling, its Hold now stands over an uncounted label, as every Hold from the Run wanted does. The removal waits for the release, and the label counts for nothing while it waits (`kernel/issue.py`, `_run_holds`).

This reverses the line of decision 1244 that read: "The act ceiling is not such a Hold. It never stops an act that stops work, so the label is still removed at that ceiling."

Limits: the ceiling is read only where acceptance is due. In triage, in new under another App's `factory:triage`, or with the count unread, the removal still runs, so a label added again each pass is removed each pass. Unmerged closes still place a Hold at the ceiling. While held, the label stays on GitHub.

## Why

An issue held at the act ceiling while its State was new read `new` for the pass that removed another App's label. Only a person may move an issue out of held. The act ceiling's Hold reads held, and no held Decision acts; the ceiling still brakes no removal by itself (decision 0003). Making the removal under a held Decision was rejected for that reason, as in decision 1244.

## Boundaries

| Boundary | Check |
|---|---|
| At the act ceiling the issue reads held, with or without the label, and makes no act; one act below, the label is removed | `tests/test_issue.py::test_an_uncounted_label_waits_at_the_act_ceiling`, `kernel/issue.py`, mutant: "an uncounted label is removed at the act ceiling" |
