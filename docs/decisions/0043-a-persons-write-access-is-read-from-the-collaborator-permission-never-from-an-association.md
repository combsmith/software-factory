# 0043. A person's write access is read from the collaborator permission, never from an association

Status: accepted. Taken as the working rulings on 2026-10-20, with the Maintainer's answer of 2026-10-21 that triage is
not write access, for this issue:
"Design: an App cannot read an author's permission from the listing (P-32 failed); read it from the collaborator permission endpoint" (issue 222)
and for this one:
"Reader App: the permission the activity read needs is in config/apps.json, held by P-39's check" (issue 231).

## Decision

Every actor the facts carry with write access, an issue's author, each label event's actor, each review's and each
dismissal's, and each thread's opening and resolving actor, has it read from the repository's collaborator permission,
`GET /repos/{repo}/collaborators/{login}/permission`. Write access is `admin`, `maintain` or `write`; `triage`, `read`
and `none` are not. The port reads the permission once for each distinct login in a pass and applies it wherever that
login appears in the pass; it caches nothing across passes, and never asks it of an App, whose access is
`config/apps.json`'s (decision 0035). The facts keep their shape: `can_write` stays the boolean the port computes, and
nothing in `kernel/` or in a schema of the facts changes. No read of `authorAssociation` decides write access.

The reader App holds what the reads need, and the Apps data names each read: `read:facts.actor.can_write` for the
permission read, and the activity read under `read:facts.last_pusher`, each under the grant trial P-47 shows it needs.

## Why

Trial P-32 asked whether an issue's author's permission can be read in the listing of open issues, and failed on
2026-10-20 (`trials/P-32.json`): the reader App reads the org's owner's `authorAssociation` as CONTRIBUTOR where the
Maintainer's own login reads MEMBER. An App does not see org membership through the listing, and every read the Factory
makes is an App's. The collaborator permission answers the question asked, for any login, with the `metadata: read`
grant the reader already holds. Triage is not write access because the Kernel's write access is the one that can merge
a change: a person with triage can label an issue and cannot push, so a triage role's label is read as nobody's, which
stops work, and is the reading the Maintainer overturns by granting write.

The cost is REST, not GraphQL: the read spends none of the 3,000 points an hour W-4 allows nor of the 1,788 P-8
measured. At P-8's scale, 41 items on the repo it measured, the distinct logins on open items are fewer than the items:
at most 41 requests a pass, 492 an hour at twelve passes, a tenth of an installation's 5,000; at the 20 passes an hour
W-4 allows, 820.

## Boundaries

| Boundary | Check |
|---|---|
| The issue world builds an author's write access from the permission it serves, as the port will, and `admin`, `maintain` and `write` are write access | `tests/test_issue_simulator.py::test_an_authors_write_access_is_read_from_the_permission` |
| The simulator's rule names the trial that grounds it, P-47 | `tools/check_trials.py`, `tests/test_tools.py::test_a_rule_no_trial_asks_names_one_or_says_why_none_can` |
| The Apps data names the permission read, `read:facts.actor.can_write`, under the reader's `metadata: read`; a fact need names a field of facts/1, or a property of one of its definitions | `tools/check_apps.py`, `tests/test_tools.py::test_a_read_of_a_fact_that_does_not_exist_is_caught` |
| The reader's grants are what P-39 recorded: re-read on 2026-10-21 through the Maintainer's login, each App's permissions and events and the org's installations equal `trials/P-39.grants.json`, so no new fixture | `tools/check_apps.py` |
| The trial's script mints only tokens narrowed to one grant on the canary alone, revokes each, refuses before minting anything it cannot hold, and leaves no token in what it hands over | `tests/test_tools.py::test_each_read_is_made_with_each_token_kept_with_its_status_and_no_token_is_kept`, `tests/test_tools.py::test_each_refusal_comes_before_anything_is_minted`, `tests/test_tools.py::test_a_refused_mint_or_revocation_stops_the_run_and_says_so` |
| The port reads the permission once per distinct login per pass, never from an association, and never of an App | waiting on `adapters/` |
