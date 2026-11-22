"""The mutants of `tools/needs_passed.py`: tools/mutants.py runs them."""

TARGETS = ("tools/needs_passed.py",)
MUTANTS = [
    # Issue 388: each run: step stops under a limit of its own, the steps together below their job's.
    ("a needed job that did not pass passes the required check", "tools/needs_passed.py",
     '        if result != "success":\n', '        if result in ("failure", None):\n', ("tests.test_tools.Workflows.test_the_required_check_fails_unless_every_job_it_needs_passed",)),
    ("needs that name no job pass the required check", "tools/needs_passed.py",
     "    if not isinstance(needs, dict) or not needs:\n", "    if not isinstance(needs, dict):\n",
     ("tests.test_tools.Workflows.test_the_required_check_fails_unless_every_job_it_needs_passed",)),
    ("needs that cannot be read pass the required check", "tools/needs_passed.py",
     '        return ["NEEDS cannot be read as JSON; give it ${{ toJSON(needs) }} in the job\'s env"]\n',
     "        return []\n", ("tests.test_tools.Workflows.test_the_required_check_fails_unless_every_job_it_needs_passed",)),
]
