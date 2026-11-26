"""The mutants of `sim/issues.py`: tools/mutants.py runs them."""

F849_WORLD = ("tests.test_issue.Unreadable.test_the_issue_world_meets_a_timeline_past_the_bound_under_faults_and_calls_a_person",)

F849_BROKEN_WORLD = ("tests.test_issue.Unreadable.test_the_issue_world_meets_a_broken_chain_of_spans_under_faults_and_calls_a_person",)
TARGETS = ("sim/issues.py",)
MUTANTS = [
    # Issue 1216: a head is told pushed only where a listed opening Run recorded pushing it.
    ("a planted branch is told as pushed", 'sim/issues.py',
     '            "branch_pushed": None if self.branch_head is None else self.branch_head in {\n'
     '                self.pushed.get(r["run"]) for r in self.records() if r["intent"] == issue.OPENING},\n',
     '            "branch_pushed": None if self.branch_head is None else True,\n',
     ("tests.test_issue_simulator.IssueSimulation.test_the_seeds_plant_a_branch_the_factory_never_pushed",)),
    # Issue 838: where the branch does not exist, the opening Run is admitted for the commit it lands on.
    ("the issue world serves no default branch's head", "sim/issues.py",
     '            "base_head": "%040x" % (0xba5e0000 + self.minute),\n', "",
     ("tests.test_issue_simulator.IssueSimulation.test_invariants_hold_under_faults",)),
    ("the issue world's default branch never moves", "sim/issues.py",
     '"%040x" % (0xba5e0000 + self.minute),\n', '"%040x" % 0xba5e0000,\n',
     ("tests.test_issue_simulator.IssueSimulation.test_invariants_hold_under_faults",)),
    ("the issue world's apply asks again with no base", "sim/issues.py",
     '            if run["base"] is not None:\n                admitted["admit"]["base_head"] = run["base"]\n', "",
     ("tests.test_issue_simulator.IssueSimulation.test_invariants_hold_under_faults",)),
    ("the issue world's apply forwards another base", "sim/issues.py",
     '                admitted["admit"]["base_head"] = run["base"]\n', '                admitted["admit"]["base_head"] = "f" * 40\n',
     ("tests.test_issue_simulator.IssueSimulation.test_invariants_hold_under_faults",)),
    ("the issue world keeps no base for a Run", "sim/issues.py",
     '"base": d["admit"].get("base_head")}', '"base": None}',
     ("tests.test_issue_simulator.IssueSimulation.test_invariants_hold_under_faults",)),
    ("the issue world lists a Run with the base it keeps", "sim/issues.py",
     'if k not in ("minute", "head", "base")}', 'if k not in ("minute", "head")}',
     ("tests.test_issue_simulator.IssueSimulation.test_invariants_hold_under_faults",)),
    # Issue 299: every actor's write access, in both worlds, read from the permission each serves (decision 0048).
    ("the issue world asks a person's fixed write access", 'sim/issues.py',
     'by["kind"] == "human" and told(by)["can_write"] is True',
     'by["kind"] == "human" and by["can_write"] is True', ("tests.test_issue_simulator.IssueSimulation.test_every_actors_write_access_is_read_from_the_permission",)),
    ("the issue world's facts keep each actor's fixed write access", 'sim/issues.py',
     '        return told({\n            "schema": "issue-facts/1"',
     '        return ({\n            "schema": "issue-facts/1"', ("tests.test_issue_simulator.IssueSimulation.test_every_actors_write_access_is_read_from_the_permission",)),
    # Issue 251: P-44's lane, one Run holding it and at most one waiting, kept by one function for both worlds.
    ("the issue's world queues past the lane", "sim/issues.py", "        self.enqueue(run)\n", "        self.runs.append(run)\n",
     ("tests.test_simulator.Simulation.test_a_newer_run_cancels_the_one_waiting_in_each_world",)),
    ("the issue's lane is not the shared one", "sim/issues.py", "        queue_in_lane(self.runs, run, self.note)\n",
     "        self.runs.append(run)\n", ("tests.test_simulator.Simulation.test_a_newer_run_cancels_the_one_waiting_in_each_world",)),
    # Decision 0234: an issue's timeline and its linked pull requests' are read to a bound, and past it the issue defers on
    # its own code and calls a person.
    ("the issue world never bounds a timeline", 'sim/issues.py',
     'facts["timeline_bounded"] = short in ("linked", "timeline") and fault < 0.11', 'facts["timeline_bounded"] = False', F849_WORLD),
    ("the issue world bounds only a linked read", 'sim/issues.py',
     'facts["timeline_bounded"] = short in ("linked", "timeline") and fault < 0.11', 'facts["timeline_bounded"] = short == "linked" and fault < 0.11', F849_WORLD),
    ("the issue world bounds a read it did not read short", 'sim/issues.py',
     'facts["timeline_bounded"] = short in ("linked", "timeline") and fault < 0.11', 'facts["timeline_bounded"] = short not in ("linked", "timeline") and fault < 0.11', F849_WORLD),
    ("the issue world never breaks a chain of spans", 'sim/issues.py',
     'facts["spans_broken"] = short == "linked" and 0.11 <= fault < 0.125', 'facts["spans_broken"] = False', F849_BROKEN_WORLD),
    ("the issue world breaks a chain beside a list it read whole", 'sim/issues.py',
     'facts["spans_broken"] = short == "linked" and 0.11 <= fault < 0.125', 'facts["spans_broken"] = short != "linked" and 0.11 <= fault < 0.125', F849_BROKEN_WORLD),
]
