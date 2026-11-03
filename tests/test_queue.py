"""The queue App's act (issue 381, decision 0129): the port held to what the trials recorded, the job's rulings, and its
step through its two credentials."""
from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest
import unittest.mock

from adapters import github, queue as queue_
from harness import queue, queue_step, steps
from tests import support
from tests.test_controller import config, passed, pr, reads, run

ROOT = pathlib.Path(__file__).resolve().parent.parent
ITEM = {"repo": "combsmith/software-factory", "type": "pull_request", "number": 2}
LOGIN = "combsmith-sf-queue[bot]"
HEAD = "a" * 40
NODE = "PR_kwDOVFD6788AAAABLaIeKg"


def recorded(name: str, index: int) -> dict:
    """An answer as a trial recorded it."""
    return copy.deepcopy(json.loads((ROOT / "trials" / name).read_text())["exchanges"][index]["response"])


def pull(head=HEAD, state="open", merged=False, number=2) -> dict:
    """The queue App's read of the pull request, as P-2.queue-app recorded one, at this item's number and head."""
    answer = recorded("P-2.queue-app.json", 8)
    answer["body"].update(number=number, state=state, merged=merged, head=dict(answer["body"]["head"], sha=head))
    return answer


def member(queued: bool) -> dict:
    """Whether pull request 2 is in the merge queue, as P-2.least's read narrowed to `metadata: read` recorded one."""
    answer = recorded("P-2.least.json", 40)
    answer["body"]["data"]["repository"]["pullRequest"]["isInMergeQueue"] = queued
    return answer


def listed_threads() -> dict:
    return recorded("P-5.queue.json", 14)


class Answers:
    """Each request held to the queue App's transport and answered in turn."""

    def __init__(self, *answers):
        self.answers, self.sent = list(answers), []

    def send(self, req):
        self.sent.append(req)
        answer = self.answers.pop(0)
        if answer is None:
            raise github.Unanswered("no answer")
        return answer


def port(*answers):
    asked = Answers(*answers)
    return queue.Port(asked, ITEM, LOGIN), asked


QUEUED = {"id": 349593770, "type": "Bot", "login": LOGIN}


def record(action_reviews=None, threads=None, queued=False, head=HEAD):
    """A pass that decides one queue act on pull request 2, with its workflow named and its account set."""
    cfg = config(workflows=dict(config()["controller"]["workflows"], queue="queue.yml"))
    cfg["controller"]["accounts"] = dict(cfg["controller"]["accounts"], queue=dict(QUEUED))
    out = passed(reads(pulls=[dict(pr(2, reviews=action_reviews or [], threads=threads or [], queue=queued), head=head)],
                       runs=[run(number=2)]), cfg=cfg)
    entry = out["record"]["pull_requests"][0]
    return out["record"], entry["run"], entry["decision"]


