"""The mutants of `tools/verify.py`: tools/mutants.py runs them."""

from tools.mutants_of.common import MAIN_ROWS

# Issue 1109: the test of the size note make checks prints.
DESK_NOTE = ("tests.test_tools.Desk.test_make_checks_note_fails_nothing",)
ENDS = ("tests.test_tools.Verify.test_a_test_module_that_ends_its_process_cannot_pass_a_failed_check",)
ISOLATED = ("tests.test_tools.Verify.test_a_file_at_the_top_named_as_a_standard_module_is_not_imported_by_the_checks",)
LEG_TESTS = ("tests.test_tools.Verify.test_the_legs_of_make_verify_run_every_test_once",)

TARGETS = ("tools/verify.py",)
MUTANTS = [
    # Issue 1109: make checks prints the desk's size note, and nothing the note does fails it.
    ('a closed pipe ends make checks', 'tools/verify.py',
     '        try:\n            print("%-22s %s" % ("diff size", desk_note()), flush=True)\n        except BaseException:       # NOSONAR: a closed pipe too; the note never decides make checks\' answer\n            quiet(sys.stdout)\n', '        print("%-22s %s" % ("diff size", desk_note()), flush=True)\n', DESK_NOTE),
    ('a closed pipe ends make checks at exit', 'tools/verify.py',
     '            os.dup2(null, fd)\n', '            pass\n', DESK_NOTE),
    ('the note is held for the flush at exit', 'tools/verify.py',
     'desk_note()), flush=True)', 'desk_note()))', DESK_NOTE),
    ("the stream's own number is closed", 'tools/verify.py',
     '        if null != fd:', '        if True:', DESK_NOTE),
    ('a stream with no file ends make checks', 'tools/verify.py',
     '    except BaseException:       # NOSONAR: a stream with no file too', '    except AttributeError:       # NOSONAR: a stream with no file too', DESK_NOTE),
    ("a note that failed sends what the checks printed to the null device", 'tools/verify.py',
     '        stream.flush()      # a failure that is no closed pipe', '        raise OSError      # a failure that is no closed pipe',
     DESK_NOTE),
    ('a stream that cannot be written is left to fail at exit', 'tools/verify.py',
     "    except BaseException:       # NOSONAR: a closed pipe; the note never decides make checks' answer\n        pass\n",
     "    except BaseException:       # NOSONAR: a closed pipe; the note never decides make checks' answer\n        return\n",
     DESK_NOTE),
    ('a stream healthy again is pointed at the null device', 'tools/verify.py',
     '        stream.flush()      # a failure that is no closed pipe, an encoding say, leaves the checks\' output to go out\n        return\n',
     '        stream.flush()      # a failure that is no closed pipe, an encoding say, leaves the checks\' output to go out\n',
     DESK_NOTE),
    ('only a closed pipe is caught when the flush fails', 'tools/verify.py',
     "    except BaseException:       # NOSONAR: a closed pipe; the note never decides make checks' answer\n        pass\n",
     "    except BrokenPipeError:       # NOSONAR: a closed pipe; the note never decides make checks' answer\n        pass\n",
     DESK_NOTE),
    ('a note that exits ends make checks', 'tools/verify.py',
     '    except BaseException as err:', '    except Exception as err:', DESK_NOTE),
    ('make checks says nothing of the size', 'tools/verify.py',
     '        try:\n            print("%-22s %s" % ("diff size", desk_note()), flush=True)\n        except BaseException:       # NOSONAR: a closed pipe too; the note never decides make checks\' answer\n            quiet(sys.stdout)\n', '', DESK_NOTE),
    ("CI's legs run the note", 'tools/verify.py',
     '"%-22s %s" % ("boundary mutants", check_decisions.unnamed())]', '"%-22s %s" % ("boundary mutants", check_decisions.unnamed()), desk_note()]', DESK_NOTE),
    ('verify says nothing of the mutants', 'tools/verify.py',
     ',\n            "%-22s %s" % ("boundary mutants", check_decisions.unnamed())]\n', ']\n', MAIN_ROWS),
    # The legs of `make verify` (2026-11-09: one job was cut at its step's 26 minutes in a merge group).
    ("a leg holds every test", "tools/verify.py",
     "        return unittest.TestSuite(_tests(whole)[index::count])\n", "        return whole\n", LEG_TESTS),
    ("a leg skips one test in each count", "tools/verify.py",
     "        return unittest.TestSuite(_tests(whole)[index::count])\n",
     "        return unittest.TestSuite(_tests(whole)[index::count + 1])\n", LEG_TESTS),
    ("a leg outside the count runs", "tools/verify.py",
     "    if not 0 <= int(index) < int(count):\n", "    if False:\n", LEG_TESTS),
    ("one of the pair alone is no leg", "tools/verify.py",
     "    if index is None and count is None:\n", "    if index is None or count is None:\n", LEG_TESTS),
    ("a leg CI names is not read", "tools/verify.py",
     '    sys.exit(main(sys.argv[1:], os.environ))', '    sys.exit(main(sys.argv[1:]))', LEG_TESTS),
    # Issue 613, the preflight: each dispatch of a gate set asks a few development cases first, and a broken pipeline stops it.
    ('verify leaves the gate sets unchecked', 'tools/verify.py',
     '    ("gate sets", check_gate_sets.run),\n',
     '', ('tests.test_tools.GateSets.test_a_gate_set_keeps_the_floored_criteria_and_natural_marks_main_has_held_for_its_cases',)),
    # Issue 909: six older ways past the Kernel's rules.
    ("the guards' purity is not among verify's checks", 'tools/verify.py',
     '    ("guards purity", check_purity.guards),\n',
     '', ('tests.test_tools.Purity.test_the_guards_are_held_as_the_kernel_is_and_import_themselves_alone',)),
    # Issue 438: the hooks run the checks alone, and a run that did not finish is no failure.
    ("make checks runs the tests", "tools/verify.py",
     '    if "--checks" in argv:\n', '    if False:\n', ('tests.test_tools.Verify.test_make_fast_is_verify_without_the_seeded_simulation',)),
    ("make checks passes whatever the checks found", "tools/verify.py",
     '        answer = 1 if checks_failed else 0 ', '        answer = 0 ', DESK_NOTE),
    # Issue 1050: the checks run isolated, the repo's top after the standard library, and the tests in a process of
    # their own, so a test module that ends its process cannot turn a failed check into a pass.
    ("the repo's top comes ahead of the standard library", "tools/verify.py",
     "    sys.path.append(str(ROOT))", "    sys.path.insert(0, str(ROOT))", ISOLATED),
    ("the tests run in the checks' process", "tools/verify.py",
     '    tests = tested("--fast" in argv, share)\n', '    tests = main(["--tests"] + argv, environ)\n', ENDS),
    ("a failed check passes verify when the tests pass", "tools/verify.py",
     "    return 1 if checks_failed or tests != 0 else 0\n", "    return 1 if tests != 0 else 0\n", ENDS),
    ("a failed tests' process passes verify", "tools/verify.py",
     "    return 1 if checks_failed or tests != 0 else 0\n", "    return 1 if checks_failed else 0\n", ENDS),
    ("the tests' process runs the checks", "tools/verify.py",
     '    if "--tests" in argv:', '    if False:', ('tests.test_tools.Verify.test_make_fast_is_verify_without_the_seeded_simulation',)),
    ("the tests' process is told no leg", "tools/verify.py",
     "        env.update(CHECKS_SHARD=str(share[0]), CHECKS_SHARDS=str(share[1]))\n", "        pass\n", ENDS),
    ("a failed tests' process is not read", "tools/verify.py",
     "cwd=str(ROOT), env=env, check=False).returncode", "cwd=str(ROOT), env=env, check=False) and 0", ENDS),
    ("a failed test passes make tests", "tools/verify.py",
     "        return 0 if result.wasSuccessful() else 1\n", "        return 0\n",
     ('tests.test_tools.Verify.test_make_fast_is_verify_without_the_seeded_simulation',)),
    ("make tests names no leg", "tools/verify.py",
     '        if share is not None:\n            print("%-22s leg', '        if False:\n            print("%-22s leg', LEG_TESTS),
    ("make tests prints no rule the fake GitHub has unverified", "tools/verify.py",
     "        unverified(check_trials.unverified())\n", "        pass\n",
     ("tests.test_tools.Trials.test_verify_prints_every_rule_no_fixture_grounds",)),
]
