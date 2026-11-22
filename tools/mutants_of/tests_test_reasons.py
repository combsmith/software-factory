"""The mutants of `tests/test_reasons.py`: tools/mutants.py runs them."""

TARGETS = ("tests/test_reasons.py",)
MUTANTS = [
    # Decision 0248: every reason is in one of two sets, a pull request's and an issue's own.
    ("the scan reads no choice between reasons", "tests/test_reasons.py",
     "    elif isinstance(node, ast.IfExp):\n        _give(node.body, found, unread)\n        _give(node.orelse, found, unread)\n",
     "", ("tests.test_reasons.Written.test_a_reason_written_any_way_is_read",)),
    ("the scan trusts any mapping's reason", "tests/test_reasons.py",
     'key.value == "reason" and isinstance(base, ast.Name) and base.id in HOLDERS',
     'key.value == "reason"',
     ("tests.test_reasons.Written.test_a_reason_written_any_way_is_read",)),
    ("the scan trusts a reason bound by a loop", "tests/test_reasons.py",
     '               and not isinstance(n.ctx, ast.Load) and id(n) not in bound]',
     '               and False]', ("tests.test_reasons.Written.test_a_reason_written_any_way_is_read",)),
    ("the scan trusts an attribute named as a holder", "tests/test_reasons.py",
     "isinstance(base, ast.Name) and base.id in HOLDERS", "_name(base) in HOLDERS",
     ("tests.test_reasons.Written.test_a_reason_written_any_way_is_read",)),
    ("the scan lets a reason into a parameter of another name", "tests/test_reasons.py",
     "for i, a in enumerate(node.args) if _flows(a, False) and i != slot]", "for i, a in enumerate(node.args) if False]",
     ("tests.test_reasons.Written.test_a_reason_written_any_way_is_read",)),
    ("the scan lets a reason be bound to another name", "tests/test_reasons.py",
     "    elif _flows(value):\n        unread.append(target.lineno)\n", "",
     ("tests.test_reasons.Written.test_a_reason_written_any_way_is_read",)),
]
