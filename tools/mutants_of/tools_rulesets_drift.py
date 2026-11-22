"""The mutants of `tools/rulesets_drift.py`: tools/mutants.py runs them."""

TARGETS = ("tools/rulesets_drift.py",)
MUTANTS = [
    # The record of `main` after issue 198's switch (decision 0191): each field back, and the four together, which
    # `tools/check_rulesets.py` lets through as a `main` that counts no approval.
    ("a changed rule is no drift", "tools/rulesets_drift.py",
     '                    if want["rules"].get(rule) != got["rules"].get(rule):\n', "                    if False:\n",
     ("tests.test_tools.RulesetsDrift.test_a_changed_rule_is_drift",)),
    ("a changed bypass is no drift", "tools/rulesets_drift.py",
     "            elif want.get(key) != got.get(key):\n", "            elif False:\n",
     ("tests.test_tools.RulesetsDrift.test_a_changed_bypass_or_target_is_drift",)),
    ("a ruleset not recorded is no drift", "tools/rulesets_drift.py",
     '        if name not in recorded or recorded[name].get("id") != number:\n', "        if False:\n",
     ("tests.test_tools.RulesetsDrift.test_a_ruleset_added_or_taken_away_is_drift",)),
    ("a ruleset answered other than 200 is compared", "tools/rulesets_drift.py",
     "        if status != 200 or not isinstance(body, dict):\n", "        if not isinstance(body, dict):\n",
     ("tests.test_tools.RulesetsDrift.test_an_answer_that_is_not_200_or_no_list_is_drift",)),
    ("a ruleset is known by its name alone", "tools/rulesets_drift.py",
     '        if name not in recorded or recorded[name].get("id") != number:\n', "        if name not in recorded:\n",
     ("tests.test_tools.RulesetsDrift.test_a_ruleset_sharing_a_recorded_name_is_drift",)),
    ("a rule type given twice is read once", "tools/rulesets_drift.py",
     "    if len(seen) != len(set(seen)):\n", "    if False:\n",
     ("tests.test_tools.RulesetsDrift.test_a_rule_type_given_twice_is_drift",)),
    ("any id is read into a call", "tools/rulesets_drift.py",
     ' if isinstance(r, dict) and type(r.get("id")) is int]', ' if isinstance(r, dict)]',
     ("tests.test_tools.RulesetsDrift.test_only_a_whole_number_is_an_id",)),
    ("a full page is the whole list", "tools/rulesets_drift.py",
     "    if len(listed) >= PAGE:\n", "    if False:\n",
     ("tests.test_tools.RulesetsDrift.test_a_full_page_says_more_may_follow",)),
    ("a ruleset listed and not answered is no drift", "tools/rulesets_drift.py",
     "    problems = [] if len(answers) == len(numbers) else [\n", "    problems = [] if True else [\n",
     ("tests.test_tools.RulesetsDrift.test_the_answers_are_read_from_stdin_in_the_order_listed",)),
    # Decision 0124: no branch may stand where a Channel's tag should.
    ("a branch standing under factory/ is no drift", 'tools/rulesets_drift.py',
     'dict(zip(numbers, answers))) + branches', 'dict(zip(numbers, answers)))', ('tests.test_tools.RulesetsDrift.test_a_branch_standing_under_factory_is_drift',)),
    ("branches that cannot be read are no drift", 'tools/rulesets_drift.py',
     '    if status != 200 or not isinstance(refs, list):\n', '    if not isinstance(refs, list):\n        return []\n    if False:\n', ('tests.test_tools.RulesetsDrift.test_a_branch_standing_under_factory_is_drift',)),
]
