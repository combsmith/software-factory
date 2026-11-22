"""The mutants of `harness/eval/canary.py`: tools/mutants.py runs them."""

CANARY_APART = ("tests.test_evals.EvalJob.test_the_canarys_head_is_apart_from_its_case",)

TARGETS = ("harness/eval/canary.py",)
MUTANTS = [
    # Decision 0106: the CLI runs with its scrub on, and the check that says so runs what the jobs hold.
    ('the canary installs a block of its own', 'harness/eval/canary.py',
     '"\\n".join(check_workflows.CLI_INSTALL_RUN)', '"\\n".join(check_workflows.CLI_INSTALL_RUN[:-1])', ("tests.test_evals.EvalJob.test_the_canary_installs_the_block_the_jobs_hold",)),
    ('the canary installs at no pin', 'harness/eval/canary.py',
     'dict(env, CLI_VERSION=version, CLI_CHECKSUM=check_workflows.CLI_CHECKSUMS[version])', 'dict(env)', ("tests.test_evals.EvalJob.test_the_canary_installs_the_block_the_jobs_hold",)),
    ('the canary is green on a failed CLI', 'harness/eval/canary.py',
     'return 0 if status in engine.ENGINE_WRITES else 1', 'return 0', ("tests.test_evals.EvalJob.test_the_canary_is_red_unless_the_cli_answered",)),
    ('the canary is green on no answer', 'harness/eval/canary.py',
     'status = results[0].get("status") if results else None', 'status = results[0].get("status") if results else "completed"', ("tests.test_evals.EvalJob.test_the_canary_is_red_unless_the_cli_answered",)),
    ('the canary is red on a model that refused', 'harness/eval/canary.py',
     'return 0 if status in engine.ENGINE_WRITES else 1', 'return 0 if status == "completed" else 1',
     ("tests.test_evals.EvalJob.test_the_canary_is_red_unless_the_cli_answered",)),
    ('the canary prints a healthy CLI', 'harness/eval/canary.py', 'if done.returncode != 0:', 'if True:',
     ("tests.test_evals.EvalJob.test_the_canary_is_red_unless_the_cli_answered",)),
    ('the canary hides what the CLI said', 'harness/eval/canary.py',
     'told(call), clock, pathlib.Path(unpacked))', 'call, clock, pathlib.Path(unpacked))', ("tests.test_evals.EvalJob.test_the_canary_is_red_unless_the_cli_answered",)),
    ('the canary says all the CLI said', 'harness/eval/canary.py',
     'said[-TAIL:]', 'said', ("tests.test_evals.EvalJob.test_the_canary_is_red_unless_the_cli_answered",)),
    # Issue 626: the scratch is read part by part, the plan makes the heads folder new, and the canary's head is apart.
    ("the canary unpacks its head beside its case", 'harness/eval/canary.py',
     'tempfile.TemporaryDirectory() as unpacked:', 'tempfile.TemporaryDirectory(dir=scratch) as unpacked:', CANARY_APART),
    # Decision 0106: a fault of the Engine or the Factory is never the reviewer's.
    ('the canary prints the credential', 'harness/eval/canary.py',
     'done.stderr.replace(env[engine.CREDENTIAL_NAME], "***")', 'done.stderr', ("tests.test_evals.EvalJob.test_the_canary_is_red_unless_the_cli_answered",)),
    ('the canary slices before it takes the credential out', 'harness/eval/canary.py',
     """said = done.stderr.replace(env[engine.CREDENTIAL_NAME], "***")\n            print("the CLI exited %d: %s" % (done.returncode, said[-TAIL:]))""",
     """said = done.stderr[-TAIL:].replace(env[engine.CREDENTIAL_NAME], "***")\n            print("the CLI exited %d: %s" % (done.returncode, said))""",
     ("tests.test_evals.EvalJob.test_the_canary_is_red_unless_the_cli_answered",)),
]
