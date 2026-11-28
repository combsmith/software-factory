"""The step before the advise step, `harness/unasked.py`: the Run says that no advisory reader was asked (decision 0224).

Nothing here reaches the network."""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest

from harness import shared, steps, unasked
from tools import jsonschema_lite

RUN = "r_01JA7Q"
ATTEMPT = "GITHUB_RUN_ATTEMPT"
NAME = "sf combsmith/software-factory#12 review-change pr-review sha256:abcd " + RUN


class Unasked(unittest.TestCase):
    def test_the_first_step_says_no_reader_was_asked_and_never_fails_its_job(self):
        nothing = {"schema": "advice-cost/1", "run": RUN, "attempt": 1, "release": "factory/v1.2.3", "asks": 0,
                   "cost_usd": 0}

        def tagged() -> str:
            return "factory/v1.2.3"
        # From the run-name alone and the checkout's one Release tag: on its command line, or as the workflow hands it.
        for argv, environ, out in (([NAME, "cost"], {ATTEMPT: "1"}, "cost"),
                                   ([], {"NAME": NAME, "ITEM": "x", "PASS": "y", ATTEMPT: "1"}, "advice")):
            with tempfile.TemporaryDirectory() as where:
                base = pathlib.Path(where)
                self.assertEqual(unasked.job(argv, environ, base=base, release=tagged), "advice-cost.json asks 0")
                self.assertEqual((os.listdir(base), os.listdir(base / out)), ([out], ["advice-cost.json"]))
                self.assertEqual(json.loads((base / out / "advice-cost.json").read_text()), nothing)
                self.assertEqual(jsonschema_lite.validate(nothing, shared.SCHEMAS["advice-cost"], schemas=shared.SCHEMAS), [])
                # It writes into a folder of its own, made new, and never over what is there.
                with self.assertRaisesRegex(steps.Stop, "^out_exists$"):
                    unasked.job(argv, environ, base=base, release=lambda: "factory/v9.9.9")
                self.assertEqual(json.loads((base / out / "advice-cost.json").read_text()), nothing)

        # A re-run says the same of its own attempt, which GitHub numbers as the run keeps its id.
        for said, attempt in (("2", 2), ("100", 100), ("37", 37)):
            with tempfile.TemporaryDirectory() as where:
                unasked.job([NAME, "advice"], {ATTEMPT: said}, base=where, release=tagged)
                written = json.loads((pathlib.Path(where) / "advice" / "advice-cost.json").read_text())
                self.assertEqual(written, dict(nothing, attempt=attempt))

        def untagged() -> str:
            raise steps.Stop("release_untagged")
        # A run-name that is none, a checkout no one Release tag names, or a name that is no Release's: nothing is made.
        with tempfile.TemporaryDirectory() as where:
            for name, release, code in ((NAME + " x", tagged, "run_name_unreadable"), (None, tagged, "run_name_unreadable"),
                                        (NAME, untagged, "release_untagged"), (NAME, lambda: "main", "cost_unwritable")):
                with self.assertRaisesRegex(steps.Stop, "^%s$" % code):
                    unasked.job([name, "advice"], {ATTEMPT: "1"}, base=where, release=release)
            self.assertEqual(os.listdir(where), [])
            # An attempt that cannot be read is never taken for the first: no cost is written, and the pass counts the
            # Run's worst case (the Factory Builder, 2026-11-28).
            for environ in ({}, {ATTEMPT: ""}, {ATTEMPT: "0"}, {ATTEMPT: "101"}, {ATTEMPT: "01"}, {ATTEMPT: "1.0"},
                            {ATTEMPT: " 1"}, {ATTEMPT: "1\n"}, {ATTEMPT: "+1"}, {ATTEMPT: "-1"}, {ATTEMPT: "\u0661"},
                            {ATTEMPT: "1000"}, {ATTEMPT: 1}, {ATTEMPT: None}, {"github_run_attempt": "1"}):
                with self.assertRaisesRegex(steps.Stop, "^attempt_unreadable$"):
                    unasked.job([NAME, "advice"], environ, base=where, release=tagged)
                self.assertEqual(unasked.attempt_of(environ), None, environ)
            self.assertEqual(os.listdir(where), [])
            # And whatever stops it, a refusal of its own or a fault it did not foresee, the job goes on.
            here = os.getcwd()
            self.addCleanup(os.chdir, here)
            os.chdir(where)
            for argv in (["not a name", "advice"], ["a", "b", "c"], []):
                self.assertEqual(unasked.main(argv, {}), 0, argv)
            os.chdir(here)
            self.assertEqual(os.listdir(where), [])


if __name__ == "__main__":
    unittest.main()
