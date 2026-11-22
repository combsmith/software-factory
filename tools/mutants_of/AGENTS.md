# tools/mutants_of/

The mutants of every file outside kernel/, one file to a target. `tools/mutants.py` holds the Kernel's mutants and runs them all, these after its ISSUE list.
Until the move that brings them here, a file whose mutants are still in `tools/mutants.py` takes a new one beside them there;
a file with none yet gets a file of its own here.
A file here is named for its target by `named` in `__init__.py`: the path in lower case, a .py dropped, other extensions kept,
and each run of characters but letters and digits an underscore. The mutants of `adapters/pull.py` are in adapters_pull.py.
It holds `TARGETS`, the paths its mutants break, and `MUTANTS`. One entry of a list may make mutants of several paths, as a loop over scripts does:
those paths share one file, named for one of them, whose `TARGETS` names them all.
`tools/mutants.py` finds each file here by the walk, in the order of the names, so a new one is in no list. What two or more files use goes in common.py.

| Rule | Held by |
|---|---|
| A mutant of a path a file here names in `TARGETS` is in that file and in no other, and the file is named for one of them; each file is found and loaded | `tests/test_tools.py::test_each_file_of_mutants_is_loaded_and_holds_its_targets_alone` |
| Every mutant's text, here or in `tools/mutants.py`, is found once in its target, or a test fails on the pull request | `tests/test_tools.py::test_every_mutant_finds_its_text_once_in_its_target` |
| A file here may name gh or git as text only in a top-level assignment, and only while it imports no module, and imports only from files here that import none either | `tools/check_writes.py` |
