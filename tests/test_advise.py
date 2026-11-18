"""The advise step, `harness/advise.py`: each advisory Lens's reader is asked, and its Result written (decision 0224).

Nothing here reaches the network: the transport is a stand-in that keeps what it was sent and answers from a list."""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest

from adapters import azure
from harness import advise, shared
from tools import jsonschema_lite

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN = "r_01JA7Q"
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


LIMITED = {"status": 429, "headers": {"retry-after": "20"}, "body": {"error": {"code": "rate_limit_exceeded"}}}


class Azure:
    """A stand-in for `azure.Live`: it keeps how it was made and what it was sent, and answers in turn."""

    def __init__(self, answers: list):
        self.answers, self.made, self.sent = list(answers), [], []

    def __call__(self, host, key, seconds):
        self.made.append((host, key, seconds))
        return self

    def send(self, request: dict) -> dict:
        self.sent.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
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
           rules=None) -> None:
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
    (task / "run").write_text(RUN + "\n")
    (task / "diff").write_bytes(diff)
    if rules is not None:
        (task / "rules.json").write_text(json.dumps(rules))


def advised(answers: list, env=None, **made) -> tuple:
    """`({lens: Result}, the stand-in, the clock)` of one run of the step, each Result held to advice/1 and its digest."""
    with tempfile.TemporaryDirectory() as where:
        base = pathlib.Path(where)
        folder(base, **made)
        stand_in, clock = Azure(answers), Clock()
        written = advise.job("task", "advice", {"ADVISORY_AZURE_KEY": "k" * 32} if env is None else env, base=base,
                             transport=stand_in, clock=clock, sleep=clock.sleep)
        results = {}
        for lens, digest in written:
            data = (base / "advice" / ("advice.%s.json" % lens)).read_bytes()
            assert digest == "sha256:" + advise.hashlib.sha256(data).hexdigest()
            assert (base / "advice" / ("advice.%s.sha256" % lens)).read_text() == digest + "\n"
            results[lens] = json.loads(data)
            assert jsonschema_lite.validate(results[lens], shared.SCHEMAS["advice"], schemas=shared.SCHEMAS) == []
        assert sorted(p.name for p in (base / "advice").iterdir()) == sorted(
            "advice.%s.%s" % (lens, kind) for lens in results for kind in ("json", "sha256"))
        return results, stand_in, clock


def codes(results: dict) -> dict:
    return {lens: (r["status"], r["reason"], len(r["findings"]), r["usage"]["asks"]) for lens, r in results.items()}


