"""The advise step, `harness/advise.py`, and the step before it, `harness/unasked.py`: each advisory Lens's reader is
asked, its Result written, and the Run's cost true wherever it stops (decision 0224).

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
from controller import advisory
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


FIRST = {"GITHUB_RUN_ATTEMPT": "1"}
KEYED = dict(FIRST, ADVISORY_AZURE_KEY="k" * 32)
LIMITED = {"status": 429, "headers": {"retry-after": "20"}, "body": {"error": {"code": "rate_limit_exceeded"}}}


class Azure:
    """A stand-in for `azure.Live`: it keeps how it was made and what it was sent, and answers in turn, or as a
    function of the request. `during` is called at each send."""

    def __init__(self, answers, during=None):
        self.answers, self.made, self.sent = answers if callable(answers) else list(answers), [], []
        self.during = during

    def __call__(self, host, key, seconds):
        self.made.append((host, key, seconds))
        return self

    def send(self, request: dict) -> dict:
        self.sent.append(request)
        if self.during:
            self.during()
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
           rules=None, run: str = RUN, drop: tuple = ()) -> None:
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
    for name in drop:
        (task / name).unlink()


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


def advised(answers, env=None, first: bool = False, readers=None, mid: bool = False, **made) -> tuple:
    """`({lens: Result}, the stand-in, the clock)` of one run of the step, each Result held to advice/1 and its digest.
    With `first`, `harness.unasked` runs before it, as in the workflow; with `mid`, the cost file is read at each send."""
    with tempfile.TemporaryDirectory() as where:
        base = pathlib.Path(where)
        folder(base, **made)
        clock = Clock()
        stand_in = Azure(answers, (lambda: stand_in.seen.append(cost_in(base))) if mid else None)
        stand_in.seen = []
        if first:
            attempt = {name: said for name, said in (KEYED if env is None else env).items() if name == ATTEMPT}
            unasked.job([NAME, "advice"], attempt, base=base, release=lambda: "factory/v0.3.1")
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
        assert sorted(p.name for p in (base / "advice").iterdir()) == sorted(
            ["advice.%s.%s" % (lens, kind) for lens in results for kind in ("json", "sha256")] + ["advice-cost.json"])
        stand_in.cost = cost_in(base)
        assert stand_in.cost["run"] == made.get("run", RUN)
        return results, stand_in, clock


def codes(results: dict) -> dict:
    return {lens: (r["status"], r["reason"], len(r["findings"]), r["usage"]["asks"]) for lens, r in results.items()}


def spent(cost) -> tuple:
    cost = getattr(cost, "cost", cost)      # the stand-in's, or the document
    return cost["asks"], cost["cost_usd"]


DOWN = {"status": 500, "headers": {"retry-after": "20"}, "body": {"error": {"code": "server_error"}}}
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
        for env in (FIRST, dict(FIRST, ADVISORY_AZURE_KEY=""), dict(FIRST, AZURE_OPENAI_API_KEY="k" * 32)):
            results, azure_, _ = advised([], env=env)
            self.assertEqual(codes(results), {"astra": ("failed", "no_key", 0, 0), "kimi": ("failed", "no_key", 0, 0)}, env)
            self.assertEqual(azure_.made, [])
        # A prompt of exactly the characters a reader takes is asked, and one character more is not.
        limit = config()["readers"]["astra"]["prompt_characters"]
        _, azure_, _ = advised([response(), completion()], diff=b"")
        fits = b"+" * (limit - len(azure_.sent[0]["body"]["input"]))
        results, azure_, _ = advised([response(), completion()], diff=fits)
        self.assertEqual((codes(results), len(azure_.sent[0]["body"]["input"])), (BOTH, limit))
        results, azure_, _ = advised([], diff=fits + b"+")
        self.assertEqual(codes(results), {"astra": ("incomplete", "too_large", 0, 0), "kimi": ("incomplete", "too_large", 0, 0)})
        self.assertEqual(azure_.sent, [])
        # No reader reads a dependency's change, none reads for another Intent, and none for a Run the record does not
        # hold: nothing is written or asked.
        for made in ({"change": {"class": "dependency"}}, {"intent": "fix-findings"}, {"run": "r_01JA7X"}):
            results, azure_, _ = advised([], **made)
            self.assertEqual((results, azure_.made), ({}, []), made)

    def test_a_rate_limit_is_waited_for_once(self):
        # The wait a rate limit names, once; a second rate limit is the Result, and nothing is asked in a loop.
        results, azure_, clock = advised([LIMITED, response(), LIMITED, LIMITED])
        self.assertEqual(codes(results), {"astra": ("completed", None, 1, 2), "kimi": ("incomplete", "rate_limited", 0, 2)})
        self.assertEqual((clock.slept, len(azure_.sent)), ([20, 20], 4))
        self.assertEqual([results[lens]["usage"]["seconds"] for lens in ("astra", "kimi")], [20.0, 20.0])
        # A wait it does not name as a short whole number, or that does not fit, is not waited for.
        for header in ("91", "soon", "-1", "1.5", "0020", "", "\uff12\uff10"):
            results, azure_, clock = advised([dict(LIMITED, headers={"retry-after": header})] * 2)
            self.assertEqual(codes(results)["astra"], ("incomplete", "rate_limited", 0, 1), header)
            self.assertEqual(clock.slept, [])
        # Only a 429 earns the second ask: an answer of any other status that names a wait is the answer.
        results, azure_, clock = advised([dict(response(), headers={"retry-after": "20"}), DOWN])
        self.assertEqual(codes(results), {"astra": ("completed", None, 1, 1), "kimi": ("failed", "transport", 0, 1)})
        self.assertEqual((clock.slept, len(azure_.sent)), ([], 2))
        # A 429 that counts tokens may have been billed, and is not asked again: a reader is billed one ask at most, as
        # the Run's worst case prices it (decision 0243).
        billed = dict(LIMITED, body=dict(LIMITED["body"], usage={"prompt_tokens": 1000, "completion_tokens": 0}))
        results, azure_, clock = advised([response(), billed, completion()])
        self.assertEqual(codes(results), {"astra": ("completed", None, 1, 1), "kimi": ("incomplete", "rate_limited", 0, 1)})
        self.assertEqual((clock.slept, [sent["act"] for sent in azure_.sent]), ([], ["create", "chat"]))
        self.assertEqual((advise.unbilled(LIMITED), advise.unbilled(billed), advise.unbilled(DOWN)), (True, False, False))
        self.assertEqual(advise.unbilled(dict(LIMITED, body=None)), True)
        # And only where the wait is less than the reader's time.
        self.assertEqual([advise.waited(LIMITED, left) for left in (20.1, 20, 5)], [20, None, None])
        self.assertEqual(advise.waited(dict(LIMITED, headers={"retry-after": "90"}), 100), 90)

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
                                      response("cancelled", ""), completion()])
        self.assertEqual((codes(results)["astra"], len(azure_.sent)), (("failed", "transport", 0, 1), 5))
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

    def test_a_response_whose_read_fails_is_cancelled_and_the_cancel_changes_nothing(self):
        # A read answered other than 200, or not answered, leaves the response running: it is cancelled, whatever the
        # cancel answers, the Result is the read's, and the one ask is counted once however many reads followed it.
        gone = azure.Unanswered("down")
        for failed, cancelled, want in ((DOWN, response("cancelled", ""), ("failed", "transport", 0, 1)),
                                        (LIMITED, DOWN, ("incomplete", "rate_limited", 0, 1)),
                                        (LIMITED, gone, ("incomplete", "rate_limited", 0, 1)),
                                        (LIMITED, RuntimeError("no"), ("incomplete", "rate_limited", 0, 1)),
                                        (gone, gone, ("failed", "transport", 0, 1))):
            results, azure_, clock = advised([response("queued", ""), response("in_progress", ""), failed, cancelled,
                                              completion()])
            self.assertEqual(codes(results), {"astra": want, "kimi": ("completed", None, 0, 1)})
            self.assertEqual([sent["act"] for sent in azure_.sent], ["create", "read", "read", "cancel", "chat"])
            self.assertEqual((azure_.sent[3], clock.slept), (azure.cancel("resp_1"), [10, 10]))
            self.assertEqual(spent(azure_), (2, None))
        # So is one in a state this step does not know to have ended; one that ended is not.
        results, azure_, _ = advised([response("paused", ""), DOWN, completion()])
        self.assertEqual((codes(results)["astra"], azure_.sent[1]), (("failed", "transport", 0, 1), azure.cancel("resp_1")))
        for state in ("failed", "cancelled", "incomplete"):
            _, azure_, _ = advised([response(state, ""), completion()])
            self.assertEqual([sent["act"] for sent in azure_.sent], ["create", "chat"], state)

    def test_a_run_that_asks_no_longer_says_that_no_reader_was_asked(self):
        nothing = {"schema": "advice-cost/1", "run": RUN, "attempt": 1, "release": "factory/v0.3.1", "asks": 0, "cost_usd": 0}
        # Before its first request the step says how many readers it is about to ask, at a cost not known, which the
        # pass counts at the worst case.
        results, azure_, _ = advised([response(), completion()], first=True, mid=True)
        self.assertEqual((codes(results), azure_.before), (BOTH, nothing))
        self.assertEqual(azure_.seen, [dict(nothing, asks=2, cost_usd=None)] * 2)
        # A reader refused before anything is sent is not among them.

        def short(changed: dict) -> None:
            changed["readers"]["kimi"]["prompt_characters"] = 10
        _, azure_, _ = advised([response()], mid=True, readers=short)
        self.assertEqual([seen["asks"] for seen in azure_.seen], [1])
        # A Run that asks nobody, refused before anything is sent or no review at all, leaves it as it was written.
        for made in ({"ask": False}, {"env": FIRST}, {"intent": "fix-findings"}, {"change": {"class": "dependency"}}):
            _, azure_, _ = advised([], first=True, **made)
            self.assertEqual((azure_.before, azure_.cost, azure_.sent), (nothing, nothing, []), made)

    def test_the_runs_cost_is_true_wherever_the_step_stops(self):
        # After its last reader the step says what was asked and what it cost, summed from each answer's tokens and the
        # prices; nothing asked costs nothing.
        results, azure_, _ = advised([response(), completion()])
        self.assertEqual(azure_.cost, {"schema": "advice-cost/1", "run": RUN, "attempt": 1, "release": results["astra"]["release"], "asks": 2,
                                       "cost_usd": round(sum(results[lens]["usage"]["cost_usd"] for lens in results), 6)})
        self.assertGreater(azure_.cost["cost_usd"], 0)
        for made in ({"ask": False}, {"drop": ("diff",)}, {"run": "r_01JA7X"}):
            self.assertEqual(spent(advised([], **made)[1]), (0, 0), made)
        # A reader that was asked and gives no count makes the Run's cost unknown, never the others' sum or nought:
        # each ask is counted, and so is the ask of a reader whose read raised what no one foresaw.
        self.assertEqual(spent(advised([LIMITED, response(), LIMITED, LIMITED])[1]), (4, None))
        self.assertEqual(spent(advised([RuntimeError("boom"), completion()])[1]), (2, None))
        with tempfile.TemporaryDirectory() as where:
            base = pathlib.Path(where)
            # A step stopped from outside while a reader is asked has counted the ask, at a cost not known.
            folder(base)
            with self.assertRaises(KeyboardInterrupt):
                advise.job("task", "advice", KEYED, base=base, transport=Azure([KeyboardInterrupt()]))
            self.assertEqual(spent(cost_in(base)), (1, None))
        with tempfile.TemporaryDirectory() as where:
            base = pathlib.Path(where)
            # A Run whose id is none is not named: nothing is made for it.
            folder(base, run="a run")
            with self.assertRaisesRegex(steps.Stop, "^run_unnamed$"):
                advise.job("task", "advice", FIRST, base=base)
            self.assertEqual(os.listdir(base), ["task"])
            # A Run that is named and whose facts cannot be read asked nobody, and says so.
            (base / "task" / "run").write_text(RUN + "\n")
            (base / "task" / "facts.json").unlink()
            with self.assertRaises(steps.Stop):
                advise.job("task", "advice", FIRST, base=base)
            self.assertEqual((os.listdir(base / "advice"), spent(cost_in(base))), (["advice-cost.json"], (0, 0)))
            # The file is replaced whole: nothing is left beside it, a link in its place is not followed, and what a
            # stopped step left beside it is no obstacle.
            (base / "task" / "facts.json").write_text((ROOT / "examples" / "facts.json").read_text())
            (base / "advice" / "advice-cost.json").unlink()
            (base / "elsewhere").write_text("kept")
            os.symlink(base / "elsewhere", base / "advice" / "advice-cost.json")
            os.symlink(base / "elsewhere", base / "advice" / "advice-cost.json.new")
            stand_in, clock = Azure([response(), completion()]), Clock()
            advise.job("task", "advice", KEYED, base=base, transport=stand_in, clock=clock, sleep=clock.sleep)
            self.assertEqual(((base / "elsewhere").read_text(), (base / "advice" / "advice-cost.json").is_symlink()),
                             ("kept", False))
            self.assertEqual((cost_in(base)["asks"], len(os.listdir(base / "advice"))), (2, 5))

    def test_a_rerun_asks_no_reader_and_its_cost_is_nought(self):
        # The yes is a grant for the Run's first attempt: that attempt asks.
        results, azure_, _ = advised([response(), completion()], first=True)
        self.assertEqual((codes(results), azure_.cost["attempt"], len(azure_.sent)), (BOTH, 1, 2))
        # A later attempt, with the same yes, asks nobody: each Result says it is a re-run's, and the cost is a readable
        # nought of that attempt (the Solution Architect, 2026-11-28).
        rerun = {"astra": ("incomplete", "rerun", 0, 0), "kimi": ("incomplete", "rerun", 0, 0)}
        for said, attempt in (("2", 2), ("100", 100)):
            results, azure_, _ = advised([response(), completion()], env=dict(KEYED, GITHUB_RUN_ATTEMPT=said), first=True,
                                         mid=True)
            self.assertEqual((codes(results), azure_.made, azure_.sent, azure_.seen), (rerun, [], [], []), said)
            nought = {"schema": "advice-cost/1", "run": RUN, "attempt": attempt, "release": "factory/v0.3.1", "asks": 0,
                      "cost_usd": 0}
            self.assertEqual((azure_.before, azure_.cost), (nought, nought), said)
        # So the day's sum does not rise on a re-run past the first attempt's worst case: the re-run's own attempt
        # counts nought, where one that asked again would count its cost beside it.
        worst = config()["advisory_worst_case_usd"]
        record = {"status": "completed", "advisory_attempt": 2, "advisory_asks": azure_.cost["asks"],
                  "advisory_cost_usd": azure_.cost["cost_usd"]}
        self.assertEqual(advisory.counted(record, worst), worst)
        self.assertEqual(advisory.counted(dict(record, advisory_asks=2, advisory_cost_usd=None), worst), 2 * worst)

    def test_an_attempt_that_cannot_be_read_asks_nobody_and_writes_nothing(self):
        # An attempt that cannot be read is never taken for the first: no reader is asked, nothing is written, and the
        # pass counts the Run's worst case (the Factory Builder, 2026-11-28).
        for env in ({"ADVISORY_AZURE_KEY": "k" * 32}, dict(KEYED, GITHUB_RUN_ATTEMPT="0"),
                    dict(KEYED, GITHUB_RUN_ATTEMPT="1 "), dict(KEYED, GITHUB_RUN_ATTEMPT="101")):
            with tempfile.TemporaryDirectory() as where:
                base = pathlib.Path(where)
                folder(base)
                stand_in = Azure([response(), completion()])
                with self.assertRaisesRegex(steps.Stop, "^attempt_unreadable$"):
                    advise.job("task", "advice", env, base=base, transport=stand_in)
                self.assertEqual((os.listdir(base), stand_in.made), (["task"], []), env)

    def test_an_ask_is_counted_as_it_is_sent_and_never_as_configured(self):
        # Kimi's transport is not reached, so nothing is sent to it: the Run said before it began that it was about to
        # ask two readers, and at its end it says the one ask it sent.
        class Once(Azure):
            def __call__(self, host, key, seconds):
                if self.made:
                    raise OSError("no route")
                return super().__call__(host, key, seconds)
        with tempfile.TemporaryDirectory() as where:
            base = pathlib.Path(where)
            folder(base)
            clock = Clock()
            stand_in = Once([response(), completion()], lambda: stand_in.seen.append(cost_in(base)))
            stand_in.seen = []
            advise.job("task", "advice", KEYED, base=base, transport=stand_in, clock=clock, sleep=clock.sleep)
            kimi = json.loads((base / "advice" / "advice.kimi.json").read_text())
            astra = json.loads((base / "advice" / "advice.astra.json").read_text())
            self.assertEqual([seen["asks"] for seen in stand_in.seen], [2])
            self.assertEqual((kimi["reason"], kimi["usage"]["asks"], len(stand_in.sent)), ("transport", 0, 1))
            self.assertEqual(spent(cost_in(base)), (1, astra["usage"]["cost_usd"]))

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
        # With no diff to send, each reader has a Result and none is asked.
        results, azure_, _ = advised([], drop=("diff",))
        self.assertEqual(codes(results), {"astra": ("failed", "transport", 0, 0), "kimi": ("failed", "transport", 0, 0)})
        self.assertEqual(azure_.sent, [])
        # A Result that cannot be written is not claimed, and the reader after it is still asked.
        with tempfile.TemporaryDirectory() as where:
            base = pathlib.Path(where)
            folder(base)
            planted = base / "advice" / "advice.astra.json"       # put there once the step has taken its folder
            stand_in, clock = Azure([response(), completion()], lambda: planted.exists() or planted.write_text("{}")), Clock()
            written = advise.job("task", "advice", KEYED, base=base, transport=stand_in, clock=clock, sleep=clock.sleep)
            self.assertEqual(([lens for lens, _ in written], len(stand_in.sent)), (["kimi"], 2))

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
                    advise.job("task", "advice", FIRST, base=base)
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
