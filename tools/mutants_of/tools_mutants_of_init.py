"""The mutants of `tools/mutants_of/__init__.py`: tools/mutants.py runs them."""

TARGETS = ("tools/mutants_of/__init__.py",)
MUTANTS = [
    # Issue 1101: each file of mutants is named for a target.
    ("a file of mutants is named with its target's .py", 'tools/mutants_of/__init__.py',
     're.sub(r"\\.py$", "", target.lower())', 'target.lower()', ('tests.test_tools.Mutants.test_each_file_of_mutants_is_loaded_and_holds_its_targets_alone',)),
    ("a file of mutants is named with its target's leading marks", 'tools/mutants_of/__init__.py',
     'target.lower())).strip("_")', 'target.lower()))', ('tests.test_tools.Mutants.test_each_file_of_mutants_is_loaded_and_holds_its_targets_alone',)),
    ("a file of mutants may be named as no module can be", 'tools/mutants_of/__init__.py',
     '    return "_" + name if name[:1].isdigit() else name\n', '    return name\n', ('tests.test_tools.Mutants.test_each_file_of_mutants_is_loaded_and_holds_its_targets_alone',)),
]
