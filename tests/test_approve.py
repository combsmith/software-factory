"""The approving act (`harness/approve.py`) and its one write (`approve` in `adapters/effects.py`), against a stand-in
GitHub: the act approves only the commit it read, only what the Kernel asked again still wants, through the approver's
own token, with one write, and says whose fault each failure was (issue 195, rulings 4 to 7)."""
from __future__ import annotations

import copy
import json
import unittest

from adapters import acceptance, checks, effects, threads
from adapters.facts import Moved
from adapters.github import Unanswered
from harness import approve
from kernel.decide import decide
from tests.support import CONFIG, NOW, ROOT, context, facts, labelled, review, run
from tools.jsonschema_lite import validate

SCHEMAS = effects.SCHEMAS
RUN = "r_01JA7Q"
GITHUB_RUN = "39100000001"
HEAD = "c0ffee" + "0" * 34
APPROVER = CONFIG["approver"]
ITEM = facts()["item"]
PULL = "/repos/%s/pulls/%d" % (ITEM["repo"], ITEM["number"])
REVIEWED = [run()]
NODE = "PRR_kwDOapproval"
LANDED = {"id": 7, "node_id": NODE, "state": "APPROVED", "commit_id": HEAD, "user": {"login": APPROVER}}


def record(f=None, runs=REVIEWED, ctx=None, entry_run=RUN) -> dict:
    """A pass record whose one pull request's Decision was made on `f`, as the pass makes it, under Run id `entry_run`."""
    out = json.loads((ROOT / "examples" / "pass.json").read_text())
    f = facts() if f is None else f
    out["pull_requests"] = [{"facts": f, "decision": decide(f, list(runs), ctx or context(), CONFIG, NOW),
                             "run": entry_run}]
    return out


class GitHub:
    """A stand-in GitHub: each request is logged and answered from `answers` by method and path, else a 404. An answer
    of None is no answer at all; a list is answered in turn, its last kept for every request after."""

    def __init__(self, over=None):
        self.log = []
        self.answers = {
            ("GET", "/user"): {"status": 200, "body": {"login": APPROVER, "type": "User", "id": 281750570}},
            ("GET", PULL + "/reviews?per_page=100"): {"status": 200, "body": []},
            ("POST", PULL + "/reviews"): {"status": 200, "body": dict(LANDED)},
            ("GET", PULL + "/reviews/7"): {"status": 200, "body": dict(LANDED)},
            ("GET", PULL): {"status": 200, "body": {"state": "open", "head": {"sha": HEAD}}},
        }
        self.answers.update(over or {})

    def send(self, req):
        self.log.append(req)
        answer = self.answers.get((req["method"], req["path"]), {"status": 404, "body": {"message": "Not Found"}})
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        if answer is None:
            raise Unanswered("no answer")
        return dict(answer, headers={})

    def writes(self) -> list:
        return [(r["method"], r["path"], r["body"]) for r in self.log if r["method"] != "GET"]


def at(path: str, answer) -> GitHub:
    return GitHub({("POST" if path == PULL + "/reviews" else "GET", path): answer})


def reads(f=None, runs=REVIEWED, ctx=None, head=HEAD):
    """`read()` as the job is handed it: the item read again, its head, the run records and the context."""
    def read():
        return (copy.deepcopy(facts() if f is None else f), head, copy.deepcopy(list(runs)),
                copy.deepcopy(context() if ctx is None else ctx))
    return read


def failing(err):
    def read():
        raise err
    return read


DEFAULT = object()


def act(github=None, rec=DEFAULT, read=None, run_id=RUN):
    github = GitHub() if github is None else github
    port = approve.Port(github, APPROVER)
    config = {"approver": APPROVER, "kernel": CONFIG, "github_run": GITHUB_RUN, "release": "factory/v0.3.1"}
    done, ended = approve.job(record() if rec is DEFAULT else rec, run_id, reads() if read is None else read, port,
                              config, NOW)
    assert not validate(done, SCHEMAS["applied"], schemas=SCHEMAS), validate(done, SCHEMAS["applied"], schemas=SCHEMAS)
    assert not validate(ended, SCHEMAS["outcome"], schemas=SCHEMAS), validate(ended, SCHEMAS["outcome"], schemas=SCHEMAS)
    return done, ended, github


def effect(done) -> tuple:
    (one,) = done["effects"]
    return one["type"], one["state"], one["key"], one["reason"]


def fault(ended) -> tuple:
    return ended["outcome"], ended["reason"]


