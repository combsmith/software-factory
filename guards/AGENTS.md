# guards/

The guards on a Role's own writes, as pure functions: each says what such a write may land, or gives the one reason, a code, why nothing may. `patch.py` applies a Role's patch, byte for byte, to the files it names; the guard on a push is still to come.
A guard binds the Role that writes this repo's code. So it lives here, never in `kernel/` or `adapters/`, where that Role may push; a port hands a guard what it read, and the Harness calls it. A guard reads nothing itself.

| Rule | Held by |
|---|---|
| No I/O: no file, socket, process, environment variable or clock. Nothing is kept between calls. No `raise`, no special name, no number but 0 and 1 | `tools/check_purity.py` |
| A guard calls nothing it is given: it takes no `_decision`, the one parameter the Kernel may call | `tests/test_tools.py::test_the_guards_are_the_package_python_imports_and_take_no_rule_of_a_kernel_module` |
| Only `__future__` and `guards` are imported, `guards` by its name and never relatively. Never the Kernel: it is not protected whole, so no guard rests on it | `tests/test_tools.py::test_the_guards_are_held_as_the_kernel_is_and_import_themselves_alone` |
| Every folder here has an `__init__.py` and holds the source the check reads and an `AGENTS.md` alone, no link: Python imports what was read | `tests/test_tools.py::test_the_guards_are_the_package_python_imports_and_take_no_rule_of_a_kernel_module` |
| No module here is named as `kernel/terms.py`, `kernel/gate.py` or `kernel/brakes.py` is: the check's rules for those names are the Kernel's | `tests/test_tools.py::test_the_guards_are_held_as_the_kernel_is_and_import_themselves_alone` |
| Nothing is read of a value but by a built-in type's method that is called: a generator's frame is one attribute from every builtin | `tests/test_tools.py::test_the_guards_are_the_package_python_imports_and_take_no_rule_of_a_kernel_module` |
| A module's name here is bound by its import alone: no parameter, local, function or other import takes it | `tests/test_tools.py::test_the_guards_are_the_package_python_imports_and_take_no_rule_of_a_kernel_module` |
| A Role's push that touches `guards/` is refused: it is a protected path | `tests/test_apply.py::test_a_push_is_held_to_the_bases_list_by_each_class_of_path` |
| A package at the top of the repo is one of verify's inputs, whole, and this one is | `tests/test_tools.py::test_every_package_at_the_top_of_the_repo_is_a_lens_input_whole` |
| A patch is read section by section as git writes it: each one's kind, its two names and its modes | `tests/test_guards.py::test_a_patch_is_read_section_by_section_as_git_writes_it` |
| A name is read one way: unquoted, of a narrow set of characters and no more parts than a bound; each line that names a file agrees with the header | `tests/test_guards.py::test_a_name_is_read_one_way_or_not_at_all` |
| What is not a patch as git writes it is unreadable, never fewer changes | `tests/test_guards.py::test_what_is_not_a_patch_as_git_writes_it_is_unreadable` |
| A section's hunks are read as their headers count them, each line on its side, with git's marker of a last line that ends in no newline | `tests/test_guards.py::test_a_sections_hunks_are_read_as_their_headers_count_them` |
| A hunk or a side git does not write makes its patch unreadable, and so does a NUL: a binary change written as text | `tests/test_guards.py::test_a_hunk_or_a_side_git_does_not_write_is_unreadable` |
| The files a patch reads are named once each, and a new file reads none | `tests/test_guards.py::test_sources_names_each_file_a_patch_reads_once_and_no_new_file` |
| A hunk stands where its header says, past the one before it: nothing is searched for, and no line is matched loosely | `tests/test_guards.py::test_a_hunk_stands_where_its_header_says_and_nowhere_else` |
| The newline at a file's end is as the patch says: git's marker stands only where a last line has none, and no line follows it | `tests/test_guards.py::test_the_newline_at_a_files_end_is_as_the_patch_says` |
| A patch lands the bytes it says and no others, or nothing | `tests/test_guards.py::test_a_patch_lands_the_bytes_it_says_and_no_others` |
| A new, a removed, a renamed and a copied file are each what the patch says; a copy reads the admitted commit's file | `tests/test_guards.py::test_a_new_a_removed_a_renamed_and_a_copied_file_are_each_what_the_patch_says` |
| No file is written twice or copied twice, and none where the tree holds one the patch does not name | `tests/test_guards.py::test_a_file_is_written_once_and_only_where_the_patch_says_it_stands` |
| What is no file is never written: a link, a submodule, a path under a file, or one where a directory stands | `tests/test_guards.py::test_what_is_no_file_is_never_written` |
| A tree in no shape a port gives, and a file's bytes it did not hand over, are the Factory's fault, under its own code | `tests/test_guards.py::test_what_a_port_did_not_read_is_the_factorys_under_its_own_code` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