class Port(unittest.TestCase):
    def test_the_queue_apps_token_sends_its_three_acts_and_reads_and_nothing_else(self):
        owner, name = ITEM["repo"].split("/")
        empty = {"status": 200, "headers": {}, "body": {}}
        # Before its own read of the pull request and of its threads, it writes nothing, not even to its own node.
        unread = queue_.Queuing(Answers(), ITEM)
        for req in (github.request("POST", "/graphql", body={"query": queue_.ENQUEUE, "variables": {"id": NODE, "h": HEAD}}),
                    github.request("POST", "/graphql", body={"query": queue_.DEQUEUE, "variables": {"id": NODE}}),
                    github.request("POST", "/graphql", body={"query": queue_.RESOLVE, "variables": {"id": "PRRT_kwDOVFD6786xYpyG"}})):
            with self.assertRaises(github.Unanswered, msg=req):
                unread.send(req)
        allowed = queue_.Queuing(Answers(pull(), empty, empty, listed_threads(), member(False), empty), ITEM)
        allowed.send(github.request("GET", "/repos/combsmith/software-factory/pulls/2"))
        allowed.send(github.request("POST", "/graphql", body={"query": queue_.ENQUEUE, "variables": {"id": NODE, "h": HEAD}}))
        allowed.send(github.request("POST", "/graphql", body={"query": queue_.DEQUEUE, "variables": {"id": NODE}}))
        allowed.send(github.request("POST", "/graphql", body={"query": queue_.THREADS,
                                                             "variables": {"owner": owner, "name": name, "pr": 2}}))
        allowed.send(github.request("POST", "/graphql", body={"query": queue_.MEMBERSHIP,
                                                             "variables": {"owner": owner, "name": name, "pr": 2}}))
        allowed.send(github.request("POST", "/graphql", body={"query": queue_.RESOLVE, "variables": {"id": "PRRT_kwDOVFD6786xYpyG"}}))
        other = "PR_kwDOVFD6788AAAABLg1GyQ"
        for req in (github.request("POST", "/graphql", body={"query": queue_.ENQUEUE, "variables": {"id": other, "h": HEAD}}),
                    github.request("POST", "/graphql", body={"query": queue_.DEQUEUE, "variables": {"id": other}}),
                    github.request("POST", "/graphql", body={"query": queue_.RESOLVE, "variables": {"id": "PRRT_kwDOVFD6786xOTHER"}}),
                    github.request("POST", "/graphql", body={"query": queue_.MEMBERSHIP,
                                                             "variables": {"owner": owner, "name": name, "pr": 3}}),
github.request("GET", "/repos/combsmith/software-factory/pulls/3"),
                    github.request("GET", "/repos/combsmith/other/pulls/2"),
                    github.request("POST", "/repos/combsmith/software-factory/pulls/2/reviews", body={}),
                    github.request("POST", "/graphql", body={"query": queue_.ENQUEUE, "variables": {"id": NODE, "h": "main"}}),
                    github.request("POST", "/graphql", body={"query": queue_.ENQUEUE, "variables": {"id": NODE}}),
                    github.request("POST", "/graphql", body={"query": queue_.DEQUEUE, "variables": {"id": "MDQ6VXNlcjE="}}),
                    github.request("POST", "/graphql", body={"query": queue_.RESOLVE, "variables": {"id": NODE}}),
                    github.request("POST", "/graphql", body={"query": queue_.THREADS,
                                                             "variables": {"owner": owner, "name": name, "pr": 3}}),
                    github.request("POST", "/graphql", body={"query": "mutation { mergePullRequest }", "variables": {}})):
            with self.assertRaises(github.Unanswered, msg=req):
                allowed.send(req)

    def test_each_document_is_the_one_a_trial_sent(self):
        # L-51: the enqueue as P-57 sent it, the dequeue as P-2.queue-app did, the resolution as P-5.queue did; the
        # threads' read as P-5.queue's, less the comments, which nothing here reads.
        sent = lambda name, i: json.loads((ROOT / "trials" / name).read_text())["exchanges"][i]["request"]["body"]["query"]
        self.assertEqual(sent("P-57.json", 9), queue_.ENQUEUE)
        self.assertEqual(sent("P-2.queue-app.json", 51), queue_.DEQUEUE)
        self.assertEqual(sent("P-5.queue.json", 15), queue_.RESOLVE)
        self.assertEqual(sent("P-2.least.json", 40), queue_.MEMBERSHIP)
        self.assertEqual(sent("P-5.queue.json", 14).replace(" comments(first: 1) { nodes { databaseId author { login __typename } body } }", ""),
                         queue_.THREADS)


