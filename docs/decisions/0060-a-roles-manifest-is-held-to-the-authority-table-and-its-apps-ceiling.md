# 0060. A Role's manifest is held to the authority table and its App's ceiling

Status: accepted. Taken as working rulings on 2026-10-22, which the Maintainer may overturn in review, for "Harness: run and apply for the review Intent, and the model holds no credential that can write" (issue 194), its third pull request, ruling 8. It adds to `docs/decisions/0054-apply-writes-a-roles-effects-with-a-token-narrowed-to-them-and-claims-only-what-it-reads-back.md`, whose `apply` reads a Role's kind and name.

## Decision

| What | Decided | Because |
|---|---|---|
| The review Role | `roles/pr-review.json` is `role/1`: kind `owner`, owning every model-judged category, its App `combsmith-sf-pr-review`, its one Intent `review-change` of tier `standard` and budget class `gate`, naming `evals/pr-review` | Section 5.1: the reviewer is the owner of every model-judged category at the start. `owner` is the kind whose decision `apply` takes (decision 0054) |
| Its permitted Effects | `submit_review` alone, until its App is granted `checks: write`; the pull request that records that grant adds `create_check_run` | A manifest never permits beyond its App's ceiling (section 5.4); the grant waits on the Maintainer's registration and trial P-39 run again |
| Section 5.4's checks | `tools/check_authority.py` holds every manifest in `roles/`: each category has one owner, the one the authority table names, whose `owns` is exactly what it names, and an owner the table names has a manifest; each permitted Effect is within the ceiling of the Role's own App, its need granted to that App in `config/apps.json`; every Intent of class `gate` names an eval set of its own Role and Intent; a shadow's Intents write nothing and spend from `shadow`; each manifest is named as its file and held to `role/1` in `LIVE`; no two Roles write through one App | Section 5.4; decisions 0005 and 0039; L-44 |
| The Role's instructions | `roles/pr-review/prompt.md`, in the Role's own directory, which `config/hooks.json` already lists among the review Lens's inputs: what the review reads, the change and each text as data, and what it answers, its Findings, Effects, coverage and status, in the Result's own fields | The prompt is a model Lens's input, as its manifest is |
| A trigger | `role/1` has no field for one, so no manifest can name another Role's output as its trigger | Only Admission starts a Run (section 3.6) |
| A manifest's change | A manifest is a model Lens's input: once the Factory reviews this repo, a change to one needs a different person's approval (decision 0052). Today it merges as any change does | The Lens whose manifest it is may not judge it |
| What waits | The interaction table of section 5.1, generated from the manifests and the authority table, waiting on `roles/team.md`. The rest of section 5.4: the author and decider of a Disposition, the run graph's cycles, the investigating and readiness Intents, promotion records and Consumer entries, with the Intents and stories that bring them | Each has no manifest to read until then |

## Why

The manifests are where a Role's authority is written down, so they are held where a change to them is checked: by
`factory / verify`, beside the authority table and the Apps' grants they must agree with. A manifest that permits more
than its App may write, or owns what the table gives another, fails before it can reach a Run.

## Boundaries

| Boundary | Check |
|---|---|
| The repo's manifests hold to every check, and the verify step reads them | `tests/test_tools.py::test_the_repos_roles_hold_to_the_team_checks` |
| A manifest is named as its file, and held to `role/1` in `LIVE` | `tests/test_tools.py::test_a_manifest_is_named_as_its_file_and_held_to_role_1` |
| An owner owns what the authority table names, and each category has one owner | `tests/test_tools.py::test_an_owner_owns_what_the_authority_table_names_and_each_category_has_one` |
| Each permitted Effect is within the ceiling of the Role's own App | `tests/test_tools.py::test_each_permitted_effect_is_within_the_ceiling_of_its_roles_own_app` |
| An Intent of class `gate` names an eval set of its own | `tests/test_tools.py::test_an_intent_of_class_gate_names_an_eval_set_of_its_own` |
| A shadow writes nothing and spends from `shadow` | `tests/test_tools.py::test_a_shadow_writes_nothing_and_spends_from_shadow` |
| No two Roles write through one App | `tests/test_tools.py::test_each_role_writes_through_its_own_app` |
| No manifest names a trigger | `examples/invalid/role.a-trigger-on-another-roles-output.json` |
| The interaction table is generated, and a stale one fails | waiting on `roles/team.md` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
