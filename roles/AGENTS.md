# roles/

The Role manifests, `role/1`, one to a file named for its Role: what each Role sees, raises, owns and may do, and each
of its Intents with its tier, permitted Effects, budget class and eval set (design sections 3.11 and 5.1). `pr-review.json`
is the review Role, the owner of every model-judged category, writing through its own App. `pr-review/prompt.md` is its instructions. A manifest is a model Lens's
input: once the Factory reviews this repo, a change to one needs a second person's approval (decision 0052).

Not built yet, by the stories that hold their rules: team.md.

| Rule | Held by |
|---|---|
| A manifest is `role/1`, named as its file, and held in `LIVE` | `tests/test_tools.py::test_a_manifest_is_named_as_its_file_and_held_to_role_1` |
| An owner owns what the authority table names, and each category has one owner | `tests/test_tools.py::test_an_owner_owns_what_the_authority_table_names_and_each_category_has_one` |
| Each permitted Effect is within the ceiling of the Role's own App | `tests/test_tools.py::test_each_permitted_effect_is_within_the_ceiling_of_its_roles_own_app` |
| An Intent of class `gate` names an eval set of its own Role and Intent | `tests/test_tools.py::test_an_intent_of_class_gate_names_an_eval_set_of_its_own` |
| A shadow writes nothing and spends from `shadow` | `tests/test_tools.py::test_a_shadow_writes_nothing_and_spends_from_shadow` |
| Each Role writes through its own App, and no two share one | `tests/test_tools.py::test_each_role_writes_through_its_own_app` |
| No manifest names another Role's output as a trigger: `role/1` has no field for one | `examples/invalid/role.a-trigger-on-another-roles-output.json` |
| The repo's manifests hold to every one of these | `tests/test_tools.py::test_the_repos_roles_hold_to_the_team_checks` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
