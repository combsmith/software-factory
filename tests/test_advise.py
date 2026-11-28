"""The advise step, `harness/advise.py`, and the step before it, `harness/unasked.py`: each advisory Lens's reader is
asked and its Result written (decision 0224).

Nothing here reaches the network: the transport is a stand-in that keeps what it was sent and answers from a list."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import tempfile
import unittest

from adapters import azure
from harness import advise, shared, steps, unasked
from tools import jsonschema_lite

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN = "r_01JA7Q"
ATTEMPT = "GITHUB_RUN_ATTEMPT"
NAME = "sf combsmith/software-factory#12 review-change pr-review sha256:abcd " + RUN
FOUND = {"severity": "major", "category": "functional", "criterion": "PR-3", "file": "kernel/derive.py", "line": 88,
         "title": "A deferral is returned", "message": "`decide` defers on a whole read."}


def config() -> dict:
    return json.loads((ROOT / "config" / "harness.json").read_text())


def said(*findings) -> str:
    return json.dumps({"schema": "advice-answer/1", "findings": list(findings)})


def response(state: str = "completed", text: str = None, status: int = 200, headers: dict = None, model: str = None) -> dict:
    model = config()["readers"]["astra"]["model"] if model is None else model
    body = {"id": "resp_1", "status": state, "model": model, "usage": {"input_tokens": 1000, "output_tokens": 500},
            "output": [{"type": "message", "content": [{"type": "output_text", "text": said(FOUND) if text is None else text}]}]}
    return {"status": status, "headers": headers or {}, "body": body}


def completion(text: str = None) -> dict:
    body = {"model": config()["readers"]["kimi"]["model"], "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
            "choices": [{"finish_reason": "stop", "message": {"content": said() if text is None else text}}]}
    return {"status": 200, "headers": {}, "body": body}


KEYED = {"ADVISORY_AZURE_KEY": "k" * 32}

class Azure:
    """A stand-in for `azure.Live`: it keeps how it was made and what it was sent, and answers in turn, or as a
    function of the request."""

    def __init__(self, answers):
        self.answers, self.made, self.sent = answers if callable(answers) else list(answers), [], []

    def __call__(self, host, key, seconds):
        self.made.append((host, key, seconds))
        return self

    def send(self, request: dict) -> dict:
        self.sent.append(request)
        answer = self.answers(request) if callable(self.answers) else self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


class Clock:
    def __init__(self):
        self.now, self.slept = 0.0, []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds) -> None:
        self.slept.append(seconds)
        self.now += seconds


def folder(base: pathlib.Path, ask=True, intent: str = "review-change", change=None, diff: bytes = b"diff --git a/x b/x\n",
           rules=None, run: str = RUN) -> None:
    """The reader's folder for one review of the example's pull request."""
    record = json.loads((ROOT / "examples" / "pass.json").read_text())
    entry = record["pull_requests"][0]
    entry["decision"]["admit"]["intent"] = intent
    if ask is not None:
        entry["advisory_ask"] = ask
    facts = dict(json.loads((ROOT / "examples" / "facts.json").read_text()), **(change or {}))
    task = base / "task"
    task.mkdir()
    (task / "record.json").write_text(json.dumps(record))
    (task / "facts.json").write_text(json.dumps(facts))
    (task / "run").write_text(run + "\n")
    (task / "diff").write_bytes(diff)
    if rules is not None:
        (task / "rules.json").write_text(rules if isinstance(rules, str) else json.dumps(rules))


def release_of(base: pathlib.Path, readers) -> pathlib.Path:
    """A Release's files as the step reads them, with its configuration changed by `readers`."""
    root = base / "release"
    (root / "config").mkdir(parents=True)
    (root / "roles" / "pr-review").mkdir(parents=True)
    shutil.copy(ROOT / "roles" / "pr-review" / "advisory-reader.md", root / "roles" / "pr-review")
    changed = config()
    readers(changed)
    (root / "config" / "harness.json").write_text(json.dumps(changed))
    return root


def cost_in(base: pathlib.Path) -> dict:
    cost = json.loads((base / "advice" / "advice-cost.json").read_text())
    assert jsonschema_lite.validate(cost, shared.SCHEMAS["advice-cost"], schemas=shared.SCHEMAS) == []
    return cost


