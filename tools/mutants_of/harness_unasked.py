"""The mutants of `harness/unasked.py`: tools/mutants.py runs them."""

TARGETS = ("harness/unasked.py",)
SAYS = ("tests.test_advise.Unasked.test_the_first_step_says_no_reader_was_asked_and_never_fails_its_job",)
MUTANTS = [
    # Decision 0224: the step a Run takes before any other says that no advisory reader was asked.
    ("the first step says that a reader was asked", 'harness/unasked.py',
     '"asks": 0,\n                "cost_usd": 0}',
     '"asks": 1,\n                "cost_usd": 0}', SAYS),
    ("the first step names a Release its checkout does not", 'harness/unasked.py',
     '"release": release(),',
     '"release": "factory/v0.0.0",', SAYS),
    ("the first step writes a cost its schema refuses", 'harness/unasked.py',
     '    if shared.errors(document, "advice-cost"):\n        raise steps.Stop("cost_unwritable")\n',
     '', SAYS),
    ("the first step writes into a folder that is already there", 'harness/unasked.py',
     'steps.new_folder(os.getcwd() if base is None else base, out)',
     '(os.makedirs(os.path.join(str(base), out), exist_ok=True), os.path.join(str(base), out))[1]', SAYS),
    ("the first step fails its job", 'harness/unasked.py',
     '    except Exception as err:    # NOSONAR the step never fails its job: the Run goes on, and is counted as one that left no cost\n',
     '    except steps.Stop as err:\n', SAYS),
    # The Factory Builder, 2026-11-28: an attempt that cannot be read is never taken for the first.
    ("the first step takes an attempt it cannot read for the first", 'harness/unasked.py',
     '    if attempt is None:\n        raise steps.Stop("attempt_unreadable")\n',
     '    if attempt is None:\n        attempt = 1\n', SAYS),
    ("the first step writes every attempt as the first", 'harness/unasked.py',
     '"attempt": attempt,', '"attempt": 1,', SAYS),
    ("an attempt is read past the most a cost may name", 'harness/unasked.py',
     'NUMBER.fullmatch(said) and int(said) <= ATTEMPTS', 'NUMBER.fullmatch(said)', SAYS),
    ("an attempt is read with a leading nought", 'harness/unasked.py',
     'NUMBER = re.compile(r"[1-9][0-9]{0,2}")', 'NUMBER = re.compile(r"[0-9]{1,3}")', SAYS),
    ("an attempt is read from any digits Python reads", 'harness/unasked.py',
     'if isinstance(said, str) and NUMBER.fullmatch(said) and', 'if isinstance(said, str) and said.strip().isdigit() and', SAYS),
]
