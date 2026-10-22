"""The `apply` job and the identity port (issue 194, PR 2), against a fake GitHub that answers as the trials recorded it.

Nothing here reaches the network. The JWT is signed by the system's `openssl` with a throwaway key made for the test and
handed to it through a pipe, as the job hands the App's key.
"""
from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest

from adapters import github, identity
from harness import apply, shared
from tests import support

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPS = json.loads((ROOT / "config" / "apps.json").read_text())
REPO = "combsmith/software-factory"
SECRET = "a-stand-in-for-an-installation-token"


def throwaway_key() -> bytes:
    """A key made for this test alone, on `openssl`'s output and never a file."""
    return subprocess.run(["openssl", "genrsa", "2048"], capture_output=True, check=True).stdout


class GitHub:
    """A fake GitHub: answers each request it holds once, in order, and records every request it was sent."""

    def __init__(self, *answers):
        self.answers, self.sent = list(answers), []

    def send(self, req: dict) -> dict:
        self.sent.append(req)
        if not self.answers:
            raise github.Unanswered("nothing left")
        want, answer = self.answers.pop(0)
        if want != (req["method"], req["path"]):
            raise github.Unanswered("asked %s %s" % (req["method"], req["path"]))
        return answer


def installation(app_id=5364144, status=200) -> tuple:
    return ("GET", "/repos/%s/installation" % REPO), {"status": status, "headers": {}, "body": {"id": 172571064,
                                                                                               "app_id": app_id}}


def minted(status=201, **over) -> tuple:
    body = {"token": SECRET, "expires_at": "2026-10-22T13:00:00Z",
            "permissions": {"pull_requests": "write", "metadata": "read"}, "repository_selection": "selected",
            "repositories": [{"full_name": REPO, "name": "software-factory"}]}
    body.update(over)
    return ("POST", "/app/installations/172571064/access_tokens"), {"status": status, "headers": {}, "body": body}


def claims(jwt: str) -> tuple:
    head, body, _ = jwt.split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)
    return (json.loads(base64.urlsafe_b64decode(pad(head))), json.loads(base64.urlsafe_b64decode(pad(body))))


