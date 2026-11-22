"""The mutants of `controller/configuration.py`: tools/mutants.py runs them."""

TARGETS = ("controller/configuration.py",)
MUTANTS = [
    # A change to a path only a person decides waits under its own code (issue 746, decision 0207).
    ('the Controller gives the Kernel no person-only path', 'controller/configuration.py',
     '    held["person_only_paths"] = person_only(hooks, held["required_lenses"]["model"])\n',
     '    held["person_only_paths"] = []\n',
     ('tests.test_controller.Feed.test_the_kernel_is_given_the_paths_only_a_person_decides_from_the_releases_own_list',)),
    ("the Controller gives the Kernel the lists of the session's checkout, not the Release's", 'controller/configuration.py',
     '    hooks = protected.load(root / "config" / "hooks.json")\n',
     '    hooks = protected.load()\n',
     ('tests.test_controller.Feed.test_the_kernel_is_given_the_paths_only_a_person_decides_from_the_releases_own_list',)),
    ("the Controller leaves no model Lens's input off the person-only paths", 'controller/configuration.py',
     '    held["person_only_paths"] = person_only(hooks, held["required_lenses"]["model"])\n',
     '    held["person_only_paths"] = person_only(hooks, [])\n',
     ('tests.test_controller.Feed.test_the_kernel_is_given_the_paths_only_a_person_decides_from_the_releases_own_list',)),
    ("a path a model Lens reads is given to the Kernel as a person's alone", 'controller/configuration.py',
     '    return [path for path in dict.fromkeys(path for path, _ in hooks["person_only"]) if path not in own]\n',
     '    return [path for path in dict.fromkeys(path for path, _ in hooks["person_only"])]\n',
     ('tests.test_controller.Feed.test_a_path_a_model_lens_reads_is_never_given_as_a_persons_alone',)),
    ('a path any Lens reads is left off the person-only paths', 'controller/configuration.py',
     '    own = [path for lens, path, _ in hooks["lens_inputs"] if lens in models]\n',
     '    own = [path for lens, path, _ in hooks["lens_inputs"]]\n',
     ('tests.test_controller.Feed.test_a_path_a_model_lens_reads_is_never_given_as_a_persons_alone',)),
    ('a person-only path listed twice is given to the Kernel twice', 'controller/configuration.py',
     '    return [path for path in dict.fromkeys(path for path, _ in hooks["person_only"]) if path not in own]\n',
     '    return [path for path, _ in hooks["person_only"] if path not in own]\n',
     ('tests.test_controller.Feed.test_a_path_a_model_lens_reads_is_never_given_as_a_persons_alone',)),
    # Issue 305: each stored credential's age read, and one alert near its limit (L-37).
    ('credentials that are not JSON stop the pass', 'controller/configuration.py',
     '    except (OSError, ValueError):\n        return None', '    except OSError:\n        return None', ('tests.test_controller.Feed.test_a_credential_near_its_limit_raises_one_alert',)),
    ('a pass is told no credentials', 'controller/configuration.py',
     '            "credentials": _readable(root, "config", "credential-ages.json")}', '            "credentials": None}', ('tests.test_controller.Feed.test_a_credential_near_its_limit_raises_one_alert',)),
]
