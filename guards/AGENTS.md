# guards/

The guards on a Role's own writes, as pure functions: each says what such a write may land, or gives the one reason, a code, why nothing may. `patch.py` reads a Role's patch as git writes it; applying it is its next part.
A guard binds the Role that writes this repo's code. So it lives here, never in `kernel/` or `adapters/`, where that Role may push; a port hands a guard what it read, and the Harness calls it. A guard reads nothing itself.

| Rule | Held by |
|---|---|
| No I/O: no file, socket, process, environment variable or clock. Nothing is kept between calls. No `raise`, no special name, no number but 0 and 1 | `tools/check_purity.py` |
| A guard calls nothing it is given: it takes no `_decision`, the one parameter the Kernel may call | `tests/test_tools.py::test_the_guards_are_the_package_python_imports_and_take_no_rule_of_a_kernel_module` |
| Only `__future__` and `guards` are imported, `guards` by its name and never relatively; the Kernel never, which is no protected path | `tests/test_tools.py::test_the_guards_are_held_as_the_kernel_is_and_import_themselves_alone` |
| Every folder here has an `__init__.py` and holds Python's source and an `AGENTS.md` alone: Python imports what the check read | `tests/test_tools.py::test_the_guards_are_the_package_python_imports_and_take_no_rule_of_a_kernel_module` |
| No module here is named as `kernel/terms.py`, `kernel/gate.py` or `kernel/brakes.py` is: the check's rules for those names are the Kernel's | `tests/test_tools.py::test_the_guards_are_the_package_python_imports_and_take_no_rule_of_a_kernel_module` |
| A patch is read section by section as git writes it: its kind, its two names, its modes and its hunks | `tests/test_guards.py::test_a_patch_is_read_section_by_section_as_git_writes_it` |
| The files a patch reads are named once each, and a new file reads none | `tests/test_guards.py::test_sources_names_each_file_a_patch_reads_once_and_no_new_file` |
| A name is read one way, unquoted and of a narrow set of bytes; every line that names a file agrees with the header | `tests/test_guards.py::test_a_name_is_read_one_way_or_not_at_all` |
| What is not a patch as git writes it is unreadable, never fewer changes | `tests/test_guards.py::test_what_is_not_a_patch_as_git_writes_it_is_unreadable` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