class Identity(unittest.TestCase):
    def test_the_jwt_is_signed_by_openssl_through_a_pipe_and_never_a_file(self):  # ruling 6
        key = throwaway_key()
        token = identity.jwt(5364144, key, 1_700_000_000)
        head, body = claims(token)
        self.assertEqual(head, {"alg": "RS256", "typ": "JWT"})
        self.assertEqual(body, {"iat": 1_700_000_000 - 60, "exp": 1_700_000_000 + 540, "iss": 5364144})
        # The signature is the key's, over the header and the claims as sent.
        public = subprocess.run(["openssl", "rsa", "-pubout"], input=key, capture_output=True, check=True).stdout
        signed_part, signature = token.rsplit(".", 1)
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "pub.pem").write_bytes(public)
            (pathlib.Path(d) / "sig").write_bytes(base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)))
            ok = subprocess.run(["openssl", "dgst", "-sha256", "-verify", "pub.pem", "-signature", "sig"], cwd=d,
                                input=signed_part.encode(), capture_output=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        # openssl is given the key's descriptor, its own environment and the message, and no path of a file.
        seen = []

        def run(args, **kw):
            seen.append((args, kw))
            return subprocess.CompletedProcess(args, 0, b"signature", b"")
        self.assertEqual(identity.signed(b"m", key, run=run), b"signature")
        args, kw = seen[0]
        self.assertEqual(args[:4] + args[5:], ["openssl", "dgst", "-sha256", "-sign", "-binary"])
        self.assertRegex(args[4], r"^/dev/fd/[0-9]+$")
        self.assertEqual((kw["pass_fds"], kw["input"], kw["env"]), ((int(args[4].split("/")[-1]),), b"m",
                                                                    {"PATH": "/usr/bin:/bin"}))
        # What cannot be a key, or cannot sign, is refused by a code that names no key.
        for bad in (b"", "a string", b"x" * (identity.KEY_MOST + 1)):
            with self.assertRaisesRegex(identity.Refused, "^key_unreadable$"):
                identity.signed(b"m", bad)
        with self.assertRaisesRegex(identity.Refused, "^key_cannot_sign$"):
            identity.signed(b"m", b"-----BEGIN PRIVATE KEY-----\nnot a key\n-----END PRIVATE KEY-----\n")
        for code, out in ((0, b""), (1, b"half a signature")):
            with self.assertRaisesRegex(identity.Refused, "^key_cannot_sign$"):
                identity.signed(b"m", key, run=lambda a, **k: subprocess.CompletedProcess(a, code, out, b""))
        for app_id, now in ((0, 1), (True, 1), ("5364144", 1), (5364144, 1.5)):
            with self.assertRaises(identity.Refused):
                identity.jwt(app_id, key, now, sign=lambda m, k: b"s")

    def test_a_token_is_narrowed_to_the_permissions_its_effects_need(self):  # ruling 6
        review = APPS["apps"]["pr-review"]
        self.assertEqual(identity.permissions(review, APPS["needs"], ["submit_review", "resolve_thread", "comment",
                                                                      "submit_review"]),
                         {"pull_requests": "write"})
        self.assertEqual(identity.permissions(review, APPS["needs"], []), {})
        # An Effect whose need waits or is not in the table, or that the App was not granted, is never minted for.
        needs = dict(APPS["needs"], **{"effect:create_check_run": {"waits_on": "the grant"}})
        for effects, table, code in ((["create_check_run"], APPS["needs"], "effect_not_grantable"),
                                     (["create_check_run"], needs, "effect_not_grantable"),
                                     (["enqueue_merge"], APPS["needs"], "effect_not_grantable")):
            with self.assertRaisesRegex(identity.Refused, "^%s$" % code):
                identity.permissions(review, table, effects)
        for app in (APPS["apps"]["reader"], APPS["apps"]["controller"],
                    dict(review, permissions=dict(review["permissions"],
                                                  pull_requests={"level": "read", "needs": ["effect:submit_review"]})),
                    dict(review, permissions=dict(review["permissions"],
                                                  pull_requests={"level": "write", "needs": ["effect:comment"]}))):
            with self.assertRaisesRegex(identity.Refused, "^effect_not_granted$"):
                identity.permissions(app, APPS["needs"], ["submit_review"])
        # A read need and a write need on one permission ask for it once, at write.
        both = dict(APPS["needs"], **{"effect:comment": {"permission": "pull_requests", "level": "read"}})
        self.assertEqual(identity.permissions(review, both, ["comment", "submit_review"]), {"pull_requests": "write"})
        self.assertEqual(identity.permissions(review, both, ["comment"]), {"pull_requests": "read"})
        first = dict(APPS["needs"], **{"effect:submit_review": {"permission": "pull_requests", "level": "read"}})
        self.assertEqual(identity.permissions(review, first, ["comment", "submit_review"]), {"pull_requests": "write"})

    def test_a_token_is_minted_for_the_one_repo_and_held_to_what_was_asked(self):  # ruling 6
        review = APPS["apps"]["pr-review"]
        hub = GitHub(installation(), minted())
        token = identity.mint(hub, review, REPO, {"pull_requests": "write"})
        self.assertEqual(token.reveal(), SECRET)
        self.assertEqual(hub.sent[1]["body"], {"repositories": ["software-factory"],
                                               "permissions": {"pull_requests": "write"}})
        # The token never says what it is.
        self.assertNotIn(SECRET, repr(token) + str(token) + json.dumps(token.permissions))
        for answers in ((installation(app_id=1), minted()), (installation(status=404), minted()),
                        (installation(), minted(status=422)), (installation(), minted(repository_selection="all")),
                        (installation(), minted(permissions={"pull_requests": "write", "metadata": "read",
                                                             "contents": "read"})),
                        (installation(), minted(repositories=[{"full_name": "combsmith/other"}])),
                        (installation(), minted(repositories=[])), (installation(), minted(token="two words")),
                        (installation(), minted(token=None))):
            with self.assertRaises(identity.Refused) as caught:
                identity.mint(GitHub(*answers), review, REPO, {"pull_requests": "write"})
            self.assertNotIn(SECRET, str(caught.exception))
        for repo, wanted in (("combsmith", {"pull_requests": "write"}), ("a/b/c", {"pull_requests": "write"}),
                             (REPO, {})):
            with self.assertRaisesRegex(identity.Refused, "^token_unreadable$"):
                identity.mint(GitHub(), review, repo, wanted)

    def test_a_token_is_revoked_only_when_github_says_so(self):  # ruling 6
        gone = ("DELETE", "/installation/token")
        self.assertTrue(identity.revoke(GitHub((gone, {"status": 204, "headers": {}, "body": None}))))
        self.assertFalse(identity.revoke(GitHub((gone, {"status": 404, "headers": {}, "body": None}))))
        self.assertFalse(identity.revoke(GitHub()))


RUN = "r_01JA7Q"
RELEASE = "factory/v0.3.1"
HEAD = "9f1c2d3e4b5a69788796a5b4c3d2e1f0a9b8c7d6"
NOW = "2026-10-11T13:00:00Z"
ROLE = json.loads((ROOT / "examples" / "role.owner.json").read_text())
RUBRIC = json.loads((ROOT / "config" / "rubric-pr-review.json").read_text())
AUTHORITY = json.loads((ROOT / "config" / "authority.json").read_text())
RESULT = json.loads((ROOT / "examples" / "result.json").read_text())


def the_task(**over) -> dict:
    """The Task of Run RUN: the review Intent on the content the Kernel admits on support's facts."""
    t = {"schema": "task/1", "run": RUN, "release": RELEASE, "role": "pr-review", "intent": "review-change",
         "item": dict(support.ITEM), "content_id": "sha256:aaaa", "findings": [], "texts": [],
         "limits": {"turns": 8, "repair_turns": 1, "seconds": 600, "cost_ceiling_usd": 2.0}, "tier": "standard",
         "permitted_effects": ["submit_review", "create_check_run"], "result_schema": "result/1", "omitted": []}
    t.update(over)
    return t


def result(**over) -> dict:
    r = json.loads(json.dumps(RESULT))
    r.update(run=RUN, release=RELEASE)
    r.update(over)
    return r


def runs(status="in_progress") -> list:
    """The run records read again: this Run's own, still in progress, which the Kernel is asked without."""
    return [support.run(name=RUN, status=status, at="2026-10-11T12:58:00Z")]


def refused(task=None, res=None, facts=None, records=None, context=None, rubric=RUBRIC, role=ROLE, github_run=4242):
    return apply.refusal(task or the_task(), res or result(), facts or support.facts(),
                         runs() if records is None else records,
                         support.context(active_runs=1) if context is None else context, support.CONFIG, NOW, role,
                         rubric, AUTHORITY, github_run)


def read_back(task, res, **over) -> list:
    """What the effects port reads back for each Effect asked: the review and its comments' threads, the check run
    and its annotations."""
    out = []
    for effect_id, kind, req in apply.requests(task, res, HEAD, ROLE):
        if kind == "submit_review":
            back = {"state": "applied", "key": "PRR_kwDOA7",
                    "surfaces": {c["finding"]: "PRRT_kw%d" % i for i, c in enumerate(req["comments"], 7)}}
        elif kind == "create_check_run":
            back = {"state": "applied", "key": "CR_kwDOA7",
                    "surfaces": {a["finding"]: "CR_kwDOA7:%s" % a["finding"] for a in req["annotations"]}}
        else:
            back = {"state": "applied", "key": "K_%s" % effect_id, "surfaces": {}}
        back.update(over.get(effect_id, {}))
        out.append((effect_id, kind, back))
    return out


class Apply(unittest.TestCase):
    def test_a_result_on_the_item_as_admitted_is_written_and_recorded_from_what_was_read_back(self):  # rulings 5, 7
        task, res = the_task(), result()
        self.assertIsNone(refused())
        asked = apply.requests(task, res, HEAD, ROLE)
        self.assertEqual([(e, k) for e, k, _ in asked], [("e1", "submit_review"), ("e2", "create_check_run")])
        review, check = asked[0][2], asked[1][2]
        # A review is a comment on the commit the Decision admitted, so a Role's review never approves.
        self.assertEqual((review["commit"], review["event"], review["body"]), (HEAD, "COMMENT", ""))
        self.assertEqual(review["comments"], [{"path": "kernel/decide.py", "start_line": 88, "end_line": 94,
                                               "finding": "n1", "body": res["effects"]["submit_review"][0]["comments"][0]["body"]}])
        # A check run's name, conclusion and key are apply's, from the Task's Role and Run.
        self.assertEqual((check["commit"], check["name"], check["conclusion"], check["external_id"]),
                         (HEAD, "factory / pr-review", "success", "%s:e2" % RUN))
        record = apply.applied(task, res, read_back(task, res), ROLE)
        self.assertEqual(shared.errors(record, "applied"), [])
        self.assertEqual([(e["id"], e["state"], e["key"], e["reason"]) for e in record["effects"]],
                         [("e1", "applied", "PRR_kwDOA7", None), ("e2", "applied", "CR_kwDOA7", None)])
        # Each Finding is written whole from where it was read back, its id from the source and the surface.
        n1, n2 = record["findings"]
        self.assertEqual((n1["surface"], n1["id"], n1["source"], n1["content_id"], n1["adopted_from"]),
                         ({"type": "thread", "key": "PRRT_kw7"}, apply.finding_id("pr-review", n1["surface"]),
                          {"lens": "pr-review", "kind": "role", "actor": "combsmith-sf-pr-review[bot]"}, "sha256:aaaa",
                          res["findings"][0]["adopted_from"]))
        self.assertEqual((n2["surface"], n2["category"], n2["severity"]),
                         ({"type": "annotation", "key": "CR_kwDOA7:n2"}, "delivery", "minor"))
        self.assertNotEqual(n1["id"], apply.finding_id("pr-review", {"type": "thread", "key": "PRRT_kw8"}))
        self.assertEqual(apply.outcome(task, record), {"schema": "outcome/1", "run": RUN, "release": RELEASE,
                                                       "outcome": None, "reason": None})
        # Recovered by its key, an Effect already written is recorded so.
        again = apply.applied(task, res, read_back(task, res, e1={"state": "already_applied"}), ROLE)
        self.assertEqual(again["effects"][0]["state"], "already_applied")

    def test_a_change_under_the_run_writes_nothing_and_is_superseded(self):  # ruling 5, I-21, I-38
        hold = support.labelled("factory:hold")
        other = support.run(name="r_01JA7Z", status="in_progress", at="2026-10-11T12:59:00Z")
        for over, code in (({"facts": support.facts(state="closed")}, "item_closed"),
                           ({"facts": support.facts(state="merged")}, "item_closed"),
                           ({"facts": support.facts(content_id="sha256:bbbb")}, "content_moved"),
                           ({"context": support.context(paused=True, active_runs=1)}, "paused"),
                           ({"context": support.context(paused=None, active_runs=1)}, "pause_unreadable"),
                           ({"facts": support.facts(label_events=[hold])}, "item_held"),
                           ({"records": runs() + [other]}, "not_admitted"),
                           ({"task": the_task(intent="adjudicate-findings")}, "not_admitted"),
                           ({"task": the_task(role="dev-lead")}, "not_admitted")):
            self.assertEqual(refused(**over), ("superseded", code), code)
        # A Run listed before its name defers, but this one's own, by its GITHUB_RUN_ID (decision 0036).
        listed = lambda *ids: support.context(active_runs=1, unidentified_runs=[
            {"run": i, "created_at": "2026-10-11T12:58:00Z", "status": "in_progress"} for i in ids])
        self.assertIsNone(refused(context=listed(4242)))
        self.assertEqual(refused(context=listed(4242, 4243)), ("superseded", "not_admitted"))
        self.assertEqual(refused(context=listed(4242), github_run=4243), ("superseded", "not_admitted"))
        # This Run, in progress, is left out of the Runs and of those counted active, or the Kernel admits nothing.
        self.assertIsNone(refused(context=support.context(active_runs=1)))
        full = support.context(active_runs=support.CONFIG["limits"]["org_max_active_runs"])
        self.assertIsNone(refused(context=full))
        self.assertEqual(refused(context=full, records=runs("completed")), ("superseded", "not_admitted"))

    def test_a_result_not_the_runs_or_not_completed_writes_nothing(self):  # ruling 5
        for over, want in (({"run": "r_01JA7Z"}, ("item", "result_not_the_runs")),
                           ({"release": "factory/v0.3.2"}, ("item", "result_not_the_runs")),
                           ({"status": "failed", "reason": "result_invalid"}, ("item", "result_invalid")),
                           ({"status": "failed", "reason": "task_too_large"}, ("item", "task_too_large")),
                           ({"status": "failed", "reason": "engine_failed"}, ("environment", "engine_failed")),
                           ({"status": "failed", "reason": "credential_missing"}, ("environment", "credential_missing")),
                           ({"status": "incomplete", "reason": "turns_spent"}, ("item", "turns_spent")),
                           ({"status": "refused", "reason": None}, ("item", "refused"))):
            self.assertEqual(refused(res=result(**over)), want, over)

    def test_an_uncovered_result_writes_nothing(self):  # decision 0049
        short = result(coverage=result()["coverage"][1:])
        self.assertEqual(refused(res=short), ("item", "uncovered"))
        self.assertEqual(refused(rubric={"criteria": []}), ("environment", "coverage_unreadable"))
        self.assertEqual(refused(facts=support.facts(changed_paths=None)), ("superseded", "not_admitted"))
        self.assertIsNone(refused(res=short, rubric=None))      # an Intent that does not review has no rubric

    def test_effects_the_task_does_not_permit_or_findings_posted_other_than_once_write_nothing(self):  # 3.6, 3.7
        base = result()
        e = base["effects"]
        review, check = e["submit_review"][0], e["create_check_run"][0]
        n1, n2 = base["findings"]
        cases = (
            ({"effects": dict(e, comment=[{"id": "e3", "on": "item", "body": "x"}])}, "effect_not_permitted"),
            ({"effects": {"submit_review": [review], "create_check_run": [dict(check, id="e1")]}}, "effect_named_twice"),
            ({"findings": [n1, dict(n2, ref="n1")]}, "finding_named_twice"),
            ({"effects": {"submit_review": [dict(review, comments=review["comments"] + [{"finding": "n9", "body": "x"}])],
                          "create_check_run": [check]}}, "finding_not_raised"),
            ({"effects": {"submit_review": [review]}}, "finding_not_posted_once"),
            ({"effects": {"submit_review": [review, dict(review, id="e3")], "create_check_run": [check]}},
             "finding_not_posted_once"),
            ({"findings": [n1, dict(n2, severity="major")]}, "finding_gates"),
            ({"findings": [dict(n1, severity="minor"), n2]}, "finding_does_not_gate"),
            ({"findings": [{k: v for k, v in n1.items() if k != "location"}, n2]}, "finding_has_no_place"),
            ({"findings": [n1, {k: v for k, v in n2.items() if k != "location"}]}, "finding_has_no_place"))
        for over, code in cases:
            self.assertEqual(refused(res=result(**over)), ("item", code), code)
        # A security Finding gates at any severity, so it is a review comment.
        secure = result(findings=[dict(n1, category="security", severity="info"), n2])
        self.assertIsNone(refused(res=secure))
        self.assertEqual(refused(res=result(findings=[n1, dict(n2, category="security")])), ("item", "finding_gates"))
        # A refused Result lists each Effect it asked for refused, and posts nothing.
        record = apply.applied(the_task(), base, [], ROLE, refused="finding_gates")
        self.assertEqual(shared.errors(record, "applied"), [])
        self.assertEqual([(x["id"], x["state"], x["reason"]) for x in record["effects"]],
                         [("e1", "refused", "finding_gates"), ("e2", "refused", "finding_gates")])
        self.assertEqual(record["findings"], [])
        self.assertEqual(apply.outcome(the_task(), record, ("item", "finding_gates"))["outcome"], "item")

    def test_a_disposition_gives_one_half_and_only_the_half_its_role_may_make(self):  # section 3.8
        threads = [support.thread("PRRT_kw7"), support.thread("PRRT_kw8", category="security"),
                   support.thread("PRRT_kw9", kind="human", name="don-petry")]
        facts = support.facts(threads=threads)
        fid = lambda key, lens="pr-review": apply.finding_id(lens, {"type": "thread", "key": key})
        task = the_task(permitted_effects=["submit_review", "create_check_run", "resolve_thread"],
                        findings=sorted([fid("PRRT_kw7"), fid("PRRT_kw8"), fid("PRRT_kw9", "don-petry")]))
        author = dict(ROLE, name="dev-lead", kind="author")

        def asked(dispositions, resolve=(), role=ROLE):
            effects = dict(result()["effects"], resolve_thread=[{"id": "e%d" % (5 + i), "thread": th}
                                                                for i, th in enumerate(resolve)])
            return refused(task=task, res=result(dispositions=dispositions, effects=effects), facts=facts, role=role)
        self.assertIsNone(asked([{"finding": fid("PRRT_kw7"), "decision": {"result": "accepted"}}], ["PRRT_kw7"]))
        self.assertIsNone(asked([{"finding": fid("PRRT_kw7"), "proposal": {"outcome": "fixed"}}], role=author))
        for dispositions, role, code in (
                ([{"finding": fid("PRRT_kw7")}], ROLE, "disposition_halves"),
                ([{"finding": fid("PRRT_kw7"), "proposal": {"outcome": "fixed"}, "decision": {"result": "accepted"}}],
                 ROLE, "disposition_halves"),
                ([{"finding": "f_0000", "decision": {"result": "accepted"}}], ROLE, "disposition_of_no_finding"),
                ([{"finding": fid("PRRT_kw7", "coderabbit"), "decision": {"result": "accepted"}}], ROLE,
                 "disposition_of_no_finding"),
                ([{"finding": fid("PRRT_kw7"), "decision": {"result": "accepted"}}] * 2, ROLE,
                 "disposition_given_twice"),
                ([{"finding": fid("PRRT_kw7"), "proposal": {"outcome": "fixed"}}], ROLE, "disposition_not_yours"),
                ([{"finding": fid("PRRT_kw7"), "decision": {"result": "accepted"}}], author, "disposition_not_yours"),
                ([{"finding": fid("PRRT_kw7"), "proposal": {"outcome": "fixed"}}], dict(author, name="qa-lead"),
                 "disposition_not_yours"),
                ([{"finding": fid("PRRT_kw7"), "proposal": {"outcome": "fixed"}}], dict(ROLE, name="dev-lead"),
                 "disposition_not_yours"),
                ([{"finding": fid("PRRT_kw9", "don-petry"), "decision": {"result": "accepted"}}], ROLE,
                 "disposition_not_yours"),
                ([{"finding": fid("PRRT_kw7"), "decision": {"result": "accepted"}}], dict(ROLE, kind="reviewer"),
                 "disposition_not_yours")):
            self.assertEqual(asked(dispositions, role=role), ("item", code), (code, dispositions))
        # A security Finding's thread is never resolved on a proposal of declined or deferred, whoever asks.
        for outcome in ("declined", "deferred"):
            self.assertEqual(asked([{"finding": fid("PRRT_kw8"), "proposal": {"outcome": outcome}}], ["PRRT_kw8"],
                                   role=author), ("item", "security_finding_declined"))
        self.assertIsNone(asked([{"finding": fid("PRRT_kw8"), "proposal": {"outcome": "fixed"}}], ["PRRT_kw8"],
                                role=author))
        self.assertIsNone(asked([{"finding": fid("PRRT_kw7"), "proposal": {"outcome": "declined"}}], ["PRRT_kw7"],
                                role=author))
        # A Finding the Task lists whose thread is not on the item is no Finding of this item's.
        astray = the_task(permitted_effects=task["permitted_effects"], findings=["f_0000"])
        self.assertEqual(refused(task=astray, facts=facts, role=author, res=result(dispositions=[
            {"finding": "f_0000", "proposal": {"outcome": "fixed"}}])), ("item", "disposition_of_no_finding"))
        # A Finding the Task does not list is no Run's to dispose of, even with its thread on the item.
        unlisted = the_task(permitted_effects=task["permitted_effects"], findings=[fid("PRRT_kw8")])
        self.assertEqual(refused(task=unlisted, facts=facts, res=result(dispositions=[
            {"finding": fid("PRRT_kw7"), "decision": {"result": "accepted"}}])), ("item", "disposition_of_no_finding"))
        # An Effect on a thread is on one of this item's: a thread id is global.
        for effects in ({"resolve_thread": [{"id": "e5", "thread": "PRRT_elsewhere"}]},
                        {"comment": [{"id": "e5", "on": "PRRT_elsewhere", "body": "x"}]}):
            wide = the_task(permitted_effects=["submit_review", "create_check_run", "resolve_thread", "comment"])
            self.assertEqual(refused(task=wide, facts=facts, res=result(effects=dict(result()["effects"], **effects))),
                             ("item", "thread_not_on_item"))
        wide = the_task(permitted_effects=["submit_review", "create_check_run", "resolve_thread", "comment"])
        self.assertIsNone(refused(task=wide, facts=facts, res=result(effects=dict(
            result()["effects"], resolve_thread=[{"id": "e5", "thread": "PRRT_kw7"}],
            comment=[{"id": "e6", "on": "PRRT_kw7", "body": "x"}, {"id": "e7", "on": "item", "body": "y"}]))))

    def test_an_effect_is_claimed_only_from_what_was_read_back(self):  # ruling 7, L-41
        task, res = the_task(), result()
        for over, reason in (({"e1": {"key": None}}, "not_read_back"), ({"e1": {"key": ""}}, "not_read_back"),
                             ({"e1": {"surfaces": {}}}, "not_read_back"), ({"e1": {"state": None}}, "not_read_back"),
                             ({"e1": {"state": "failed", "reason": "github_refused"}}, "github_refused"),
                             ({"e1": {"state": "failed"}}, "not_read_back")):
            record = apply.applied(task, res, read_back(task, res, **over), ROLE)
            self.assertEqual(shared.errors(record, "applied"), [])
            self.assertEqual((record["effects"][0]["state"], record["effects"][0]["key"], record["effects"][0]["reason"]),
                             ("failed", None, reason), over)
            # Nothing it posted is claimed, and the Run ends as the Factory's fault.
            self.assertEqual([f["surface"]["type"] for f in record["findings"]], ["annotation"])
            self.assertEqual(apply.outcome(task, record)["outcome"], "environment")
            self.assertEqual(apply.outcome(task, record)["reason"], "effect_failed")


class Job(unittest.TestCase):
    CONFIG = {"kernel": support.CONFIG, "rubric": RUBRIC, "authority": AUTHORITY, "github_run": 4242,
              "app": APPS["apps"]["pr-review"], "needs": APPS["needs"]}

    def go(self, res, refusing=False, write=None, mint_refuses=None):
        calls = {"mint": [], "revoke": 0, "written": []}

        def read():
            facts = support.facts(state="closed") if refusing else support.facts()
            return facts, HEAD, runs(), support.context(active_runs=1)

        def mint(wanted):
            calls["mint"].append(wanted)
            if mint_refuses:
                raise identity.Refused(mint_refuses)
            def revoke():
                calls["revoke"] += 1
            return "a transport with the token", revoke

        def wrote(transport, kind, req):
            calls["written"].append((transport, kind, req))
            if write:
                return write(kind, req)
            surfaces = {c["finding"]: "PRRT_kw7" for c in req.get("comments", ())}
            return {"state": "applied", "key": "PRR_kwDOA7", "surfaces": surfaces}
        record, ended = apply.job(the_task(), res, read, wrote, mint, ROLE, self.CONFIG, NOW)
        self.assertEqual(shared.errors(record, "applied"), [])
        self.assertEqual(shared.errors(ended, "outcome"), [])
        return record, ended, calls

    def test_a_result_is_taken_by_the_digest_run_reported_and_held_to_its_schema(self):  # section 3.6
        data = json.dumps(result()).encode()
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        self.assertEqual(apply.taken(data, digest), result())
        for given, at in ((data, "sha256:" + "0" * 64), (data + b" ", digest), ("text", digest),
                          (b"\xff", "sha256:" + hashlib.sha256(b"\xff").hexdigest()),
                          (b"{}", "sha256:" + hashlib.sha256(b"{}").hexdigest())):
            self.assertIsNone(apply.taken(given, at))
        record, ended, calls = self.go(None)
        self.assertEqual((ended["outcome"], ended["reason"], calls["mint"]), ("environment", "result_unreadable", []))

    def test_what_a_result_is_held_to_is_the_decision_that_admitted_its_run(self):  # section 3.5
        record = json.loads((ROOT / "examples" / "pass.json").read_text())
        entry = record["pull_requests"][0]
        entry["decision"]["admit"] = {"role": "pr-review", "intent": "review-change", "content_id": "sha256:5d0c"}
        got = apply.admitted(record, entry["run"], ROLE, ["f_9c1e"])
        self.assertEqual(got, {"run": entry["run"], "release": record["release"], "role": "pr-review",
                               "intent": "review-change", "content_id": "sha256:5d0c",
                               "item": entry["decision"]["item"], "permitted_effects": ["submit_review",
                                                                                         "create_check_run"],
                               "findings": ["f_9c1e"]})
        for run, role, findings in (("r_01JA7Z", ROLE, []), (entry["run"], dict(ROLE, name="dev-lead"), []),
                                    (entry["run"], dict(ROLE, intents=ROLE["intents"][1:]), []),
                                    (entry["run"], dict(ROLE, kind="boss"), []), (entry["run"], ROLE, "f_9c1e")):
            with self.assertRaises(apply.task_.Refused):
                apply.admitted(record, run, role, findings)
        with self.assertRaises(apply.task_.Refused):
            apply.admitted({}, entry["run"], ROLE, [])

    def test_nothing_is_minted_for_a_refused_result_and_the_token_is_revoked_whatever_happens(self):  # ruling 6
        review_only = result(findings=result()["findings"][:1],
                             effects={"submit_review": result()["effects"]["submit_review"]})
        record, ended, calls = self.go(review_only, refusing=True)
        self.assertEqual((ended["outcome"], ended["reason"], calls["mint"]), ("superseded", "item_closed", []))
        self.assertEqual([e["state"] for e in record["effects"]], ["refused"])
        record, ended, calls = self.go(review_only)
        self.assertEqual((calls["mint"], calls["revoke"], ended["outcome"]), ([{"pull_requests": "write"}], 1, None))
        self.assertEqual([(t, k) for t, k, _ in calls["written"]], [("a transport with the token", "submit_review")])
        self.assertEqual(record["findings"][0]["surface"], {"type": "thread", "key": "PRRT_kw7"})
        # A write that raised is a failed Effect, and the token is still revoked.
        def boom(kind, req):
            raise github.Unanswered("no answer")
        record, ended, calls = self.go(review_only, write=boom)
        self.assertEqual((record["effects"][0]["state"], record["effects"][0]["reason"], calls["revoke"]),
                         ("failed", "effect_raised", 1))
        self.assertEqual((ended["outcome"], ended["reason"]), ("environment", "effect_failed"))
        # A token that cannot be minted, or an Effect the App may not write, writes nothing.
        record, ended, calls = self.go(review_only, mint_refuses="token_refused")
        self.assertEqual((ended["outcome"], ended["reason"], calls["written"]), ("environment", "token_refused", []))
        record, ended, calls = self.go(result())
        self.assertEqual((ended["outcome"], ended["reason"], calls["mint"]),
                         ("environment", "effect_not_grantable", []))
        self.assertEqual([e["state"] for e in record["effects"]], ["refused", "refused"])
        # A Result that asks for nothing writes nothing, and mints nothing.
        quiet = result(findings=[], effects={}, coverage=[dict(c, verdict="met", reason=None) if c["verdict"] == "finding"
                                                         else c for c in result()["coverage"]])
        record, ended, calls = self.go(quiet)
        self.assertEqual((record["effects"], ended["outcome"], calls["mint"]), ([], None, []))


if __name__ == "__main__":
    unittest.main()
