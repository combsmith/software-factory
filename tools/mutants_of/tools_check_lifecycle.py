"""The mutants of `tools/check_lifecycle.py`: tools/mutants.py runs them."""

# The boundary of a person-only State (decision 0037).
LIFECYCLE_TESTS = ("tests.test_tools.Lifecycle.test_only_a_person_or_a_strangers_change_left_to_a_person_leaves_a_person_"
                   "only_state",)

TARGETS = ("tools/check_lifecycle.py",)
MUTANTS = [
    # Decision 0037: a person-only State is left by a person, or by a stranger's change left to a person.
    ("the platform leaves a State only a person leaves", "tools/check_lifecycle.py",
     'tr["by"] not in ("human", STRANGER):', 'tr["by"] not in ("human", STRANGER, "platform"):', LIFECYCLE_TESTS),
    ("a stranger's change left to a person may not leave a person-only State", "tools/check_lifecycle.py",
     'tr["by"] not in ("human", STRANGER):', 'tr["by"] != "human":', LIFECYCLE_TESTS),
    ("a stranger's change need name no bound", "tools/check_lifecycle.py",
     '        if tr["by"] == STRANGER and tr["bound"] != PERSON:\n', "        if False:\n", LIFECYCLE_TESTS),
    ("a stranger's change may not name the bound person", "tools/check_lifecycle.py",
     ' and tr["by"] != STRANGER:\n', ":\n", LIFECYCLE_TESTS),
]
