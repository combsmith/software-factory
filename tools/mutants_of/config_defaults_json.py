"""The mutants of `config/defaults.json`: tools/mutants.py runs them."""

TARGETS = ("config/defaults.json",)
MUTANTS = [
    # Carbon's read of #827: the other sides of the implementing rule, and its dormancy.
    ("the author Role is named before the implementing rule's reads", "config/defaults.json",
     '"author_role": null,', '"author_role": "dev-lead",',
     ("tests.test_issue.Outcomes.test_no_author_role_is_named_while_the_implementing_rule_is_owed_its_reads",)),
    # Not the old line, `rv["by"]["name"] == config["approver"]`: readable_actor holds that name to the machine user
    # and the machine user to it, so put back it would be an equivalent mutant, which no test can notice.
    ("a Lens is read from another workflow file", "config/defaults.json",
     '"workflow": ".github/workflows/verify.yml"', '"workflow": ".github/workflows/ci.yml"',
     ("tests.test_decide.Acceptance",)),
    # On a pull request the shards decline; on a merge group every shard runs.
    ("a neutral check is read as passing", "config/defaults.json",
     '"neutral": "unreadable"', '"neutral": "passing"', ("tests.test_decide.Classes",)),
    ("a neutral check is read as failing", "config/defaults.json",
     '"neutral": "unreadable"', '"neutral": "failing"', ("tests.test_decide.Content",)),
    ("a timed-out check is read as no verdict", "config/defaults.json",
     '"timed_out": "failing"', '"timed_out": "unreadable"', ("tests.test_decide.Content",)),
    ("a running check is read as passing", "config/defaults.json",
     '"in_progress": "pending"', '"in_progress": "passing"', ("tests.test_decide.Content",)),
    # Issue 675: no author Role is named until its manifest exists, and a named Role has one.
    ("the configuration names an author Role with no manifest", "config/defaults.json",
     '  "author_role": null,\n', '  "author_role": "dev-lead",\n',
     ("tests.test_decide.Ceilings.test_the_configuration_names_no_author_role_until_its_manifest_exists",)),
]