class Advise(unittest.TestCase):
    def test_each_reader_configured_is_asked_once_with_no_tool_and_its_result_written(self):
        results, azure_, _ = advised([response("queued", ""), response("in_progress", ""), response(), completion()],
                                     rules={"AGENTS.md": "The rules.", "x": 7})
        self.assertEqual(codes(results), {"astra": ("completed", None, 1, 1), "kimi": ("completed", None, 0, 1)})
        readers = config()["readers"]
        # Each is reached at its own host with the step's one key, and a wait no longer than its own seconds.
        self.assertEqual(azure_.made, [(readers["astra"]["host"], "k" * 32, readers["astra"]["seconds"]),
                                       (readers["kimi"]["host"], "k" * 32, readers["kimi"]["seconds"])])
        create, first, second, chat = azure_.sent
        self.assertEqual((create["act"], first, second, chat["act"]),
                         ("create", azure.read("resp_1"), azure.read("resp_1"), "chat"))
        # One prompt, the cap, the effort, in the background; no tool, no file, nothing else.
        self.assertEqual(sorted(create["body"]), ["background", "input", "max_output_tokens", "model", "reasoning", "store"])
        self.assertEqual((create["body"]["model"], create["body"]["max_output_tokens"], create["body"]["reasoning"]),
                         (readers["astra"]["deployment"], readers["astra"]["output_tokens"], {"effort": "max"}))
        self.assertEqual(sorted(chat["body"]), ["max_completion_tokens", "messages", "model", "reasoning_effort"])
        self.assertEqual(chat["body"]["messages"][0]["content"], create["body"]["input"])
        # The prompt: the fixed instruction, then the rules the folder held, then the whole diff, as data.
        prompt = create["body"]["input"]
        instruction = (ROOT / "roles" / "pr-review" / "advisory-reader.md").read_text()
        self.assertTrue(prompt.startswith(instruction))
        self.assertLess(prompt.index("--- AGENTS.md ---\nThe rules."), prompt.index("diff --git a/x b/x"))
        self.assertNotIn("--- x ---", prompt)
        self.assertEqual(results["astra"]["findings"][0]["location"], {"path": "kernel/derive.py", "start_line": 88})
        self.assertEqual(results["astra"]["usage"]["effort"], "max")       # the example's change touches the Kernel
        elsewhere, _, _ = advised([response(), completion()],
                                  change={"changed_paths": [{"path": "docs/glossary.md", "previous": None}]})
        self.assertEqual(elsewhere["astra"]["usage"]["effort"], "xhigh")
        moved, _, _ = advised([response(), completion()],
                              change={"changed_paths": [{"path": "docs/derive.md", "previous": "kernel/derive.py"}]})
        self.assertEqual(moved["astra"]["usage"]["effort"], "max")

    def test_a_reader_is_not_asked_without_the_days_yes_a_key_or_a_prompt_that_fits(self):
        for ask in (False, None, "yes", 1):
            results, azure_, _ = advised([], ask=ask)
            self.assertEqual(codes(results), {"astra": ("incomplete", "budget", 0, 0), "kimi": ("incomplete", "budget", 0, 0)}, ask)
            self.assertEqual((azure_.made, azure_.sent), ([], []))
        for env in ({}, {"ADVISORY_AZURE_KEY": ""}, {"AZURE_OPENAI_API_KEY": "k" * 32}):
            results, azure_, _ = advised([], env=env)
            self.assertEqual(codes(results), {"astra": ("failed", "no_key", 0, 0), "kimi": ("failed", "no_key", 0, 0)}, env)
            self.assertEqual(azure_.made, [])
        large = b"+" * config()["readers"]["astra"]["prompt_characters"]
        results, azure_, _ = advised([], diff=large)
        self.assertEqual(codes(results), {"astra": ("incomplete", "too_large", 0, 0), "kimi": ("incomplete", "too_large", 0, 0)})
        self.assertEqual(azure_.sent, [])
        # No reader reads a dependency's change, and none reads for another Intent: nothing is written or asked.
        for made in ({"change": {"class": "dependency"}}, {"intent": "fix-findings"}):
            results, azure_, _ = advised([], **made)
            self.assertEqual((results, azure_.made), ({}, []), made)

    def test_a_rate_limit_is_waited_for_once_and_a_response_still_running_is_cancelled(self):
        # The wait a rate limit names, once; a second rate limit is the Result, and nothing is asked in a loop.
        results, azure_, clock = advised([LIMITED, response(), LIMITED, LIMITED])
        self.assertEqual(codes(results), {"astra": ("completed", None, 1, 2), "kimi": ("incomplete", "rate_limited", 0, 2)})
        self.assertEqual((clock.slept, len(azure_.sent)), ([20, 20], 4))
        # A wait it does not name as a short whole number, or that does not fit, is not waited for.
        for header in ("91", "soon", "-1", "1.5", "0020", ""):
            results, azure_, clock = advised([dict(LIMITED, headers={"retry-after": header})] * 2)
            self.assertEqual(codes(results)["astra"], ("incomplete", "rate_limited", 0, 1), header)
            self.assertEqual(clock.slept, [])
        # A response not ended when the reader's share of the step is spent is cancelled, and is `timed_out`.
        polls = advise.WHOLE // 2 // advise.POLL - 1      # the first of two readers has half the step
        results, azure_, clock = advised([response("queued", "")] + [response("in_progress", "")] * polls
                                         + [response("cancelled", ""), completion()])
        self.assertEqual(codes(results), {"astra": ("incomplete", "timed_out", 0, 1), "kimi": ("completed", None, 0, 1)})
        self.assertEqual(azure_.sent[-2], azure.cancel("resp_1"))
        self.assertLessEqual(clock.now, advise.WHOLE)
        self.assertEqual(azure_.made[1][2], min(config()["readers"]["kimi"]["seconds"], int(advise.WHOLE - sum(clock.slept))))
        # What Azure does not answer, or this step did not foresee of it, is a code, and the next reader is still asked.
        results, azure_, _ = advised([azure.Unanswered("down"), completion()])
        self.assertEqual(codes(results), {"astra": ("failed", "transport", 0, 1), "kimi": ("completed", None, 0, 1)})
        results, _, _ = advised([response(), azure.Unanswered("down")])
        self.assertEqual(codes(results), {"astra": ("completed", None, 1, 1), "kimi": ("failed", "transport", 0, 1)})
        results, _, _ = advised([response(model="another-model"), completion("not json")])
        self.assertEqual(codes(results), {"astra": ("failed", "not_the_model", 0, 1), "kimi": ("failed", "unparsed", 0, 1)})

    def test_the_step_never_fails_its_job(self):
        with tempfile.TemporaryDirectory() as where:
            self.assertEqual(advise.main([where + "/no-task", where + "/out"], {}), 0)
        self.assertEqual(advise.main(["../outside", "advice"], {}), 0)
        # Nor on a fault that is no refusal of a step's: a folder with no Run in it, read where the step runs.
        with tempfile.TemporaryDirectory() as where:
            folder(pathlib.Path(where))
            (pathlib.Path(where) / "task" / "run").unlink()
            here = os.getcwd()
            self.addCleanup(os.chdir, here)
            os.chdir(where)
            self.assertEqual(advise.main(["task", "advice"], {}), 0)
            os.chdir(here)


if __name__ == "__main__":
    unittest.main()
