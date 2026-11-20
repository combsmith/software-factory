# guards/

The guards on a Role's own writes, as pure functions: each says what such a write may land, or the one reason, a code, why not. `patch.py` applies a Role's patch byte for byte; `push.py` holds its push to its order; `opening.py` keeps a draft from linking.
A guard binds the Role that writes this repo's code. So it lives here, never in `kernel/` or `adapters/`, where that Role may push; a port hands a guard what it read, and the Harness calls it. A guard reads nothing itself.

| Rule | Held by |
|---|---|
| No I/O: no file, socket, process, environment variable or clock. Nothing is kept between calls. No `raise`, no special name, no number but 0 and 1 | `tools/check_purity.py` |
| A guard calls nothing it is given: it takes no `_decision`, the one parameter the Kernel may call | `tests/test_tools.py::test_the_guards_are_held_as_the_kernel_is_and_import_themselves_alone` |
| Only `__future__` and `guards` are imported, `guards` by its name and never relatively. Never the Kernel: it is not protected whole, so no guard rests on it | `tests/test_tools.py::test_the_guards_are_held_as_the_kernel_is_and_import_themselves_alone` |
| Every folder here has an `__init__.py` and holds the source the check reads and an `AGENTS.md` alone, no link: Python imports what was read | `tests/test_tools.py::test_the_guards_are_the_package_python_imports_and_read_nothing_off_a_value` |
| No module here is named as `kernel/terms.py`, `kernel/gate.py` or `kernel/brakes.py` is: the check's rules for those names are the Kernel's | `tests/test_tools.py::test_the_guards_are_held_as_the_kernel_is_and_import_themselves_alone` |
| Nothing is read of a value but by a built-in type's method that is called: a generator's frame is one attribute from every builtin | `tests/test_tools.py::test_the_guards_are_the_package_python_imports_and_read_nothing_off_a_value` |
| A module's name here is bound by its import alone: no parameter, local, function or other import takes it | `tests/test_tools.py::test_the_guards_are_the_package_python_imports_and_read_nothing_off_a_value` |
| A Role's push that touches `guards/` is refused: it is a protected path | `tests/test_apply.py::test_a_push_is_held_to_the_bases_list_by_each_class_of_path` |
| A package at the top of the repo is one of verify's inputs, whole, and this one is | `tests/test_tools.py::test_every_package_at_the_top_of_the_repo_is_a_lens_input_whole` |
| A patch is read section by section as git writes it: each one's kind, its two names and its modes | `tests/test_guards.py::test_a_patch_is_read_section_by_section_as_git_writes_it` |
| A name is read one way: unquoted, of a narrow set of characters and no more parts than a bound; each line that names a file agrees with the header | `tests/test_guards.py::test_a_name_is_read_one_way_or_not_at_all` |
| Unreadable, never fewer changes: what git does not write, a path on two new sides, named once renamed or removed, read once made, moved once changed, a file under one made | `tests/test_guards.py::test_what_is_not_a_patch_as_git_writes_it_is_unreadable` |
| A section's hunks are read as their headers count them, each line on its side, with git's marker of a last line that ends in no newline | `tests/test_guards.py::test_a_sections_hunks_are_read_as_their_headers_count_them` |
| A hunk or a side git does not write makes its patch unreadable: out of order or place, changing nothing, in a form or with no index line git never writes; so does a NUL | `tests/test_guards.py::test_a_hunk_or_a_side_git_does_not_write_is_unreadable` |
| The files a patch reads are named once each, and a new file reads none | `tests/test_guards.py::test_sources_names_each_file_a_patch_reads_once_and_no_new_file` |
| A hunk stands in the file where its header says: nothing is searched for, and no line is matched loosely | `tests/test_guards.py::test_a_hunk_stands_where_its_header_says_and_nowhere_else` |
| The newline at a file's end is as the patch says: git's marker stands only where a last line has none, and no line follows it | `tests/test_guards.py::test_the_newline_at_a_files_end_is_as_the_patch_says` |
| A patch lands the bytes it says and no others, or nothing | `tests/test_guards.py::test_a_patch_lands_the_bytes_it_says_and_no_others` |
| A new, a removed, a renamed and a copied file are each what the patch says; a copy reads the admitted commit's file | `tests/test_guards.py::test_a_new_a_removed_a_renamed_and_a_copied_file_are_each_what_the_patch_says` |
| No file is written twice or copied twice, and none where the tree holds one the patch does not name | `tests/test_guards.py::test_a_file_is_written_once_and_only_where_the_patch_says_it_stands` |
| What is no file is never written: a link, a submodule, a path under a file, or one where a directory stands | `tests/test_guards.py::test_what_is_no_file_is_never_written` |
| A tree in no shape a port gives, and a file's bytes it did not hand over, are the Factory's fault, under its own code | `tests/test_guards.py::test_what_a_port_did_not_read_is_the_factorys_under_its_own_code` |
| What it lands is what git lands, on fixed seeds, of a patch as git writes it and of the same patch broken | `tests/test_guards.py::test_a_patch_as_git_writes_it_lands_what_git_would` |
| A push is told whole or begins nothing; its changes are `applied`'s, path by path | `tests/test_guards.py::test_a_push_is_told_whole_or_begins_nothing`, `tests/test_guards.py::test_a_pushs_changes_are_what_applied_gives_path_by_path` |
| No request leaves this repo's git data; it reads only the admitted commit, its branch, what it made | `tests/test_guards.py::test_nothing_leaves_outside_this_repos_git_data`, `tests/test_guards.py::test_a_push_reads_the_admitted_commit_and_its_own_branch` |
| The admitted tree is read whole, and the branch as the Decision admitted it | `tests/test_guards.py::test_the_admitted_tree_is_read_whole_or_not_at_all`, `tests/test_guards.py::test_the_branch_is_read_as_the_decision_admitted_it` |
| Nothing is written before those reads; one blob to each written content | `tests/test_guards.py::test_nothing_is_written_before_the_tree_and_the_branch_were_read`, `tests/test_guards.py::test_a_blob_is_made_once_of_each_written_files_base64` |
| One tree, of exactly the changes; `apply` is asked about the paths that land | `tests/test_guards.py::test_the_one_tree_names_exactly_the_changes_by_the_blobs_made`, `tests/test_guards.py::test_the_paths_apply_is_asked_about_are_the_paths_that_land` |
| One commit, of the tree read back as the admitted one with the changes | `tests/test_guards.py::test_the_tree_read_back_is_the_admitted_one_with_the_changes`, `tests/test_guards.py::test_the_one_commit_is_of_the_tree_read_back_on_the_admitted_commit` |
| The branch is written once, not by force; landed when read again there | `tests/test_guards.py::test_the_branch_is_written_once_at_the_commit_made_never_by_force`, `tests/test_guards.py::test_a_push_lands_when_the_branch_is_read_again_at_the_commit` |
| A draft's title and body are text UTF-8 carries, read as GitHub renders it; the first refusal is given | `tests/test_guards.py::test_a_drafts_title_and_body_are_text_this_reads`, `tests/test_guards.py::test_the_first_refusal_that_holds_is_the_one_given` |
| No issue or pull request is linked, no one is mentioned, no keyword closes | `tests/test_guards.py::test_no_issue_or_pull_request_is_linked`, `tests/test_guards.py::test_no_one_is_mentioned`, `tests/test_guards.py::test_no_keyword_closes` |
| An answer is GitHub's to that request, or the push stops; each rule here has a mutant a test kills | `tests/test_guards.py::test_an_answer_is_githubs_to_that_request_or_the_push_stops`, `tools/mutants.py` |
