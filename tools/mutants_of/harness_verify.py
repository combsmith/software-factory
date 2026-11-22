"""The mutants of `harness/verify.py`: tools/mutants.py runs them."""

TARGETS = ("harness/verify.py",)
MUTANTS = [
    # Muse's read of #194's PR 3.
    ('a Result of other bytes is verified', 'harness/verify.py',
     'if "sha256:" + hashlib.sha256(data).hexdigest() != reported:',
     'if False:', ('tests.test_steps.Verify.test_verify_takes_the_results_digest',)),
    ('verify takes a digest of any form', 'harness/verify.py',
     '    if not isinstance(reported, str) or not DIGEST.fullmatch(reported):\n        raise Stop("digest_unreadable")\n',
     '', ('tests.test_steps.Verify.test_verify_takes_the_results_digest',)),
    ('verify takes what is no Result', 'harness/verify.py',
     '    if shared.errors(result, "result"):\n        raise Stop("result_unreadable")\n',
     '', ('tests.test_steps.Verify.test_verify_takes_the_results_digest',)),
    # Muse's read of #330.
    ('verify names no Release of its own', 'harness/verify.py',
     '    release = steps.release()\n    reported = environ.get("RUN_DIGEST")',
     '    release = "factory/v9.9.9"\n    reported = environ.get("RUN_DIGEST")', ('tests.test_steps.Verify.test_verify_takes_the_results_digest',)),
    ('verify takes a Result of another Release', 'harness/verify.py',
     '    if result["release"] != release:\n        raise Stop("release_differs")\n',
     '', ('tests.test_steps.Verify.test_verify_takes_the_results_digest',)),
]
