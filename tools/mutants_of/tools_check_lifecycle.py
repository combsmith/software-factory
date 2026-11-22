"""The mutants of `tools/check_lifecycle.py`: tools/mutants.py runs them."""

# The boundary of a person-only State (decision 0037).
LIFECYCLE_TESTS = ("tests.test_tools.Lifecycle.test_only_a_person_or_a_strangers_change_left_to_a_person_leaves_a_person_"
                   "only_state",)

ROUNDS_CEILING = ("tests.test_tools.Lifecycle.test_the_implementing_rounds_are_held_at_or_below_the_run_ceiling_and_bound_no_transition",)
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
    ("a Run ceiling of a bool holds the implementing rounds under it", "tools/check_lifecycle.py",
     'type(ceiling) is int and', 'isinstance(ceiling, int) and', ROUNDS_CEILING),
    ("a Run ceiling of a fraction holds the implementing rounds under it", "tools/check_lifecycle.py",
     'type(ceiling) is int and', 'type(ceiling) in (int, float) and', ROUNDS_CEILING),
    ("the implementing rounds may not reach the Run ceiling", "tools/check_lifecycle.py",
     'and 1 <= value <= ceiling):', 'and 1 <= value < ceiling):', ROUNDS_CEILING),
    ("the implementing rounds may not be one", "tools/check_lifecycle.py",
     'and 1 <= value <= ceiling):', 'and 2 <= value <= ceiling):', ROUNDS_CEILING),
    ("the implementing rounds may be a fraction", "tools/check_lifecycle.py",
     'if not (type(value) is int and', 'if not (type(value) in (int, float) and', ROUNDS_CEILING),
    ("a transition may be bound by the implementing rounds", "tools/check_lifecycle.py",
     '            "max_unmerged_closes")\n# The counts whose', '            "max_unmerged_closes", "max_implementing_rounds")\n# The counts whose',
     ROUNDS_CEILING),
    ("the implementing rounds may pass the Run ceiling", "tools/check_lifecycle.py",
     'and 1 <= value <= ceiling):', 'and 1 <= value):', ROUNDS_CEILING),
    ("the implementing rounds may be none", "tools/check_lifecycle.py",
     'and 1 <= value <= ceiling):', 'and value <= ceiling):', ROUNDS_CEILING),
    ("the implementing rounds may be a bool", "tools/check_lifecycle.py",
     'if not (type(value) is int and', 'if not (isinstance(value, int) and', ROUNDS_CEILING),
]
