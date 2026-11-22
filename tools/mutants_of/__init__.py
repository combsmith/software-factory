"""The mutants of every file outside kernel/, one file to a target: tools/mutants.py runs them, after its ISSUE.

A file here is named for its target, as `named` names it, and holds TARGETS, the paths its mutants break, and MUTANTS.
tools/mutants.py finds each by the walk, in the order of the names, so no list names one. A mutant of a file under
kernel/ stays in tools/mutants.py. Each mutant of a path in a file's TARGETS is in that file and no other
(tests/test_tools.py::Mutants::test_each_file_of_mutants_is_loaded_and_holds_its_targets_alone). What two or more
files use is in common.py.
"""

import re


def named(target: str) -> str:
    """The name of the file here that holds the mutants of `target`: the path in lower case, its .py dropped, and every
    run of other marks an underscore, `adapters/pull.py` as `adapters_pull`; led by one where it starts with a digit."""
    name = re.sub(r"[^0-9a-z]+", "_", re.sub(r"\.py$", "", target.lower())).strip("_")
    return "_" + name if name[:1].isdigit() else name