class Job(unittest.TestCase):
    def test_an_enqueue_is_made_at_the_head_decided_on_and_read_back(self):
        rec, rid, decided = record(action_reviews=[support.review()])
        self.assertEqual(decided["action"], "enqueue")
        p, asked = port(pull(), member(False), recorded("P-57.json", 9))
        done, ended = queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})
        self.assertEqual([(e["type"], e["state"], e["key"]) for e in done["effects"]], [("enqueue", "applied", NODE)])
        self.assertIsNone(ended["outcome"])
        self.assertEqual(asked.sent[2]["body"]["variables"], {"id": NODE, "h": HEAD})
        # Already in the merge queue, as a second Run sent beside the first finds it: recovered, nothing sent.
        p, asked = port(pull(), member(True))
        done, ended = queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})
        self.assertEqual((done["effects"][0]["state"], done["effects"][0]["key"], ended["outcome"], len(asked.sent)),
                         ("already_applied", NODE, None, 2))
        # A queue that cannot be read is the environment's, and nothing is sent.
        for unread in ({"status": 200, "headers": {}, "body": {"data": None, "errors": [{"type": "FORBIDDEN"}]}}, None):
            p, asked = port(pull(), unread)
            ended = queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})[1]
            self.assertEqual((ended["outcome"], len(asked.sent)), ("environment", 2))
        # A refusal at the head decided on, open: the item's, which its attempts bound. One with the head moved, or
        # closed, since: a change under the act. GitHub's words are never read.
        for again, why in ((pull(), ("item", "enqueue_refused")), (pull(head="b" * 40), ("superseded", "head_moved")),
                           (pull(state="closed"), ("superseded", "closed_under_act"))):
            p, _ = port(pull(), member(False), recorded("P-57.json", 4), again)
            done, ended = queue.job(rec, rid, p, {"release": rec["release"], "paused": "false"})
            self.assertEqual((ended["outcome"], ended["reason"]), why)
            self.assertEqual(done["effects"][0]["state"], "failed")
        # Read again, closed or at another head before anything is sent: nothing is sent.
        for read, why in ((pull(head="b" * 40), "head_moved"), (pull(state="closed"), "closed_under_act"),
                          (pull(merged=True), "closed_under_act")):
            p, asked = port(read)
            done, ended = queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})
            self.assertEqual((ended["outcome"], ended["reason"], len(asked.sent)), ("superseded", why, 1))
        # A refusal whose re-read GitHub did not answer is the environment's, never the item's.
        p, _ = port(pull(), member(False), recorded("P-57.json", 4), None)
        ended = queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})[1]
        self.assertEqual((ended["outcome"], ended["reason"]), ("environment", "github_unavailable"))
        # An answer that names no entry, or an entry in no state the queue has, claims nothing; no answer, a refused
        # token or a pull request unreadable is the environment's.
        bogus = recorded("P-57.json", 9)
        bogus["body"]["data"]["enqueuePullRequest"]["mergeQueueEntry"]["state"] = "BOGUS"
        for answer, why in (({"status": 200, "headers": {}, "body": {"data": {"enqueuePullRequest": None}}}, "not_read_back"),
                            (bogus, "not_read_back"),
                            ({"status": 502, "headers": {}, "body": None}, "github_unavailable"),
                            (None, "github_unavailable"), ({"status": 401, "headers": {}, "body": {}}, "token_refused")):
            p, _ = port(pull(), member(False), answer)
            self.assertEqual(queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})[1]["reason"], why)
        for read in ({"status": 200, "headers": {}, "body": {"number": 2}}, pull(number=3)):
            p, _ = port(read)
            self.assertEqual(queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})[1]["reason"], "pull_unreadable")

    def test_a_dequeue_is_made_at_the_head_decided_on_and_claims_nothing_it_did_not_see_taken(self):
        person = support.thread(kind="human", name="don-petry", severity=None)
        rec, rid, decided = record(action_reviews=[support.review()], threads=[person], queued=True)
        self.assertEqual(decided["action"], "dequeue")
        p, asked = port(pull(), member(True), recorded("P-2.queue-app.json", 51))
        done, ended = queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})
        self.assertEqual([(e["type"], e["state"], e["key"]) for e in done["effects"]], [("dequeue", "applied", NODE)])
        self.assertEqual(asked.sent[2]["body"], {"query": queue_.DEQUEUE, "variables": {"id": NODE}})
        # Out of the queue already: recovered, nothing sent.
        p, asked = port(pull(), member(False))
        done, ended = queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})
        self.assertEqual((done["effects"][0]["state"], ended["outcome"], len(asked.sent)), ("already_applied", None, 2))
        # GitHub's refusal, as P-2.queue-app recorded it for a pull request not in the queue: the item may have left
        # already, which the next pass reads, so nothing is claimed.
        p, _ = port(pull(), member(True), recorded("P-2.queue-app.json", 41))
        done, ended = queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})
        self.assertEqual((done["effects"][0]["state"], ended["outcome"], ended["reason"]), ("failed", "environment", "dequeue_refused"))
        p, asked = port(pull(head="b" * 40))
        self.assertEqual(queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})[1]["reason"], "head_moved")

    def test_a_thread_is_resolved_unless_it_is_already_and_read_back_as_the_queue_apps(self):
        rec, rid, decided = record(threads=[support.thread(tid="PRRT_kwDOVFD6786xYpyG", ruling="accepted")])
        self.assertEqual(decided["action"], "resolve_thread")
        listed = recorded("P-5.queue.json", 14)
        p, asked = port(listed, recorded("P-5.queue.json", 15))
        done, ended = queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})
        self.assertEqual([(e["type"], e["state"], e["key"]) for e in done["effects"]],
                         [("resolve_thread", "applied", "PRRT_kwDOVFD6786xYpyG")])
        self.assertIsNone(ended["outcome"])
        # One GitHub shows resolved already is recovered, and nothing is written.
        shown = copy.deepcopy(listed)
        shown["body"]["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"][0]["isResolved"] = True
        p, asked = port(shown)
        done, ended = queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})
        self.assertEqual((done["effects"][0]["state"], len(asked.sent)), ("already_applied", 1))
        # Read back by another account, or not resolved: nothing claimed. A thread gone: a change under the act.
        for change in ({"login": "someone-else"}, None):
            back = recorded("P-5.queue.json", 15)
            node = back["body"]["data"]["resolveReviewThread"]["thread"]
            if change is None:
                node["isResolved"] = False
            else:
                node["resolvedBy"].update(change)
            p, _ = port(listed, back)
            self.assertEqual(queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})[1]["reason"], "not_read_back")
        # An answer about another thread claims nothing.
        back = recorded("P-5.queue.json", 15)
        back["body"]["data"]["resolveReviewThread"]["thread"]["id"] = "PRRT_kwDOVFD6786xYylP"
        p, _ = port(listed, back)
        self.assertEqual(queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})[1]["reason"], "not_read_back")
        gone = copy.deepcopy(listed)
        nodes = gone["body"]["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
        gone["body"]["data"]["repository"]["pullRequest"]["reviewThreads"].update(nodes=nodes[1:], totalCount=len(nodes) - 1)
        p, _ = port(gone)
        self.assertEqual(queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})[1]["reason"], "thread_gone")
        # A list not read whole, or shorter than its count, is the environment's.
        cut = copy.deepcopy(listed)
        cut["body"]["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"]["hasNextPage"] = True
        short = copy.deepcopy(listed)
        short["body"]["data"]["repository"]["pullRequest"]["reviewThreads"]["totalCount"] += 1
        malformed = [{"status": 200, "headers": {}, "body": body} for body in (
            {"data": "x"}, {"data": {"repository": "x"}}, {"data": {"repository": {"pullRequest": "x"}}})]
        paged = copy.deepcopy(listed)
        paged["body"]["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"] = "x"
        for unread in [cut, short, paged] + malformed:
            p, _ = port(unread)
            self.assertEqual(queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})[1]["reason"], "threads_unreadable")

    def test_a_resolution_writes_nothing_unless_every_thread_is_there_and_stops_at_its_first_failure(self):
        ids = ("PRRT_kwDOVFD6786xYpyG", "PRRT_kwDOVFD6786xYylP")
        rec, rid, decided = record(threads=[support.thread(tid=i, ruling="accepted") for i in ids])
        self.assertEqual(sorted(decided["evidence"]), sorted(ids))
        listed = listed_threads()
        # One of the two gone: nothing is written, not even the one still there.
        gone = copy.deepcopy(listed)
        held = gone["body"]["data"]["repository"]["pullRequest"]["reviewThreads"]
        held.update(nodes=[n for n in held["nodes"] if n["id"] != decided["evidence"][1]], totalCount=len(held["nodes"]) - 1)
        p, asked = port(gone)
        ended = queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})[1]
        self.assertEqual((ended["reason"], len(asked.sent)), ("thread_gone", 1))
        # The first write refused: the second is never sent.
        p, asked = port(listed, {"status": 200, "headers": {}, "body": {"errors": [{"type": "FORBIDDEN"}]}})
        done, ended = queue.job(rec, rid, p, {"release": rec["release"], "paused": ""})
        self.assertEqual((ended["reason"], len(asked.sent), len(done["effects"])), ("resolve_refused", 2, 1))

    def test_no_decision_a_pause_or_no_head_sends_nothing(self):
        rec, rid, decided = record(action_reviews=[support.review()])
        for paused in ("true", "1", None, "TRUE "):
            p, asked = port()
            done, ended = queue.job(rec, rid, p, {"release": rec["release"], "paused": paused})
            self.assertEqual((ended["outcome"], ended["reason"], asked.sent), ("superseded", "paused", []), paused)
        p, asked = port()
        done, ended = queue.job(rec, "r_0OTHER1", p, {"release": rec["release"], "kind": "dequeue", "paused": ""})
        self.assertEqual((ended["reason"], done["effects"][0]["type"]), ("no_decision", "dequeue"))
        headless = copy.deepcopy(rec)
        del headless["pull_requests"][0]["head"]
        self.assertEqual(queue.job(headless, rid, p, {"release": rec["release"], "paused": ""})[1]["reason"], "head_unknown")
        self.assertEqual(asked.sent, [])
        # An approval's or an admission's Run is no queue act.
        approving = passed(reads(runs=[run()]))["record"]
        entry = approving["pull_requests"][0]
        self.assertIsNone(queue.decision_of(approving, entry["run"]))


