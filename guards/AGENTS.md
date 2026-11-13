# guards/

The guards on a Role's own writes, as pure functions: each says what such a write may land, or gives the one reason, a code, why nothing may. None is built yet; the first applies a Role's patch.
A guard binds the Role that writes this repo's code. So it lives here, never in `kernel/` or `adapters/`, where that Role may push; a port hands a guard what it read, and the Harness calls it. A guard reads nothing itself.

| Rule | Held by |
|---|---|
| No I/O: no file, socket, process, environment variable or clock. Nothing is kept between calls. No `raise`, no special name, no number but 0 and 1 | `tools/check_purity.py` |
| A guard calls nothing it is given: it takes no `_decision`, the one parameter the Kernel may call | `tests/test_tools.py::test_the_guards_are_the_package_python_imports_and_take_no_rule_of_a_kernel_module` |
| Only `__future__` and `guards` are imported, `guards` by its name and never relatively; the Kernel never, which is no protected path | `tests/test_tools.py::test_the_guards_are_held_as_the_kernel_is_and_import_themselves_alone` |
| Every folder here has an `__init__.py` and holds Python's source and an `AGENTS.md` alone: Python imports what the check read | `tests/test_tools.py::test_the_guards_are_the_package_python_imports_and_take_no_rule_of_a_kernel_module` |
| No module here is named as `kernel/terms.py`, `kernel/gate.py` or `kernel/brakes.py` is: the check's rules for those names are the Kernel's | `tests/test_tools.py::test_the_guards_are_the_package_python_imports_and_take_no_rule_of_a_kernel_module` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
