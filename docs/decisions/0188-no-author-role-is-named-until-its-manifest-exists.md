# 0188. No author Role is named until its manifest exists

Status: accepted. The Factory Builder's ruling on "author_role is null until roles/dev-lead.json exists, so a fix Run is never dispatched to a missing role" (issue 675), under the slice-1 epic. The edits to `config/defaults.json` and `sim/world.py` are pre-approved by the Maintainer 2026-11-08, ruled by the Factory Builder. It changes back when waiting on `roles/dev-lead.json` lands.

## Decision

| What | Decided | Because |
|---|---|---|
| The configuration | `config/defaults.json` names no `author_role` until the author Role has its manifest, waiting on `roles/dev-lead.json`. Until then the Kernel decides no fix Run (`kernel/decide.py`'s `_wanted_run`), and an item that needs one, with an open blocking Finding or a failed check, has outcome `nothing` and waits for a person | Its manifest is not there, so the Run fails at `harness.read` with `file_unreadable` on every pass, up to the Run ceiling of 10 an item, and three such faults trip the automatic Pause |
| The check | `tools/check_authority.py` refuses a configuration whose `author_role` or `owner_role` is no Role's name as role/1 spells one, or names no file under `roles/`, so it cannot recur. The owner Role is always named; the author Role may be none. A named author Role is the authority table's, as before. The configuration may name none while the table still names the Role that will fix | The authority table says who the author Role is; the configuration says whether one serves yet |
| The tests and the simulator | `tests/support.py` and `sim/world.py` take the author Role from the authority table: the simulator models the Factory once `dev-lead` exists, and the Kernel's fix path is held with a Role in place. The live configuration defers each fix to a person until then, which a test reading the real configuration holds | The fix path still has to be right on the day the Role lands |
| When it changes back | The pull request that adds the author Role's manifest, waiting on `roles/dev-lead.json`, names it in `config/defaults.json` again, and changes the test that reads the configuration | The check refuses the name before then |

## Why

The Factory decided fix Runs for a Role that does not exist, and each failed where it read the Role's manifest. Naming no author Role stops that at the decision, and the check stops a name with no manifest.

## Boundaries

| Boundary | Check |
|---|---|
| The configuration names no author Role while it has no manifest, and an item needing a fix, for an open blocking Finding or a failed check, waits with outcome `nothing` and no Run | `tests/test_decide.py::test_the_configuration_names_no_author_role_until_its_manifest_exists`, `config/defaults.json`, mutant: "the configuration names an author Role with no manifest" |
| A Role the configuration names is a Role's name and has a manifest under `roles/`; the owner is always named; a named author Role is the authority table's, and none is allowed | `tests/test_tools.py::test_a_role_the_configuration_names_has_a_manifest`, `tools/check_authority.py`, mutant: "a Role the configuration names may have no manifest", mutant: "a Role's name in the configuration may reach outside roles/", mutant: "a Role's name in the configuration need only begin as one", mutant: "the configuration may name no owner Role", mutant: "no author Role in the configuration differs from the authority table's", mutant: "every named author Role differs from the authority table's" |