class Step(unittest.TestCase):
    def setUp(self):
        self.rec, self.rid, self.decided = record(action_reviews=[support.review()])
        entry = self.rec["pull_requests"][0]
        self.name = "sf %s#2 enqueue-merge pr-review %s %s" % (ITEM["repo"], self.decided["content_id"], self.rid)
        self.argv = [self.name, "%s#2" % ITEM["repo"], self.rec["pass"], "out"]
        loaded = queue_step.configuration.load

        def load(*a, **k):
            got = loaded(*a, **k)
            got["controller"]["accounts"] = dict(got["controller"]["accounts"], queue=dict(QUEUED))
            return got
        self.patches = [unittest.mock.patch.object(queue_step.configuration, "load", load),
                        unittest.mock.patch.object(queue_step.steps, "release", lambda: self.rec["release"])]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def written(self, environ, found=None, minted=None, answers=(), revoked=True):
        reads_through, wanted = [], []
        asked = Answers(*answers)
        self.revokes = []

        def find(transport, *a):
            reads_through.append(transport)
            if isinstance(found, Exception):
                raise found
            return self.rec if found is None else found

        def from_key(app, repo, want, key, now, connect):
            wanted.append((app["name"], repo, want, key))
            if minted is not None:
                raise minted
            return asked, lambda: self.revokes.append(revoked) or revoked
        with unittest.mock.patch.object(queue_step.passes, "find", find), \
                unittest.mock.patch.object(queue_step.identity, "from_key", from_key):
            got = queue_step.written(self.argv, environ, lambda: 0, lambda token: ("live", token))
        return got, reads_through, wanted, asked

    def test_the_step_reads_with_the_jobs_token_and_writes_with_the_queue_apps(self):
        environ = {"GITHUB_TOKEN": "g", "QUEUE_APP_KEY": "k", "FACTORY_PAUSED": ""}
        (done, ended), reads_through, wanted, asked = self.written(environ, answers=(pull(), member(False), recorded("P-57.json", 9)))
        self.assertIsNone(ended["outcome"], ended)
        self.assertEqual(done["effects"][0]["state"], "applied")
        # The token is revoked when the act ends; a revoke that fails is a fault, though the write landed.
        self.assertEqual(self.revokes, [True])
        (done, ended), _, _, _ = self.written(environ, answers=(pull(), member(False), recorded("P-57.json", 9)), revoked=False)
        self.assertEqual((done["effects"][0]["state"], ended["outcome"], ended["reason"]),
                         ("applied", "environment", "token_not_revoked"))
        # The record is found through the job's own token, held to the item's repo and reads.
        self.assertEqual([type(t).__name__ for t in reads_through], ["Approving"])
        # The queue App's token is minted with the grants its three acts take, and nothing more.
        self.assertEqual(wanted, [("combsmith-sf-queue", ITEM["repo"], {"contents": "write"}, "k")])
        self.assertEqual(len(asked.sent), 3)
        # Paused as the job's vars give it, or with no Pause given at all: nothing is written.
        for paused in ({"FACTORY_PAUSED": "true"}, {}):
            env = dict(environ, **paused)
            if not paused:
                del env["FACTORY_PAUSED"]
            (done, ended), _, wanted, asked = self.written(env, answers=())
            self.assertEqual((ended["reason"], asked.sent, wanted), ("paused", [], []), paused)

    def test_a_record_a_decision_or_a_key_that_cannot_serve_writes_nothing(self):
        environ = {"GITHUB_TOKEN": "g", "QUEUE_APP_KEY": "k", "FACTORY_PAUSED": ""}
        elsewhere = copy.deepcopy(self.rec)
        elsewhere["pull_requests"][0]["decision"]["item"]["number"] = 3
        for found, minted, why in ((github.Unanswered("no"), None, "record_unreadable"),
                                   (dict(self.rec, release="factory/v9.9.9"), None, "release_differs"),
                                   (elsewhere, None, "not_the_decision"),
                                   (None, queue_step.identity.Refused("key_unreadable"), "key_unreadable")):
            (done, ended), _, _, asked = self.written(environ, found=found, minted=minted)
            self.assertEqual((ended["reason"], asked.sent), (why, []), why)
        # A run-name that names another content id, Role or act than its Decision's: nothing is minted.
        name = self.name
        for other in (name.replace(self.decided["content_id"], "sha256:bbbb"), name.replace(" pr-review ", " lens-security "),
                      name.replace("enqueue-merge", "dequeue-merge")):
            self.argv[0] = other
            (done, ended), _, wanted, _ = self.written(environ)
            self.assertEqual((ended["reason"], wanted), ("not_the_decision", []), other)
        self.argv[0] = name
        # No Decision for the Run in the record, or no record at all, paused or not: nothing is minted, and the Effect
        # is of the act the run-name names.
        absent = dict(self.rec, pull_requests=[])
        for paused in ("", "true"):
            (done, ended), _, wanted, _ = self.written(dict(environ, FACTORY_PAUSED=paused), found=absent)
            self.assertEqual((ended["reason"], wanted), ("no_decision", []), paused)
        self.argv[0] = name.replace("enqueue-merge", "dequeue-merge")
        with unittest.mock.patch.object(queue_step.passes, "find", lambda *a: None):
            done, ended = queue_step.written(self.argv, environ, lambda: 0, lambda token: "live")
        self.assertEqual((ended["reason"], done["effects"][0]["type"]), ("no_decision", "dequeue"))
        self.argv[0] = name
        # With no queue App's account, a resolution could not be read back as the App's: nothing is minted.
        base = self.loaded()
        base["controller"]["accounts"] = dict(base["controller"]["accounts"], queue=None)
        with unittest.mock.patch.object(queue_step.configuration, "load", lambda *a, **k: copy.deepcopy(base)):
            (done, ended), _, wanted, _ = self.written(environ)
        self.assertEqual((ended["reason"], wanted), ("queue_account_unknown", []))
        # A run-name of another Intent is no queue act.
        self.argv[0] = self.name.replace("enqueue-merge", "issue-approval")
        with self.assertRaises(steps.Stop):
            self.written(environ)

    def loaded(self):
        return queue_step.configuration.load(steps.ROOT, self.rec["release"], "controller")

    def test_the_step_writes_its_records_and_fails_by_its_code(self):
        environ = {"GITHUB_TOKEN": "g", "QUEUE_APP_KEY": "k", "FACTORY_PAUSED": "true"}
        with tempfile.TemporaryDirectory() as d, \
                unittest.mock.patch.object(queue_step.passes, "find", lambda *a: self.rec):
            with self.assertRaises(steps.Stop) as stopped:
                queue_step.step(self.argv, environ, d, lambda: 0, lambda token: "live")
            self.assertEqual(str(stopped.exception), "paused")
            said = json.loads(pathlib.Path(d, "out", "outcome.json").read_text())
            self.assertEqual((said["outcome"], said["reason"]), ("superseded", "paused"))
            self.assertTrue(pathlib.Path(d, "out", "applied.json").exists())


if __name__ == "__main__":
    unittest.main()