class TheAct(unittest.TestCase):
    def test_the_act_approves_the_commit_it_read_and_claims_only_what_it_reads_back(self):  # decision 0007, L-41
        done, ended, github = act()
        self.assertEqual(effect(done), ("approve", "applied", NODE, None))
        self.assertEqual(fault(ended), (None, None))
        self.assertEqual((done["run"], ended["run"], done["findings"]), (RUN, RUN, []))
        self.assertEqual([(r["method"], r["path"]) for r in github.log],
                         [("GET", "/user"), ("GET", PULL + "/reviews?per_page=100"), ("GET", PULL),
                          ("POST", PULL + "/reviews"), ("GET", PULL + "/reviews/7"), ("GET", PULL)])
        # The commit approved is the one just read, never the pull request by number alone; nothing else is in it.
        self.assertEqual(github.writes(), [("POST", PULL + "/reviews", {"commit_id": HEAD, "event": "APPROVE"})])

    def test_the_act_sends_one_write_and_it_is_the_approval(self):  # decision 0005, issue 195 ruling 4.6
        # The approver's transport sends the item's reads and one write, the approval of the commit read, and nothing
        # else: no comment, push, merge, dismissal, resolution or mutation leaves the job.
        github = GitHub()
        token = effects.Approving(github, ITEM, HEAD)
        repo = ITEM["repo"]
        refused = [("POST", PULL + "/reviews", {"commit_id": HEAD, "event": "COMMENT"}),
                   ("POST", PULL + "/reviews", {"commit_id": HEAD, "event": "REQUEST_CHANGES"}),
                   ("POST", PULL + "/reviews", {"commit_id": "f" * 40, "event": "APPROVE"}),
                   ("POST", PULL + "/reviews", {"commit_id": HEAD, "event": "APPROVE", "body": "LGTM"}),
                   ("POST", PULL + "/reviews", {"event": "APPROVE"}),
                   ("POST", "/repos/combsmith/other/pulls/42/reviews", {"commit_id": HEAD, "event": "APPROVE"}),
                   ("POST", "/repos/%s/pulls/43/reviews" % repo, {"commit_id": HEAD, "event": "APPROVE"}),
                   ("POST", "/repos/%s/issues/42/comments" % repo, {"body": "x"}),
                   ("PUT", PULL + "/merge", {}), ("PUT", PULL + "/reviews/7/dismissals", {"message": "x"}),
                   ("DELETE", "/repos/%s/git/refs/heads/main" % repo, None), ("PATCH", PULL, {"state": "closed"}),
                   ("POST", "/repos/%s/git/refs" % repo, {"ref": "refs/heads/x", "sha": HEAD}),
                   ("POST", "/graphql", {"query": "mutation { resolveReviewThread(input: {threadId: \"T\"}) { thread "
                                                  "{ id } } }", "variables": {}}),
                   ("GET", "/repos/combsmith/other/pulls/42", None),
                   ("GET", "/repos/%s/../other/pulls/1" % repo, None), ("GET", "/repos/%s/%%2e%%2e/x" % repo, None),
                   ("GET", "/repos/%s//pulls/42" % repo, None), ("GET", "/repos/%s/%%2E%%2E/x" % repo, None),
                   ("POST", "/graphql", {"query": "mutation { resolveReviewThread(input: {threadId: \"T\"}) { thread "
                                                  "{ id } } }", "variables": {"owner": repo.split("/")[0],
                                                                             "name": repo.split("/")[1], "number": 42}}),
                   ("GET", "/orgs/combsmith/members", None), ("GET", "https://example.com/repos/%s/pulls/42" % repo, None)]
        for method, path, body in refused:
            with self.assertRaises(Unanswered, msg=(method, path, body)):
                token.send({"method": method, "path": path, "body": body})
        self.assertEqual(github.log, [])
        # The reads the act makes go through: the item's repo, who the token is, the org's Pause as the repo's list of
        # the org's variables (issue 362), and the facts port's own GraphQL reads of this pull request.
        owner, name = repo.split("/")
        allowed = [("GET", "/user", None), ("GET", PULL + "/reviews?per_page=100", None),
                   ("GET", "/repos/%s/actions/organization-variables?per_page=100" % repo, None),
                   ("POST", PULL + "/reviews", {"commit_id": HEAD, "event": "APPROVE"})]
        for query in (threads.QUERY, checks.QUERY, acceptance.QUERY):
            allowed.append(("POST", "/graphql", {"query": query, "variables": {"owner": owner, "name": name,
                                                                                "number": ITEM["number"]}}))
        allowed.append(("POST", "/graphql", {"query": threads.QUERY, "variables": {
            "owner": owner, "name": name, "number": ITEM["number"], "after": "Y3Vyc29y"}}))
        for method, path, body in allowed:
            token.send({"method": method, "path": path, "body": body})
        self.assertEqual(len(github.log), len(allowed))
        # The facts port's own reads go through as the ports send them: the first page with no cursor (CodeRabbit on PR
        # 321), and the closing references' read with none at all.
        pull = {"number": ITEM["number"], "base": {"repo": {"full_name": repo, "default_branch": "main"}, "ref": "main"}}
        for port in (lambda t: threads.read(t, pull, None), lambda t: checks.read(t, pull),
                     lambda t: acceptance.closing(t, pull)):
            seen = GitHub({("POST", "/graphql"): {"status": 500, "body": {}}})
            with self.assertRaises(Unanswered):
                port(effects.Approving(seen, ITEM))
            self.assertEqual([r["path"] for r in seen.log], ["/graphql"])
        # The facts port's queries of another pull request, or with more in them, are not this item's reads.
        for variables in ({"owner": owner, "name": name, "number": 43}, {"owner": "x", "name": name, "number": 42},
                          {"owner": owner, "name": name, "number": 42, "first": 1}):
            with self.assertRaises(Unanswered, msg=variables):
                token.send({"method": "POST", "path": "/graphql",
                            "body": {"query": threads.QUERY, "variables": variables}})
        # GraphQL bodies with more in them, another repo's name or a cursor that is no text are not this item's reads.
        for body in ({"query": threads.QUERY, "variables": {"owner": owner, "name": "other", "number": 42}},
                     {"query": threads.QUERY, "variables": {"owner": owner, "name": name, "number": 42}, "x": 1},
                     {"query": threads.QUERY, "variables": {"owner": owner, "name": name, "number": 42, "after": 5}}):
            with self.assertRaises(Unanswered, msg=body):
                token.send({"method": "POST", "path": "/graphql", "body": body})
        # Each step's transport is narrowed to it: with no item, only who the token is; with no head, no write.
        bare, reading = effects.Approving(github), effects.Approving(github, ITEM)
        bare.send({"method": "GET", "path": "/user", "body": None})
        for req in ({"method": "GET", "path": PULL + "/reviews?per_page=100", "body": None},
                    {"method": "POST", "path": "/graphql", "body": {"query": threads.QUERY, "variables": {
                        "owner": owner, "name": name, "number": 42}}}):
            with self.assertRaises(Unanswered):
                bare.send(req)
        with self.assertRaises(Unanswered):
            reading.send({"method": "POST", "path": PULL + "/reviews", "body": {"commit_id": HEAD, "event": "APPROVE"}})
        # And the act's whole run sends exactly one write, the approval of the head it read, whatever head that is.
        _, _, github = act()
        self.assertEqual(len(github.writes()), 1)
        other = "ab" * 20
        landed = dict(LANDED, commit_id=other)
        github = GitHub({("POST", PULL + "/reviews"): {"status": 200, "body": landed},
                         ("GET", PULL + "/reviews/7"): {"status": 200, "body": landed},
                         ("GET", PULL): {"status": 200, "body": {"state": "open", "head": {"sha": other}}}})
        done, ended, github = act(github, read=reads(head=other))
        self.assertEqual((github.writes(), effect(done)[1]),
                         ([("POST", PULL + "/reviews", {"commit_id": other, "event": "APPROVE"})], "applied"))

    def test_a_pull_request_not_open_at_the_commit_is_never_approved(self):  # issue 378, trials/P-7.refused.json
        # GitHub takes an approval of a closed pull request, so the act reads the pull request open at the commit it
        # approves before it sends anything: one closed, merged or at another head since the act read it is a change
        # under the act, refused with nothing sent; one that cannot be read is whose fault its status says.
        for pull, want, state in (({"state": "closed", "head": {"sha": HEAD}}, ("superseded", "not_open"), "refused"),
                                  ({"state": "closed", "merged": True, "head": {"sha": HEAD}}, ("superseded", "not_open"),
                                   "refused"),
                                  ({"state": "open", "merged": True, "head": {"sha": HEAD}}, ("superseded", "not_open"),
                                   "refused"),
                                  ({"state": "open", "head": {"sha": "f" * 40}}, ("superseded", "head_moved"), "refused")):
            done, ended, github = act(GitHub({("GET", PULL): {"status": 200, "body": pull}}))
            self.assertEqual((fault(ended), effect(done)[1:], github.writes()), (want, (state, None, want[1]), []), pull)
        for answer, want in (({"status": 500, "body": {}}, ("environment", "github_unavailable")),
                             ({"status": 403, "body": {}}, ("environment", "token_refused")),
                             ({"status": 200, "body": {"head": {"sha": HEAD}}}, ("environment", "github_unavailable")),
                             (None, ("environment", "github_unavailable"))):
            done, ended, github = act(GitHub({("GET", PULL): answer}))
            self.assertEqual((fault(ended), effect(done)[1], github.writes()), (want, "refused", []), answer)

    def test_a_pull_request_closed_under_the_act_claims_no_approval(self):  # issue 378, trials/P-7.refused.json
        # A pull request closed or merged between the act's read and its approval took the approval all the same: read
        # again after it, the act claims nothing, superseded, closed_under_act, and no Effect lands, so reconciliation
        # names the approval as a write no Effect recorded. One at another head now keeps the approval of the commit
        # it read; one that cannot be read claims nothing.
        opened = {"status": 200, "body": {"state": "open", "head": {"sha": HEAD}}}
        # The approval was sent, so the Effect is failed, never refused: a refusal sends nothing.
        for after, want, landed in (({"state": "closed", "head": {"sha": HEAD}}, ("superseded", "closed_under_act"),
                                     ("failed", None)),
                                    ({"state": "closed", "merged": True, "head": {"sha": HEAD}},
                                     ("superseded", "closed_under_act"), ("failed", None)),
                                    ({"state": "open", "head": {"sha": "f" * 40}}, (None, None), ("applied", NODE))):
            done, ended, github = act(GitHub({("GET", PULL): [opened, {"status": 200, "body": after}]}))
            self.assertEqual((fault(ended), effect(done)[1:3], len(github.writes())), (want, landed, 1), after)
        for after in ({"status": 500, "body": {}}, None, {"status": 200, "body": {"state": "open"}}):
            done, ended, github = act(GitHub({("GET", PULL): [opened, after]}))
            self.assertEqual((fault(ended), effect(done)[1:3]), (("environment", "not_read_back"), ("failed", None)), after)

    def test_an_approval_from_before_a_reopening_is_not_recovered(self):  # issue 378, decision 0079
        # The approver's approval of the head, submitted before the pull request was last reopened, does not stand: it
        # is not this act's to recover, and the act sends a fresh one, which the Kernel still wants. One submitted after
        # the reopening stands, and is recovered with nothing sent.
        earlier = review(at="2026-10-11T12:15:00Z")
        listed = {"status": 200, "body": [dict(LANDED, submitted_at="2026-10-11T12:15:00Z")]}
        done, ended, github = act(GitHub({("GET", PULL + "/reviews?per_page=100"): listed}),
                                  read=reads(facts(reviews=[earlier], last_reopened_at="2026-10-11T12:20:00Z")))
        self.assertEqual((effect(done), fault(ended), len(github.writes())), (("approve", "applied", NODE, None),
                                                                            (None, None), 1))
        # One submitted in the second of the reopening, or whose time cannot be read, is not after it either.
        for at in ("2026-10-11T12:20:00Z", None):
            listed = {"status": 200, "body": [dict(LANDED, submitted_at=at)]}
            done, ended, github = act(GitHub({("GET", PULL + "/reviews?per_page=100"): listed}),
                                      read=reads(facts(reviews=[review(at="2026-10-11T12:20:00Z")],
                                                       last_reopened_at="2026-10-11T12:20:00Z")))
            self.assertEqual((effect(done), fault(ended), len(github.writes())),
                             (("approve", "applied", NODE, None), (None, None), 1), at)
        later = review(at="2026-10-11T12:25:00Z")
        listed = {"status": 200, "body": [dict(LANDED, submitted_at="2026-10-11T12:25:00Z")]}
        done, ended, github = act(GitHub({("GET", PULL + "/reviews?per_page=100"): listed}),
                                  read=reads(facts(reviews=[later], last_reopened_at="2026-10-11T12:20:00Z")))
        self.assertEqual((effect(done), len(github.writes())), (("approve", "already_applied", NODE, None), 0))

    def test_no_approval_is_recovered_on_a_timeline_read_short(self):  # issue 378, Codex on PR 380
        # A timeline read short may hide the last reopening, so an approval of the head is not recovered on it: the
        # Kernel defers, and the act claims nothing.
        f = facts()
        f["complete"] = dict(f["complete"], timeline=False)
        listed = {"status": 200, "body": [dict(LANDED, submitted_at="2026-10-11T12:15:00Z")]}
        done, ended, github = act(GitHub({("GET", PULL + "/reviews?per_page=100"): listed}), read=reads(f))
        self.assertEqual((effect(done)[1:3], github.writes()), (("refused", None), []))
        self.assertEqual([r["path"] for r in github.log if r["method"] == "GET"], ["/user"])

    def test_a_re_run_claims_no_approval_of_a_pull_request_now_closed(self):  # issue 378, decision 0079
        # An earlier attempt's approval of a pull request closed under it claimed nothing; a re-run that finds the pull
        # request closed recovers nothing either, so the approval stays one no Effect recorded.
        listed = {"status": 200, "body": [dict(LANDED, submitted_at="2026-10-11T12:15:00Z")]}
        done, ended, github = act(GitHub({("GET", PULL + "/reviews?per_page=100"): listed}),
                                  read=reads(facts(state="closed")))
        self.assertEqual((effect(done)[1:3], fault(ended), github.writes()), (("refused", None),
                                                                            ("superseded", "not_wanted"), []))

    def test_a_run_no_decision_issued_an_approval_for_finds_none_and_writes_nothing(self):  # section 3.5
        admitted = record(runs=[])
        self.assertEqual(admitted["pull_requests"][0]["decision"]["outcome"], "admit")
        unreadable = record()
        unreadable["pull_requests"][0]["decision"]["outcome"] = "approve it"
        enqueue = record(facts(reviews=[review()]))
        self.assertEqual(enqueue["pull_requests"][0]["decision"]["action"], "enqueue")
        twice = record()
        twice["pull_requests"].append(dict(twice["pull_requests"][0], facts=dict(
            twice["pull_requests"][0]["facts"], item=dict(ITEM, number=43))))
        twice["pull_requests"][1]["decision"] = dict(twice["pull_requests"][1]["decision"], item=dict(ITEM, number=43))
        for rec, run_id in ((record(), "r_01JA7R"), (admitted, RUN), (unreadable, RUN), (enqueue, RUN), (twice, RUN),
                            ({"schema": "pass/1"}, RUN), (None, RUN), (record(entry_run=None), RUN)):
            done, ended, github = act(rec=rec, run_id=run_id)
            self.assertEqual(fault(ended), ("superseded", "no_decision"), run_id)
            self.assertEqual(effect(done)[1:], ("refused", None, "no_decision"))
            self.assertEqual(github.log, [])

    def test_only_the_approvers_own_token_approves(self):  # issue 195, ruling 4.2
        for who in ({"login": "don-petry", "type": "User"}, {"login": APPROVER, "type": "Bot"}, {"login": APPROVER},
                    [], {"login": APPROVER.upper(), "type": "User"}):
            done, ended, github = act(at("/user", {"status": 200, "body": who}))
            self.assertEqual(fault(ended), ("environment", "approver_unreadable"), who)
            self.assertEqual(github.writes(), [])
        for status, want in ((401, "token_refused"), (403, "token_refused"), (404, "token_refused"),
                             (500, "github_unavailable"), (429, "github_unavailable"), (None, "github_unavailable")):
            done, ended, github = act(at("/user", None if status is None else {"status": status, "body": {}}))
            self.assertEqual(fault(ended), ("environment", want), status)
            self.assertEqual([r["path"] for r in github.log], ["/user"])

    def test_an_approval_that_landed_is_recovered_and_nothing_is_written(self):  # section 3.6
        landed = dict(LANDED, id=5, node_id="PRR_landed")
        # The facts, read through the same token, show the approval standing: the Kernel wants no other.
        stands = reads(facts(reviews=[review()]))
        done, ended, github = act(at(PULL + "/reviews?per_page=100", {"status": 200, "body": [landed]}), read=stands)
        self.assertEqual(effect(done), ("approve", "already_applied", "PRR_landed", None))
        self.assertEqual(fault(ended), (None, None))
        self.assertEqual(github.writes(), [])
        # Recovered before the Kernel is asked: a re-run after a landed approval does not fail, though the Kernel now
        # reads the item approved and issues no second one.
        done, _, _ = act(at(PULL + "/reviews?per_page=100", {"status": 200, "body": [landed]}),
                         read=reads(facts(reviews=[review()])))
        self.assertEqual(effect(done)[1], "already_applied")
        # None of these is the approver's standing approval of this commit: each is approved afresh.
        for other in (dict(landed, state="DISMISSED"), dict(landed, state="COMMENTED"), dict(landed, commit_id="f" * 40),
                      dict(landed, user={"login": "don-petry"}), dict(landed, node_id=None), "a review"):
            done, ended, github = act(at(PULL + "/reviews?per_page=100", {"status": 200, "body": [other]}))
            self.assertEqual(effect(done)[1:3], ("applied", NODE), other)
            self.assertEqual(len(github.writes()), 1)
        # A landed approval the Kernel does not read standing, the approver's write access lost among them, is no success:
        # the Kernel would issue it again at every pass. It is the environment's, which the Run ceiling bounds (Muse).
        lost = facts(reviews=[review(can_write=False)])
        done, ended, github = act(at(PULL + "/reviews?per_page=100", {"status": 200, "body": [landed]}), read=reads(lost))
        self.assertEqual((effect(done)[1:], fault(ended), github.writes()),
                         (("failed", None, "approval_not_standing"), ("environment", "approval_not_standing"), []))
        # Only the approver's own reviews of this commit are read: another person's later review, or the approver's of
        # another commit, leaves the approval standing (Argon's read).
        for after in (dict(landed, id=8, state="COMMENTED", user={"login": "don-petry"}),
                      dict(landed, id=8, state="CHANGES_REQUESTED", commit_id="f" * 40)):
            done, _, github = act(at(PULL + "/reviews?per_page=100", {"status": 200, "body": [landed, after]}),
                                  read=stands)
            self.assertEqual((effect(done)[1:3], github.writes()), (("already_applied", "PRR_landed"), []), after)
        # An approval of the head read is recovered only for the content the Decision approved: otherwise the Kernel,
        # asked again, decides, and here wants nothing (Argon's read).
        done, ended, github = act(at(PULL + "/reviews?per_page=100", {"status": 200, "body": [landed]}),
                                  read=reads(facts(content_id="sha256:bbbb")))
        self.assertEqual((fault(ended), github.writes()), (("superseded", "not_wanted"), []))
        # The approver's latest review of the commit is the one that stands: a request for changes after it supersedes
        # the approval, which is approved afresh (the fresh review).
        later = dict(landed, id=6, node_id="PRR_later", state="CHANGES_REQUESTED")
        done, ended, github = act(at(PULL + "/reviews?per_page=100", {"status": 200, "body": [landed, later]}))
        self.assertEqual((effect(done)[1:3], len(github.writes())), (("applied", NODE), 1))
        done, _, github = act(at(PULL + "/reviews?per_page=100", {"status": 200, "body": [later, landed]}), read=stands)
        self.assertEqual((effect(done)[1:3], github.writes()), (("already_applied", "PRR_landed"), []))
        # A list that cannot be read, or may be cut short, recovers nothing and writes nothing.
        for answer, want in (({"status": 200, "body": {}}, "facts_unreadable"),
                             ({"status": 200, "body": [dict(landed, state="COMMENTED")] * 100}, "facts_unreadable"),
                             ({"status": 502, "body": {}}, "github_unavailable"), (None, "github_unavailable"),
                             ({"status": 429, "body": {}}, "github_unavailable"),
                             ({"status": 403, "body": {}}, "token_refused")):
            done, ended, github = act(at(PULL + "/reviews?per_page=100", answer))
            self.assertEqual(fault(ended), ("environment", want), answer)
            self.assertEqual(github.writes(), [])

    def test_the_act_approves_only_what_the_kernel_asked_again_still_wants(self):  # I-38, issue 195 ruling 4.5
        stopped = [reads(facts(label_events=[labelled("factory:hold")])), reads(facts(content_id="sha256:bbbb")),
                   reads(ctx=context(paused=True)), reads(facts(author=APPROVER)),
                   reads(facts(state="closed")),
                   reads(runs=REVIEWED + [run(role="dev-lead", intent="fix-findings", status="in_progress", name="r7",
                                              at="2026-10-11T12:40:00Z")]),
                   reads(ctx=context(unidentified_runs=[{"run": "39100000002", "created_at": NOW,
                                                          "status": "queued"}]))]
        for read in stopped:
            done, ended, github = act(read=read)
            self.assertEqual(fault(ended), ("superseded", "not_wanted"))
            self.assertEqual(effect(done)[1:], ("refused", None, "not_wanted"))
            self.assertEqual(github.writes(), [])
        # This Run is left out of the records and of the Runs counted active, and so is its own unnamed listing.
        mine = run(role="pr-review", intent="issue-approval", status="in_progress", name=RUN, at="2026-10-11T12:50:00Z")
        flight = context(active_runs=1, unidentified_runs=[{"run": GITHUB_RUN, "created_at": NOW,
                                                             "status": "in_progress"}])
        done, ended, github = act(read=reads(runs=REVIEWED + [mine], ctx=flight))
        self.assertEqual((effect(done)[1], fault(ended)), ("applied", (None, None)))

    def test_the_act_approves_no_change_to_a_model_lenss_inputs_that_no_judge_approved(self):  # issue 140, ruling 7
        # The pass record holds the approval, issued while a different person's approval of the change stood; by the
        # time the act reads, a person has dismissed it. Nothing is posted, and the reason is not_wanted.
        agent = {"class": "agent", "author": "combsmith-sf-dev-lead[bot]", "last_pusher": "combsmith-sf-dev-lead[bot]"}
        changed = facts(changed_paths=[{"path": "kernel/gate.py", "previous": None}],
                        diff={"files": 1, "lines": 4, "truncated": False, "characters": 160}, **agent)
        judge = review(kind="human", name="a-colleague")
        rec = record(dict(changed, reviews=[judge]))
        self.assertEqual(rec["pull_requests"][0]["decision"].get("action"), "issue_approval")
        dismissed = review(kind="human", name="a-colleague", state="dismissed",
                           dismissed_by={"kind": "human", "name": "a-colleague", "can_write": True},
                           dismissed_from="approved")
        for now in (dict(changed, reviews=[dismissed]), dict(changed, reviews=[]),
                    dict(changed, reviews=[dismissed, review()])):
            done, ended, github = act(rec=rec, read=reads(now))
            self.assertEqual(fault(ended), ("superseded", "not_wanted"))
            self.assertEqual(github.writes(), [])
        # While the judge's approval stands, the act approves as for any change.
        done, ended, github = act(rec=rec, read=reads(dict(changed, reviews=[judge])))
        self.assertEqual(effect(done)[1], "applied")

    def test_each_fault_of_the_act_is_classed_as_the_design_classes_it(self):  # L-03, decision 0003, ruling 6
        def posting(answer, pull=None, back=None):
            over = {("POST", PULL + "/reviews"): answer}
            if pull is not None:
                # Open at the commit as the act reads it before the approval, then as it is read again after.
                over[("GET", PULL)] = [{"status": 200, "body": {"state": "open", "head": {"sha": HEAD}}}, pull]
            if back is not None:
                over[("GET", PULL + "/reviews/7")] = back
            return GitHub(over)
        moved = {"status": 200, "body": {"state": "open", "head": {"sha": "f" * 40}}}
        closed = {"status": 200, "body": {"state": "closed", "head": {"sha": HEAD}}}
        cases = [
            (GitHub(), failing(Moved("moved")), ("superseded", "head_moved"), "refused"),
            (GitHub(), failing(Unanswered("no")), ("environment", "facts_unreadable"), "refused"),
            (GitHub(), failing(KeyError("x")), ("environment", "facts_unreadable"), "refused"),
            (GitHub(), reads(head="not a commit"), ("environment", "facts_unreadable"), "refused"),
            (GitHub(), reads(head=None), ("environment", "facts_unreadable"), "refused"),
            (GitHub(), failing(IndexError("x")), ("environment", "facts_unreadable"), "refused"),
            (GitHub(), lambda: (None, HEAD, REVIEWED, context()), ("environment", "facts_unreadable"), "refused"),
            (GitHub(), lambda: (facts(), HEAD, None, context()), ("environment", "facts_unreadable"), "refused"),
            (GitHub(), lambda: ({}, HEAD, REVIEWED, context()), ("environment", "facts_unreadable"), "refused"),
            (GitHub(), lambda: (dict(facts(), state="?"), HEAD, REVIEWED, context()), ("environment", "facts_unreadable"),
             "refused"),
            (GitHub(), lambda: (facts(), HEAD, [None], context()), ("environment", "facts_unreadable"), "refused"),
            (GitHub(), lambda: (facts(), HEAD, [dict(run(), status="?")], context()), ("environment", "facts_unreadable"),
             "refused"),
            (GitHub(), lambda: (facts(), HEAD, REVIEWED, None), ("environment", "facts_unreadable"), "refused"),
            (GitHub(), reads(ctx=context(paused=None)), ("environment", "facts_unreadable"), "refused"),
            (GitHub(), reads(ctx=context(paused="true")), ("environment", "facts_unreadable"), "refused"),
            (posting({"status": 201, "body": LANDED}), None, ("environment", "not_read_back"), "failed"),
            (posting({"status": 200, "body": [LANDED]}), None, ("environment", "not_read_back"), "failed"),
            (posting({"status": 401, "body": {}}), None, ("environment", "token_refused"), "refused"),
            (posting({"status": 403, "body": {}}), None, ("environment", "token_refused"), "refused"),
            (posting({"status": 404, "body": {}}), None, ("environment", "token_refused"), "refused"),
            (posting({"status": 500, "body": {}}), None, ("environment", "github_unavailable"), "failed"),
            (posting({"status": 429, "body": {}}), None, ("environment", "github_unavailable"), "failed"),
            (posting(None), None, ("environment", "github_unavailable"), "failed"),
            (posting({"status": 422, "body": {"message": "x"}}), None, ("item", "approval_refused"), "failed"),
            (posting({"status": 422, "body": {}}, pull=moved), None, ("superseded", "head_moved"), "failed"),
            (posting({"status": 422, "body": {}}, pull=closed), None, ("superseded", "not_open"), "failed"),
            (posting({"status": 422, "body": {}}, pull={"status": 500, "body": {}}), None,
             ("environment", "github_unavailable"), "failed"),
            # The pull request read again is classed by its own status, and an answer missing its parts is unreadable
            # (Codex on PR 321).
            (posting({"status": 422, "body": {}}, pull={"status": 403, "body": {}}), None,
             ("environment", "token_refused"), "failed"),
            (posting({"status": 422, "body": {}}, pull={"status": 404, "body": {}}), None,
             ("environment", "token_refused"), "failed"),
            (posting({"status": 422, "body": {}}, pull={"status": 200, "body": {"head": {"sha": HEAD}}}), None,
             ("environment", "github_unavailable"), "failed"),
            (posting({"status": 422, "body": {}}, pull={"status": 200, "body": {"state": "open", "head": {}}}), None,
             ("environment", "github_unavailable"), "failed"),
            (posting({"status": 200, "body": {"id": "7"}}), None, ("environment", "not_read_back"), "failed"),
            (posting({"status": 200, "body": LANDED}, back={"status": 500, "body": {}}), None,
             ("environment", "not_read_back"), "failed"),
            (posting({"status": 200, "body": LANDED}, back={"status": 200, "body": dict(LANDED, id=8)}), None,
             ("environment", "not_read_back"), "failed"),
        ]
        for answer in (dict(LANDED, state="COMMENTED"), dict(LANDED, commit_id="f" * 40),
                       dict(LANDED, user={"login": "don-petry"}), dict(LANDED, node_id=""), dict(LANDED, user=None)):
            cases.append((posting({"status": 200, "body": LANDED}, back={"status": 200, "body": answer}), None,
                          ("item", "read_back_differs"), "failed"))
        for github, read, want, state in cases:
            done, ended, _ = act(github, read=read)
            self.assertEqual(fault(ended), want, (want, state))
            self.assertEqual(effect(done)[1:], (state, None, want[1]), want)
            # The act runs no model: its outcome is never capacity, which would defer every model Run.
            self.assertNotEqual(ended["outcome"], "capacity")
        # Only a status and what is read again decide the class: GitHub's words decide nothing.
        for words in ("Bad credentials", "rate limit", "Pull request is closed", "head moved"):
            _, ended, _ = act(posting({"status": 422, "body": {"message": words}}))
            self.assertEqual(fault(ended), ("item", "approval_refused"), words)


class Records(unittest.TestCase):
    def test_an_approval_is_an_effect_apply_records_and_no_result_may_ask_for(self):  # issue 195, ruling 5
        done = json.loads((ROOT / "examples" / "applied.approval.json").read_text())
        self.assertEqual(validate(done, SCHEMAS["applied"], schemas=SCHEMAS), [])
        self.assertEqual([e["type"] for e in done["effects"]], ["approve"])
        asked = json.loads((ROOT / "examples" / "invalid" / "result.asks-for-an-approval.json").read_text())
        self.assertNotEqual(validate(asked, SCHEMAS["result"], schemas=SCHEMAS), [])
        self.assertNotIn("approve", SCHEMAS["effect"]["$defs"]["type"]["enum"])
        # applied/1 records every type effect/1 lets a Result ask for, and approve beside them, which no Result may.
        recorded = SCHEMAS["applied"]["properties"]["effects"]["items"]["properties"]["type"]["enum"]
        self.assertEqual(recorded, SCHEMAS["effect"]["$defs"]["type"]["enum"] + ["approve"])


if __name__ == "__main__":
    unittest.main()
