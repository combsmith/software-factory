# tools/mutants_of/

The mutants of every file outside kernel/, one file to a target. `tools/mutants.py` holds the Kernel's mutants and runs them all, these after its ISSUE list.
A file here is named for its target, the path in lower case with its .py dropped and every other mark an underscore: the mutants of `adapters/pull.py` are in adapters_pull.py.
It holds `TARGETS`, the paths its mutants break, and `MUTANTS`. A mutant that breaks more than one path joins their files into one, whose `TARGETS` names them all.
A new file is imported, and listed in `AREAS`, in `__init__.py`, in the order of the names. What two or more files use goes in common.py.

| Rule | Held by |
|---|---|
| A mutant of a file outside kernel/ is in the file here whose `TARGETS` name that file, and in no other; each file is imported and listed in `AREAS` | `tests/test_tools.py::test_each_file_of_mutants_is_loaded_and_holds_its_targets_alone` |
| Every mutant's text, here or in `tools/mutants.py`, is found once in its target, or a test fails on the pull request | `tests/test_tools.py::test_every_mutant_finds_its_text_once_in_its_target` |
| A file here may name gh or git as text only while it imports nothing but from `tools.mutants_of` and `pathlib` | `tools/check_writes.py` |
