# guards/

The guards on a Role's own writes, as pure functions: each says what such a write may land, or gives the one reason, a code, why nothing may. None is built yet; the first applies a Role's patch.
A guard binds the Role that writes this repo's code. So it lives here, never in `kernel/` or `adapters/`, where that Role may push; a port hands a guard what it read, and the Harness calls it. A guard reads nothing itself.

| Rule | Held by |
|---|---|
| No I/O: no file, socket, process, environment variable or clock. Nothing is kept between calls. No `raise`, no special name, no number but 0 and 1 | `tools/check_purity.py` |
| Only `__future__` and `guards` are imported, `guards` by its name and never relatively. Never the Kernel: it is not protected whole, so no guard rests on it | `tests/test_tools.py::test_the_guards_are_held_as_the_kernel_is_and_import_themselves_alone` |
| No module here is named as `kernel/terms.py`, `kernel/gate.py` or `kernel/brakes.py` is: the check's rules for those names are the Kernel's | `tests/test_tools.py::test_the_guards_are_held_as_the_kernel_is_and_import_themselves_alone` |
| A Role's push that touches `guards/` is refused: it is a protected path | `tests/test_apply.py::test_a_push_is_held_to_the_bases_list_by_each_class_of_path` |
| A package at the top of the repo is one of verify's inputs, whole, and this one is | `tests/test_tools.py::test_every_package_at_the_top_of_the_repo_is_a_lens_input_whole` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