def advised(answers, env=None, first: bool = False, readers=None, **made) -> tuple:
    """`({lens: Result}, the stand-in, the clock)` of one run of the step, each Result held to advice/1 and its digest.
    With `first`, `harness.unasked` runs before it, as in the workflow."""
    with tempfile.TemporaryDirectory() as where:
        base = pathlib.Path(where)
        folder(base, **made)
        clock = Clock()
        stand_in = Azure(answers)
        if first:
            unasked.job([NAME, "advice"], {ATTEMPT: "1"}, base=base, release=lambda: "factory/v0.3.1")
            stand_in.before = cost_in(base)
        root = ROOT if readers is None else release_of(base, readers)
        written = advise.job("task", "advice", KEYED if env is None else env, root=root, base=base, transport=stand_in,
                             clock=clock, sleep=clock.sleep)
        results = {}
        for lens, digest in written:
            data = (base / "advice" / ("advice.%s.json" % lens)).read_bytes()
            assert digest == "sha256:" + hashlib.sha256(data).hexdigest()
            assert (base / "advice" / ("advice.%s.sha256" % lens)).read_text() == digest + "\n"
            results[lens] = json.loads(data)
            assert jsonschema_lite.validate(results[lens], shared.SCHEMAS["advice"], schemas=shared.SCHEMAS) == []
        there = sorted(p.name for p in (base / "advice").iterdir())
        stand_in.cost = cost_in(base) if "advice-cost.json" in there else None
        assert there == sorted(["advice.%s.%s" % (lens, kind) for lens in results for kind in ("json", "sha256")]
                               + ["advice-cost.json"] * (stand_in.cost is not None))
        return results, stand_in, clock


def codes(results: dict) -> dict:
    return {lens: (r["status"], r["reason"], len(r["findings"]), r["usage"]["asks"]) for lens, r in results.items()}


BOTH = {"astra": ("completed", None, 1, 1), "kimi": ("completed", None, 0, 1)}


