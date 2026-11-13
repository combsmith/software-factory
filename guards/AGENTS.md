# guards/

The guards on a Role's own writes, as pure functions. `patch.py` applies a Role's patch to the files it names, byte for byte, and gives what the push writes, or the one reason, a code, why nothing may land.
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
| A patch lands the bytes it says and no others; a carriage return stays a byte of its line | `tests/test_guards.py::test_a_patch_lands_the_bytes_it_says_and_no_others` |
| A hunk stands where its header says, past the one before it: nothing is searched for, and no line is matched loosely | `tests/test_guards.py::test_a_hunk_stands_where_its_header_says_and_nowhere_else` |
| The newline at a file's end is as the patch says; git's marker stands only where a last line has none, and no line follows a new one | `tests/test_guards.py::test_the_newline_at_a_files_end_is_as_the_patch_says` |
| A new, a removed, a renamed and a copied file are each what the patch says; a copy reads the admitted commit's bytes | `tests/test_guards.py::test_a_new_a_removed_a_renamed_and_a_copied_file_are_each_what_the_patch_says` |
| No file is written twice, none where the tree holds one the patch does not name, and none whose bytes were not read | `tests/test_guards.py::test_a_file_is_written_once_and_only_where_the_patch_says_it_stands` |
| What is no file is never written: a link, a submodule, a path under a file, or one where a directory stands | `tests/test_guards.py::test_what_is_no_file_is_never_written` |
| A name is read one way, unquoted and of a narrow set of bytes; every line that names a file agrees with the header | `tests/test_guards.py::test_a_name_is_read_one_way_or_not_at_all` |
| What is not a patch as git writes it is unreadable, never fewer changes | `tests/test_guards.py::test_what_is_not_a_patch_as_git_writes_it_is_unreadable` |
| A tree or contents in no shape a port gives is the Factory's fault, under its own code, whatever the patch is | `tests/test_guards.py::test_what_is_not_a_patch_as_git_writes_it_is_unreadable` |
| What it lands is what git itself would, on fixed seeds | `tests/test_guards.py::test_a_patch_as_git_writes_it_lands_what_git_would` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
