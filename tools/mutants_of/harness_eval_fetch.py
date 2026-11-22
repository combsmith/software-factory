"""The mutants of `harness/eval/fetch.py`: tools/mutants.py runs them."""

TARGETS = ("harness/eval/fetch.py",)
MUTANTS = [
    # Astra's second read of 0138: `--`, a list option's second value, an option dropped from WIDER, a dangling pax header.
    ("the eval reads the heads with the home's token", 'harness/eval/fetch.py',
     '    return fetch(env, root, workspace, transport(env), github.Live.anonymous())',
     '    return fetch(env, root, workspace, transport(env), transport(env))', ('tests.test_evals.EvalJob.test_each_cases_head_is_read_with_no_credential_and_one_not_read_closes_the_gate',)),
    # Decision 0106: a fault of the Engine or the Factory is never the reviewer's.
    ('a token that cannot be read is sent', 'harness/eval/fetch.py',
     '    try:\n        return ReadOnly(github.Live(env.get("HELDOUT_TOKEN")))\n    except github.Unanswered:\n        raise Stop("token_unreadable") from None\n',
     '    return ReadOnly(github.Live(env.get("HELDOUT_TOKEN") or "x"))\n', ('tests.test_evals.EvalJob.test_the_fetch_step_takes_its_token_from_its_environment_alone',)),
    ("the Maintainer's token may write", 'harness/eval/fetch.py',
     ' or req.get("method") != "GET" or',
     ' or', ('tests.test_evals.EvalJob.test_the_fetch_step_takes_its_token_from_its_environment_alone',)),
    ("the Maintainer's token may send a body", 'harness/eval/fetch.py',
     ' or req.get("body") is not None:',
     ':', ('tests.test_evals.EvalJob.test_the_fetch_step_takes_its_token_from_its_environment_alone',)),
    ("the Maintainer's token is used unwrapped", 'harness/eval/fetch.py',
     '        return ReadOnly(github.Live(',
     '        return (github.Live(', ('tests.test_evals.EvalJob.test_the_fetch_step_takes_its_token_from_its_environment_alone',)),
]
