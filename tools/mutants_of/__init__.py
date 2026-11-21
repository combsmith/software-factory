"""The mutants of every file outside kernel/, one file to a target: tools/mutants.py runs them after the Kernel's ISSUE.

A file here is named for its target, `adapters/pull.py` as `adapters_pull.py`, holds TARGETS, the paths its mutants
break, and MUTANTS, and is imported below and listed in AREAS, in the order of the files' names. A mutant of a file
under kernel/ stays in tools/mutants.py. Each mutant of a path in a file's TARGETS is in that file and no other
(tests/test_tools.py::Mutants::test_each_file_of_mutants_is_loaded_and_holds_its_targets_alone). What two or more
files use is in common.py.
"""

# Every file's mutants, in the order of the files' names.
AREAS = ()
MUTANTS = [mutant for area in AREAS for mutant in area.MUTANTS]
