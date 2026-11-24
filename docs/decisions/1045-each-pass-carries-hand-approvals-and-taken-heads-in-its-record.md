# 1045. Each pass carries hand approvals and taken heads in its record

Status: accepted. 2026-11-22, the Solution Architect's ruling on issue 1026. Extends `docs/decisions/0241-the-maintainers-hand-approval-of-a-pull-request-waiting-for-a-person-is-information-and-any-other-unmatched-approval-alarms.md`, whose row "Until the next part" ends here.

## Decision

Each pass writes `reconciled.hand` and `reconciled.taken` into its record, as decision 0241's row "Carried" says. `controller/reconcile.py` (`carried`) holds the exact form and `schemas/pass.schema.json` the shape. The cut-a-release skill says such a hand approval is information, any other unmatched one alarms, and every entry is read.

Limits: a pull request left out of the last pass, its facts unread and nothing of it owed, and closed before the next, is read as leaving by no pass. So its entries stay: a head stays taken, which raises more alarms, never fewer.

## Why

Without the carry, a head was taken only within the 30-hour window of the last two records, so a hand pull request that waited longer read its approval as unmatched. Decision 0241 left the carry to this part and its record, and a record is never edited.

## Boundaries

| Boundary | Check |
|---|---|
| `reconciled.hand` and `reconciled.taken` carry each hand approval and each head any other approval took, once, while its pull request is open or its leaving is held; the pass whose window passes that leaving drops them, with what is new for it; one given and merged between passes is information until then; one read open again (decided or left out) or leaving again keeps its own, another repository's of that number does not; an unreadable seen drops nothing; one carried as the hand is not carried as taken, and one whose review reads another head keeps that head taken | `tests/test_reconcile.py::test_hand_and_taken_are_carried_until_the_window_passes_their_leaving`, `tests/test_controller.py::test_a_hand_approval_merged_between_passes_stays_information`, `controller/reconcile.py`, `controller/pass_.py`, `schemas/pass.schema.json`, mutant: "a hand is not carried", mutant: "a carried hand is carried twice", mutant: "a hand ages out", mutant: "a hand outlives its leaving", mutant: "a taken head is not carried", mutant: "a taken head outlives its leaving", mutant: "a leaving drops at once", mutant: "a held leaving drops", mutant: "an unreadable seen drops", mutant: "leaving again drops", mutant: "a reopened one drops", mutant: "another repository's number keeps", mutant: "a new hand past its leaving is carried", mutant: "a new head past its leaving is carried", mutant: "an old leaving drops every hand", mutant: "an old leaving drops every head", mutant: "a head read again is carried twice", mutant: "a hand beside a carried one is dropped", mutant: "two keyless heads at one commit are one", mutant: "a hand is carried as taken too", mutant: "a hand drops its key from taken", mutant: "a taken head ages out", mutant: "a keyless head is not carried", mutant: "the pass carries no hand", mutant: "the pass carries no taken head", mutant: "the pass reads no pull request as open", mutant: "one left out is not read as open" |
| The skill says the hand approval of such a pull request is information and any other unmatched approval alarms, and every entry is read | `tests/test_release.py::test_when_the_factory_cannot_approve_the_skill_leaves_the_approval_to_the_maintainers_hand_and_runs_nothing`, `.claude/skills/cut-a-release/SKILL.md`, mutant: "the skill is silent on the alert a hand approval raises" |