class Advise(unittest.TestCase):
    def test_each_reader_configured_is_asked_once_with_no_tool_and_its_result_written(self):
        results, azure_, _ = advised([response("queued", ""), response("in_progress", ""), response(), completion()],
                                     rules={"AGENTS.md": "The rules.", "x": 7})
        self.assertEqual(codes(results), BOTH)
        readers = config()["readers"]
        # Each is reached at its own host with the step's one key, and a wait no longer than its own seconds.
        self.assertEqual(azure_.made, [(readers["astra"]["host"], "k" * 32, readers["astra"]["seconds"]),
                                       (readers["kimi"]["host"], "k" * 32, readers["kimi"]["seconds"])])
        create, first, second, chat = azure_.sent       # and a response that ended is not cancelled
        self.assertEqual((create["act"], first, second, chat["act"]),
                         ("create", azure.read("resp_1"), azure.read("resp_1"), "chat"))
        # One prompt, the cap, the effort, in the background; no tool, no file, nothing else.
        self.assertEqual(sorted(create["body"]), ["background", "input", "max_output_tokens", "model", "reasoning", "store"])
        self.assertEqual((create["body"]["model"], create["body"]["max_output_tokens"], create["body"]["reasoning"]),
                         (readers["astra"]["deployment"], readers["astra"]["output_tokens"], {"effort": "max"}))
        self.assertEqual((create["body"]["background"], create["body"]["store"]), (True, True))
        self.assertEqual(sorted(chat["body"]), ["max_completion_tokens", "messages", "model", "reasoning_effort"])
        self.assertEqual(chat["body"]["messages"][0]["content"], create["body"]["input"])
        self.assertEqual((chat["body"]["reasoning_effort"], results["kimi"]["usage"]["effort"]), ("max", "max"))
        self.assertEqual(results["astra"]["findings"][0]["location"], {"path": "kernel/derive.py", "start_line": 88})
        self.assertEqual(results["astra"]["usage"]["effort"], "max")       # the example's change touches the Kernel
        each = [results[lens]["usage"]["cost_usd"] for lens in ("astra", "kimi")]
        self.assertTrue(all(cost > 0 for cost in each))
        elsewhere, azure_, _ = advised([response(), completion()],
                                       change={"changed_paths": [{"path": "docs/glossary.md", "previous": None}]})
        self.assertEqual((elsewhere["astra"]["usage"]["effort"], azure_.sent[1]["body"]["reasoning_effort"]), ("xhigh", "xhigh"))
        moved, _, _ = advised([response(), completion()],
                              change={"changed_paths": [{"path": "docs/derive.md", "previous": "kernel/derive.py"}]})
        self.assertEqual(moved["astra"]["usage"]["effort"], "max")

    def test_the_rules_and_the_diff_follow_the_instruction_as_data(self):
        _, azure_, _ = advised([response(), completion()], rules={"AGENTS.md": "The rules.", "x": 7})
        prompt = azure_.sent[0]["body"]["input"]
        self.assertTrue(prompt.startswith((ROOT / "roles" / "pr-review" / "advisory-reader.md").read_text()))
        self.assertLess(prompt.index("--- AGENTS.md ---\nThe rules."), prompt.index("diff --git a/x b/x"))
        self.assertNotIn("--- x ---", prompt)       # what is no text is not sent
        # A diff that is not UTF-8 is sent, with a mark where a byte could not be read.
        results, azure_, _ = advised([response(), completion()], diff=b"diff --git a/x b/x\n+\xff\n")
        self.assertEqual(codes(results), BOTH)
        self.assertIn("diff --git a/x b/x\n+\ufffd\n", azure_.sent[0]["body"]["input"])
        # Rules that cannot be read as one object of texts, however they fail, are none; the reader is still asked.
        for rules in ("[" * 100000, "{", "[1]"):
            results, azure_, _ = advised([response(), completion()], rules=rules)
            self.assertEqual(codes(results), BOTH, rules[:3])
            self.assertIn("\n\n(none was read)\n\n", azure_.sent[0]["body"]["input"])

    def test_a_reader_is_not_asked_without_the_days_yes_a_key_or_a_prompt_that_fits(self):
        for ask in (False, None, "yes", 1):
            results, azure_, _ = advised([], ask=ask)
            self.assertEqual(codes(results), {"astra": ("incomplete", "budget", 0, 0), "kimi": ("incomplete", "budget", 0, 0)}, ask)
            self.assertEqual((azure_.made, azure_.sent), ([], []))
        for env in ({}, {"ADVISORY_AZURE_KEY": ""}, {"AZURE_OPENAI_API_KEY": "k" * 32}):
            results, azure_, _ = advised([], env=env)
            self.assertEqual(codes(results), {"astra": ("failed", "no_key", 0, 0), "kimi": ("failed", "no_key", 0, 0)}, env)
            self.assertEqual(azure_.made, [])
        # A prompt of exactly the characters a reader takes is asked, and one character more is not.
        limit = config()["readers"]["astra"]["prompt_characters"]
        _, azure_, _ = advised([response(), completion()], diff=b"")
        fits = b"+" * (limit - len(azure_.sent[0]["body"]["input"].encode("utf-8")))
        results, azure_, _ = advised([response(), completion()], diff=fits)
        self.assertEqual((codes(results), len(azure_.sent[0]["body"]["input"].encode("utf-8"))), (BOTH, limit))
        # The bound is in bytes of UTF-8, as the worst case prices it: as many characters, one of two bytes, is refused.
        for past in (fits + b"+", fits[:-1] + "\u00e9".encode("utf-8")):
            results, azure_, _ = advised([], diff=past)
            self.assertEqual(codes(results), {"astra": ("incomplete", "too_large", 0, 0), "kimi": ("incomplete", "too_large", 0, 0)})
            self.assertEqual(azure_.sent, [])
        # No reader reads a dependency's change, none reads for another Intent, and none for a Run the record does not
        # hold: nothing is written or asked.
        for made in ({"change": {"class": "dependency"}}, {"intent": "fix-findings"}, {"run": "r_01JA7X"}):
            results, azure_, _ = advised([], **made)
            self.assertEqual((results, azure_.made), ({}, []), made)

    def test_a_response_still_running_when_its_readers_share_is_spent_is_cancelled(self):
        # A response not ended when its reader's turn is spent, where only the next reader's share is left of the step,
        # is cancelled, and is that reader's own Result, `timed_out`; the next reader is still asked (trial P-78).
        kimi = config()["readers"]["kimi"]["share"]
        polls = (advise.WHOLE - kimi) // advise.POLL - 1      # astra, asked first, has the step but kimi's share
        results, azure_, clock = advised([response("queued", "")] + [response("in_progress", "")] * polls
                                         + [response("cancelled", ""), completion()])
        self.assertEqual(codes(results), {"astra": ("incomplete", "timed_out", 0, 1), "kimi": ("completed", None, 0, 1)})
        self.assertEqual(azure_.sent[-2], azure.cancel("resp_1"))
        self.assertLessEqual(clock.now, advise.WHOLE)
        turn = advise.WHOLE - kimi - advise.POLL     # astra's last read, the last that left it POLL of its turn
        self.assertEqual((results["astra"]["usage"]["seconds"], results["astra"]["usage"]["cost_usd"]), (turn, None))
        # A reader waits the time left of the step where that is less than its own seconds: kimi has its share and more.
        self.assertEqual(azure_.made[1][2], advise.WHOLE - turn)
        self.assertGreaterEqual(advise.WHOLE - turn, kimi)
        # What Azure does not answer, or this step did not foresee of it, is a code, and the next reader is still asked.
        results, azure_, _ = advised([azure.Unanswered("down"), completion()])
        self.assertEqual(codes(results), {"astra": ("failed", "transport", 0, 1), "kimi": ("completed", None, 0, 1)})
        results, _, _ = advised([response(), azure.Unanswered("down")])
        self.assertEqual(codes(results), {"astra": ("completed", None, 1, 1), "kimi": ("failed", "transport", 0, 1)})
        # An ask is counted once, however many reads of its response followed it before one was not answered.
        results, azure_, _ = advised([response("queued", ""), response("in_progress", ""), azure.Unanswered("down"),
                                      completion()])
        self.assertEqual((codes(results)["astra"], len(azure_.sent)), (("failed", "transport", 0, 1), 4))
        results, _, _ = advised([response(model="another-model"), completion("not json")])
        self.assertEqual(codes(results), {"astra": ("failed", "not_the_model", 0, 1), "kimi": ("failed", "unparsed", 0, 1)})

    def test_each_readers_turn_ends_where_only_the_shares_of_the_readers_after_it_are_left(self):  # trial P-78
        # The readers share the step's WHOLE seconds, each configured reader's share summed, asked one after another.
        shares = {lens: reader["share"] for lens, reader in config()["readers"].items()}
        self.assertEqual(advise.WHOLE, sum(shares.values()))
        self.assertEqual(advise.turn_of([{"share": 540}], 1440.0), 900.0)
        self.assertEqual(advise.turn_of([{"share": 300}, {"share": 200}], 1000.0), 500.0)
        self.assertEqual(advise.turn_of([], 1440.0), 1440.0)       # the last runs to the step's end
        # A share that cannot be read is none, so that no turn ends past the step's end and none breaks it.
        for share in (None, True, -100, 0, 1.5, "540"):
            self.assertEqual(advise.turn_of([{} if share is None else {"share": share}], 1440.0), 1440.0, share)

        def running(request: dict):
            return response("cancelled", "") if request["act"] == "cancel" else response("in_progress", "")
        last = advise.WHOLE - advise.POLL       # the last read that leaves POLL of the step
        # Kimi, asked after astra, takes its whole wait where astra ended early: the last is not held to its own share.
        results, azure_, _ = advised([response(), completion()])
        self.assertEqual((codes(results), azure_.made[-1][2]), (BOTH, config()["readers"]["kimi"]["seconds"]))
        # A reader after it that is not to be asked leaves astra the whole step.
        results, azure_, _ = advised(running, readers=lambda changed: changed["readers"]["kimi"].update(prompt_characters=1))
        self.assertEqual(codes(results), {"astra": ("incomplete", "timed_out", 0, 1), "kimi": ("incomplete", "too_large", 0, 0)})
        self.assertEqual(results["astra"]["usage"]["seconds"], last)
        # And so does one whose share cannot be read.
        for share in (None, True, "540"):
            def odd(changed, share=share):
                changed["readers"]["kimi"].pop("share")
                if share is not None:
                    changed["readers"]["kimi"]["share"] = share
            results, azure_, _ = advised(running, readers=odd)
            self.assertEqual(results["astra"]["usage"]["seconds"], last, share)

    def test_a_run_that_asks_no_longer_says_that_no_reader_was_asked(self):
        nothing = {"schema": "advice-cost/1", "run": RUN, "attempt": 1, "release": "factory/v0.3.1", "asks": 0, "cost_usd": 0}
        # A Run about to ask a reader takes away what its first step said, and the pass counts its worst case.
        results, azure_, _ = advised([response(), completion()], first=True)
        self.assertEqual((codes(results), azure_.before, azure_.cost), (BOTH, nothing, None))
        # So does one that asks one reader of two.
        results, azure_, _ = advised([completion()], first=True,
                                     readers=lambda changed: changed["readers"]["astra"].update(prompt_characters=1))
        self.assertEqual((codes(results)["kimi"][0], azure_.cost), ("completed", None))
        # A Run that asks nobody, refused before anything is sent or no review at all, leaves it as it was written.
        for made in ({"ask": False}, {"env": {}}, {"intent": "fix-findings"}, {"change": {"class": "dependency"}}):
            _, azure_, _ = advised([], first=True, **made)
            self.assertEqual((azure_.before, azure_.cost, azure_.sent), (nothing, nothing, []), made)

    def test_a_fault_in_one_reader_is_that_readers_alone(self):
        # A fault no one foresaw in one reader is that reader's Result, and the other is still asked.
        results, azure_, _ = advised([RuntimeError("boom"), completion()])
        self.assertEqual(codes(results), {"astra": ("failed", "transport", 0, 1), "kimi": ("completed", None, 0, 1)})
        # A reader for whom not even that can be said has no Result; the other has.

        def unpinned(changed: dict) -> None:
            del changed["readers"]["astra"]["model"]
        results, azure_, _ = advised([completion()], readers=unpinned)
        self.assertEqual(codes(results), {"kimi": ("completed", None, 0, 1)})
        # Nor has one whose name `advice/1` refuses, and it is not asked: nothing is paid for an answer no Result holds.

        def renamed(changed: dict) -> None:
            changed["advisory"], changed["readers"]["kimi-2"] = ["astra", "kimi-2"], changed["readers"].pop("kimi")
        results, azure_, _ = advised([response()], readers=renamed)
        self.assertEqual((codes(results), len(azure_.sent)), ({"astra": ("completed", None, 1, 1)}, 1))

    def test_the_step_never_fails_its_job(self):
        with tempfile.TemporaryDirectory() as where:
            self.assertEqual(advise.main([where + "/no-task", where + "/out"], {}), 0)
        self.assertEqual(advise.main(["../outside", "advice"], {}), 0)
        # Nor on a fault that is no refusal of a step's: a folder with no Run in it, read where the step runs. And for
        # a Run whose Release it cannot name it makes nothing: no empty folder is left.
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        for spoil in (lambda task: (task / "run").unlink(), lambda task: (task / "record.json").write_text("{}"),
                      lambda task: (task / "record.json").write_text("[]")):
            with tempfile.TemporaryDirectory() as where:
                folder(pathlib.Path(where))
                spoil(pathlib.Path(where) / "task")
                os.chdir(where)
                self.assertEqual(advise.main(["task", "advice"], {}), 0)
                self.assertEqual(os.listdir(where), ["task"])
                # Nor does it take for its folder a file, or a link to one elsewhere.
                os.chdir(here)
        with tempfile.TemporaryDirectory() as where:
            base = pathlib.Path(where)
            folder(base)
            (base / "there").mkdir()
            for make in (lambda: (base / "advice").write_text(""), lambda: os.symlink(base / "there", base / "advice")):
                make()
                with self.assertRaisesRegex(steps.Stop, "^out_exists$"):
                    advise.job("task", "advice", {}, base=base)
                self.assertEqual(os.listdir(base / "there"), [])
                (base / "advice").unlink()
            # Nor a folder that holds anything but the first step's file, a Result or a link planted there among them,
            # nor the task's own folder; and nothing is asked.
            stand_in = Azure([])
            for plant in (lambda: [(base / "advice" / name).write_text("{}") for name in ("advice.astra.json", "advice.astra.sha256")],
                          lambda: os.symlink(base / "there", base / "advice" / "advice.kimi.json")):
                (base / "advice").mkdir()
                (base / "advice" / "advice-cost.json").write_text("{}")
                plant()
                with self.assertRaisesRegex(steps.Stop, "^out_exists$"):
                    advise.job("task", "advice", KEYED, base=base, transport=stand_in)
                shutil.rmtree(base / "advice")
            with self.assertRaisesRegex(steps.Stop, "^out_exists$"):
                advise.job("task", "task", KEYED, base=base, transport=stand_in)
            self.assertEqual(stand_in.made, [])


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
