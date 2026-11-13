# guards/

The guards on a Role's own writes, as pure functions: each will say what such a write may land, or give the one reason, a code, why nothing may. None is built yet.
The package is listed in `config/hooks.json` before it holds a guard, so that the first one is never a file a Role could change.

| Rule | Held by |
|---|---|
| A Role's push that touches `guards/` is refused: it is a protected path | `tests/test_apply.py::test_a_push_is_held_to_the_bases_list_by_each_class_of_path` |
| A package at the top of the repo is one of verify's inputs, whole, and this one is | `tests/test_tools.py::test_every_package_at_the_top_of_the_repo_is_a_lens_input_whole` |
