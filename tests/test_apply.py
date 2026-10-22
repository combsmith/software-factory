"""The `apply` job and the identity port (issue 194, PR 2), against a fake GitHub that answers as the trials recorded it.

Nothing here reaches the network. The JWT is signed by the system's `openssl` with a throwaway key made for the test and
handed to it through a pipe, as the job hands the App's key.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest

from adapters import effects, github, identity
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
            identity.signed(b"m", b"no key, in no format openssl reads\n")
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
        # A grant of no level, or an App with no grants, is no grant (Muse's read).
        for app in (dict(review, permissions=dict(review["permissions"], pull_requests={"needs": ["effect:submit_review"]})),
                    {k: v for k, v in review.items() if k != "permissions"}):
            with self.assertRaisesRegex(identity.Refused, "^effect_not_granted$"):
                identity.permissions(app, APPS["needs"], ["submit_review"])
        for level in ("admin", None):
            odd = dict(APPS["needs"], **{"effect:submit_review": {"permission": "pull_requests", "level": level}})
            with self.assertRaisesRegex(identity.Refused, "^effect_not_grantable$"):
                identity.permissions(review, odd, ["submit_review"])
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
        # No answer, or an id that is no number, is refused; a token made other than asked is revoked first.
        for answers, code in (((), "installation_unreadable"), ((installation(),), "token_refused")):
            with self.assertRaisesRegex(identity.Refused, "^%s$" % code):
                identity.mint(GitHub(*answers), review, REPO, {"pull_requests": "write"})
        odd = installation()
        odd[1]["body"]["id"] = "172571064"
        with self.assertRaisesRegex(identity.Refused, "^installation_unreadable$"):
            identity.mint(GitHub(odd), review, REPO, {"pull_requests": "write"})
        revoked = GitHub((("DELETE", "/installation/token"), {"status": 204, "headers": {}, "body": None}))
        for wide in (minted(repository_selection="all"), minted(repositories=None)):
            with self.assertRaisesRegex(identity.Refused, "^token_not_as_asked$"):
                identity.mint(GitHub(installation(), wide), review, REPO, {"pull_requests": "write"},
                              as_token=lambda value: revoked)
        self.assertEqual([r["method"] for r in revoked.sent], ["DELETE", "DELETE"])
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
        self.assertIsNone(refused(context=listed("4242")))
        self.assertEqual(refused(context=listed("4242", "4243")), ("superseded", "not_admitted"))
        self.assertEqual(refused(context=listed("4242"), github_run=4243), ("superseded", "not_admitted"))
        # The records port gives the id as digits, and the job may be given its own as a number: the same id either way.
        self.assertIsNone(refused(context=listed("4242"), github_run=4242))
        self.assertEqual(refused(context=listed("4242"), github_run=None), ("superseded", "not_admitted"))
        # A count of active Runs that cannot be this Run's is left as read, and the Kernel defers on it (Argon's read).
        for count in (True, -1, None):
            self.assertEqual(refused(context=support.context(active_runs=count)), ("superseded", "not_admitted"), count)
        self.assertIsNone(refused(context=support.context(active_runs=0)))
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
            ({"effects": {"submit_review": [review], "create_check_run": [dict(check, annotations=check["annotations"] + [
                {"finding": "n1", "body": "again"}])]}}, "finding_not_posted_once"),
            ({"findings": [n1, dict(n2, severity="major")]}, "finding_gates"),
            ({"findings": [dict(n1, severity="minor"), n2]}, "finding_does_not_gate"),
            ({"findings": [{k: v for k, v in n1.items() if k != "location"}, n2]}, "finding_has_no_place"),
            ({"findings": [n1, {k: v for k, v in n2.items() if k != "location"}]}, "finding_has_no_place"),
            ({"findings": [dict(n1, location={"path": "kernel/decide.py"}), n2]}, "finding_has_no_place"),
            ({"effects": {"submit_review": [review, dict(review, id="e3", comments=[])], "create_check_run": [check]}},
             "review_twice"))
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
        # A resolved thread is an accepted Disposition: only the owner of its category resolves it, and only on its
        # own decision, in this Result, to accept it (section 3.8).
        for dispositions, resolve, role, code in (
                ([{"finding": fid("PRRT_kw8"), "proposal": {"outcome": "fixed"}}], ["PRRT_kw8"], author,
                 "resolve_not_yours"),
                ([], ["PRRT_kw8"], author, "resolve_not_yours"),
                ([{"finding": fid("PRRT_kw7"), "proposal": {"outcome": "declined"}}], ["PRRT_kw7"], author,
                 "resolve_not_yours"),
                ([], ["PRRT_kw7"], ROLE, "resolve_not_accepted"),
                ([{"finding": fid("PRRT_kw7"), "decision": {"result": "rejected"}}], ["PRRT_kw7"], ROLE,
                 "resolve_not_accepted"),
                ([{"finding": fid("PRRT_kw8"), "decision": {"result": "accepted"}}], ["PRRT_kw7"], ROLE,
                 "resolve_not_accepted"),
                ([], ["PRRT_kw9"], ROLE, "resolve_not_yours"),
                ([{"finding": fid("PRRT_kw7"), "decision": {"result": "accepted"}}], ["PRRT_kw7"],
                 dict(ROLE, kind="reviewer"), "disposition_not_yours")):
            self.assertEqual(asked(dispositions, resolve, role=role), ("item", code), (code, resolve))
        # The owner accepts a security Finding only on the author's proposal of fixed or not applicable, which is in a
        # Run apply cannot read yet: a security thread is resolved by no Role (Muse's read).
        self.assertEqual(asked([{"finding": fid("PRRT_kw8"), "decision": {"result": "accepted"}}], ["PRRT_kw8"]),
                         ("item", "security_proposal_unread"))
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
        wide = the_task(permitted_effects=["submit_review", "create_check_run", "resolve_thread", "comment"],
                        findings=[fid("PRRT_kw7")])
        self.assertIsNone(refused(task=wide, facts=facts, res=result(dispositions=[
            {"finding": fid("PRRT_kw7"), "decision": {"result": "accepted"}}], effects=dict(
            result()["effects"], resolve_thread=[{"id": "e5", "thread": "PRRT_kw7"}],
            comment=[{"id": "e6", "on": "PRRT_kw7", "body": "x"}, {"id": "e7", "on": "item", "body": "y"}]))))

    def test_an_effect_is_claimed_only_from_what_was_read_back(self):  # ruling 7, L-41
        task, res = the_task(), result()
        record = apply.applied(task, res, read_back(task, res, e2={"surfaces": {"n2": "CR_other:n2"}}), ROLE)
        self.assertEqual((record["effects"][1]["state"], record["effects"][1]["reason"]), ("failed", "not_read_back"))
        self.assertEqual([f["surface"]["type"] for f in record["findings"]], ["thread"])
        for over, reason in (({"e1": {"key": None}}, "not_read_back"), ({"e1": {"key": ""}}, "not_read_back"),
                             ({"e1": {"surfaces": {"n1": ""}}}, "not_read_back"),
                             ({"e1": {"surfaces": {"n1": "a note"}}}, "not_read_back"),
                             ({"e1": {"surfaces": {}}}, "not_read_back"), ({"e1": {"state": None}}, "not_read_back"),
                             ({"e1": {"state": "failed", "reason": "github_refused"}}, "github_refused"),
                             ({"e1": {"state": "failed"}}, "not_read_back")):
            record = apply.applied(task, res, read_back(task, res, **over), ROLE)
            self.assertEqual(shared.errors(record, "applied"), [])
            self.assertEqual((record["effects"][0]["state"], record["effects"][0]["key"], record["effects"][0]["reason"]),
                             ("failed", None, reason), over)
            # Nothing it posted is claimed, and the Run ends as the Factory's fault.
            self.assertNotIn("thread", [f["surface"]["type"] for f in record["findings"]])
            self.assertEqual([f["surface"]["type"] for f in record["findings"]], ["annotation"])
            self.assertEqual(apply.outcome(task, record)["outcome"], "environment")
            self.assertEqual(apply.outcome(task, record)["reason"], "effect_failed")


LOGIN = "combsmith-sf-pr-review[bot]"
ITEM = dict(support.ITEM)
PULL = "/repos/%s/pulls/%d" % (ITEM["repo"], ITEM["number"])
ISSUE = "/repos/%s/issues/%d" % (ITEM["repo"], ITEM["number"])


def p43_review(**over) -> dict:
    """The review GitHub answered in trials/P-43.json, as this App's on HEAD."""
    body = copy.deepcopy(json.loads((ROOT / "trials" / "P-43.json").read_text())["exchanges"][4]["response"]["body"])
    body.update(commit_id=HEAD, user=dict(body["user"], login=LOGIN))
    body.update(over)
    return body


def ok(body, status=200) -> dict:
    return {"status": status, "headers": {}, "body": body}


def threads_of(review_id, *threads, total=None) -> dict:
    nodes = [{"id": th, "comments": {"nodes": [{"databaseId": n, "pullRequestReview": {"databaseId": rid}}]}}
             for n, (th, rid) in enumerate(threads, 1)]
    return ok({"data": {"repository": {"pullRequest": {"reviewThreads": {
        "totalCount": len(nodes) if total is None else total, "nodes": nodes}}}}})


def thread_node(resolved, number=None, repo=None) -> dict:
    return ok({"data": {"node": {"id": "PRRT_kw7", "isResolved": resolved, "pullRequest": {
        "number": ITEM["number"] if number is None else number,
        "repository": {"nameWithOwner": repo or ITEM["repo"]}}}}})


def review_request() -> dict:
    task, res = the_task(), result()
    return apply.requests(task, res, HEAD, ROLE)[0][2]


class RoleWrites(unittest.TestCase):
    def test_a_review_is_sent_once_as_a_comment_and_read_back_with_its_threads(self):  # sections 3.6, 3.7
        rid = p43_review()["id"]
        hub = GitHub((("GET", PULL + "/reviews?per_page=100"), ok([])), (("POST", PULL + "/reviews"), ok(p43_review())),
                     (("GET", PULL + "/reviews/%d" % rid), ok(p43_review())),
                     (("POST", "/graphql"), threads_of(rid, ("PRRT_kw0", 1), ("PRRT_kw7", rid))))
        back = effects.role_write(hub, ITEM, "submit_review", review_request(), LOGIN)
        self.assertEqual(back, {"state": "applied", "key": p43_review()["node_id"], "surfaces": {"n1": "PRRT_kw7"},
                                "reason": None})
        self.assertEqual(hub.sent[1]["body"], {"commit_id": HEAD, "event": "COMMENT", "body": "", "comments": [
            {"path": "kernel/decide.py", "line": 94, "start_line": 88, "start_side": "RIGHT", "side": "RIGHT",
             "body": result()["effects"]["submit_review"][0]["comments"][0]["body"]}]})
        # One already made by this App on this commit is recovered, never made twice; another's is not this App's.
        other = p43_review(user={"login": "coderabbitai[bot]"})
        hub = GitHub((("GET", PULL + "/reviews?per_page=100"), ok([other, p43_review()])),
                     (("GET", PULL + "/reviews/%d" % rid), ok(p43_review())),
                     (("POST", "/graphql"), threads_of(rid, ("PRRT_kw7", rid))))
        self.assertEqual(effects.role_write(hub, ITEM, "submit_review", review_request(), LOGIN)["state"],
                         "already_applied")
        self.assertNotIn("POST %s/reviews" % PULL, ["%s %s" % (r["method"], r["path"]) for r in hub.sent])
        # This App's review on an earlier commit is not one on this commit: a new one is made.
        hub = GitHub((("GET", PULL + "/reviews?per_page=100"), ok([p43_review(commit_id="0" * 40)])),
                     (("POST", PULL + "/reviews"), ok(p43_review())), (("GET", PULL + "/reviews/%d" % rid), ok(p43_review())),
                     (("POST", "/graphql"), threads_of(rid, ("PRRT_kw7", rid))))
        self.assertEqual(effects.role_write(hub, ITEM, "submit_review", review_request(), LOGIN)["state"], "applied")
        # Each comment's thread is the one its comment opened, by the comments' order, however the threads are listed.
        two = dict(review_request(), comments=[dict(review_request()["comments"][0], finding=ref) for ref in ("n1", "n2")])
        listed = threads_of(rid, ("PRRT_kwB", rid), ("PRRT_kwA", rid))
        listed["body"]["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"].reverse()
        hub = GitHub((("GET", PULL + "/reviews?per_page=100"), ok([p43_review()])),
                     (("GET", PULL + "/reviews/%d" % rid), ok(p43_review())), (("POST", "/graphql"), listed))
        self.assertEqual(effects.role_write(hub, ITEM, "submit_review", two, LOGIN)["surfaces"],
                         {"n1": "PRRT_kwB", "n2": "PRRT_kwA"})
        hub = GitHub((("GET", PULL + "/reviews?per_page=100"), ok([p43_review(), p43_review(id=1)])))
        self.assertEqual(effects.role_write(hub, ITEM, "submit_review", review_request(), LOGIN)["reason"],
                         "reviewed_twice")
        for listed in (ok({}), ok([p43_review(id=n, commit_id="0" * 40) for n in range(100)]), ok([], 500)):
            hub = GitHub((("GET", PULL + "/reviews?per_page=100"), listed))
            self.assertEqual(effects.role_write(hub, ITEM, "submit_review", review_request(), LOGIN)["reason"],
                             "reviews_unreadable")

    def test_a_write_github_did_not_take_is_never_claimed_or_sent_again(self):  # section 3.6, L-41
        rid = p43_review()["id"]
        for answer, want in ((ok(None, 401), ("refused", "token_refused")), (ok(None, 403), ("refused", "token_refused")),
                             (ok({"message": "x"}, 422), ("failed", "write_refused")),
                             (ok(None, 502), ("failed", "write_unanswered")), (None, ("failed", "write_unanswered"))):
            hub = GitHub((("GET", PULL + "/reviews?per_page=100"), ok([])), (("POST", PULL + "/reviews"), answer))
            if answer is None:
                hub.answers.pop()
            back = effects.role_write(hub, ITEM, "submit_review", review_request(), LOGIN)
            self.assertEqual((back["state"], back["reason"], back["key"]), want + (None,))
            self.assertEqual(len(hub.sent), 2)
        # A credential GitHub refuses on a recovery read or a read-back is refused as on a write (Codex's read).
        for answers in ((ok(None, 401),), (ok([]), ok(p43_review()), ok(None, 403))):
            calls = [("GET", PULL + "/reviews?per_page=100"), ("POST", PULL + "/reviews"),
                     ("GET", PULL + "/reviews/%d" % rid)]
            hub = GitHub(*zip(calls, answers))
            self.assertEqual(effects.role_write(hub, ITEM, "submit_review", review_request(), LOGIN),
                             {"state": "refused", "key": None, "surfaces": {}, "reason": "token_refused"})
        # GitHub took it, but what was read back is not it: sent, and nothing claimed.
        for review, threads in ((p43_review(commit_id="0" * 40), threads_of(rid, ("PRRT_kw7", rid))),
                                (p43_review(state="APPROVED"), threads_of(rid, ("PRRT_kw7", rid))),
                                (p43_review(user={"login": "someone"}), threads_of(rid, ("PRRT_kw7", rid))),
                                (p43_review(), threads_of(rid)), (p43_review(), threads_of(rid, ("PRRT_kw7", rid), total=101)),
                                (p43_review(), threads_of(rid, ("not a thread", rid))), (p43_review(), ok({"errors": [1]})),
                                (p43_review(), ok(dict(threads_of(rid, ("PRRT_kw7", rid))["body"], errors=[1]))),
                                (p43_review(id=1), threads_of(rid, ("PRRT_kw7", rid))),
                                (p43_review(), threads_of(rid, ("PRRT_kw7", rid), total=2)),
                                (p43_review(), threads_of(rid, ("PRRT_kw7", rid),
                                                          *[("PRRT_x%d" % n, 1) for n in range(100)])),
                                (p43_review(), ok({"data": {"repository": {"pullRequest": {"reviewThreads": {
                                    "totalCount": 1, "nodes": [{"id": "PRRT_kw7", "comments": {"nodes": [
                                        {"databaseId": None, "pullRequestReview": {"databaseId": rid}}]}}]}}}}}))):
            hub = GitHub((("GET", PULL + "/reviews?per_page=100"), ok([])), (("POST", PULL + "/reviews"), ok(p43_review())),
                         (("GET", PULL + "/reviews/%d" % rid), ok(review)), (("POST", "/graphql"), threads))
            self.assertEqual(effects.role_write(hub, ITEM, "submit_review", review_request(), LOGIN),
                             {"state": "sent", "key": None, "surfaces": {}, "reason": None})

    def test_a_thread_is_resolved_once_on_its_own_item_and_read_back_resolved(self):  # section 3.6
        req = {"thread": "PRRT_kw7"}
        resolved = ok({"data": {"resolveReviewThread": {"thread": {"id": "PRRT_kw7", "isResolved": True}}}})
        cases = (((thread_node(False), resolved, thread_node(True)), ("applied", "PRRT_kw7", None)),
                 ((thread_node(True),), ("already_applied", "PRRT_kw7", None)),
                 ((thread_node(False, number=43),), ("refused", None, "thread_not_on_item")),
                 ((thread_node(False, repo="combsmith/other"),), ("refused", None, "thread_not_on_item")),
                 ((ok({"data": {"node": None}}),), ("failed", None, "thread_unreadable")),
                 ((thread_node(False), ok({"errors": [{"type": "FORBIDDEN"}]})), ("failed", None, "write_refused")),
                 ((thread_node(False), ok(None, 401)), ("refused", None, "token_refused")),
                 ((thread_node(False), resolved, thread_node(False)), ("sent", None, None)))
        for answers, want in cases:
            hub = GitHub(*[(("POST", "/graphql"), a) for a in answers])
            back = effects.role_write(hub, ITEM, "resolve_thread", req, LOGIN)
            self.assertEqual((back["state"], back["key"], back["reason"]), want, answers)
            self.assertEqual(len(hub.sent), len(answers))
        self.assertEqual(hub.sent[1]["body"], {"query": effects.RESOLVE, "variables": {"id": "PRRT_kw7"}})

    def test_a_comment_is_recovered_by_this_apps_comments_since_the_run_began_never_by_its_text(self):  # 3.6
        since = "2026-10-11T12:58:00Z"
        listed = ("GET", ISSUE + "/comments?since=%s&per_page=100" % since)
        mine = lambda cid, at=since: {"id": cid, "node_id": "IC_%d" % cid, "user": {"login": LOGIN}, "body": "anything",
                                      "created_at": at}
        req = lambda index: {"on": "item", "body": "Said once.", "since": since, "index": index}
        hub = GitHub((listed, ok([mine(7), {"id": 8, "user": {"login": "don-petry"}, "created_at": since}])),
                     (("POST", ISSUE + "/comments"), ok(mine(9), 201)),
                     (("GET", "/repos/%s/issues/comments/9" % ITEM["repo"]), ok(mine(9))))
        self.assertEqual(effects.role_write(hub, ITEM, "comment", req(1), LOGIN)["state"], "applied")
        self.assertEqual(hub.sent[1]["body"], {"body": "Said once."})
        # One this App made before the Run and edited since is listed, and is not this Run's (Codex's read).
        hub = GitHub((listed, ok([mine(3, "2026-10-11T11:00:00Z")])), (("POST", ISSUE + "/comments"), ok(mine(9), 201)),
                     (("GET", "/repos/%s/issues/comments/9" % ITEM["repo"]), ok(mine(9))))
        self.assertEqual(effects.role_write(hub, ITEM, "comment", req(0), LOGIN)["state"], "applied")
        hub = GitHub((listed, ok([mine(9), mine(7)])), (("GET", "/repos/%s/issues/comments/7" % ITEM["repo"]), ok(mine(7))))
        self.assertEqual(effects.role_write(hub, ITEM, "comment", req(0), LOGIN),
                         {"state": "already_applied", "key": "IC_7", "surfaces": {}, "reason": None})
        hub = GitHub((listed, ok([])), (("POST", ISSUE + "/comments"), ok(mine(9), 201)),
                     (("GET", "/repos/%s/issues/comments/9" % ITEM["repo"]), ok(mine(10))))
        self.assertEqual(effects.role_write(hub, ITEM, "comment", req(0), LOGIN)["state"], "sent")
        for answers, want in (((ok({}),), ("failed", "comments_unreadable")),
                              ((ok([mine(n) for n in range(1, 101)]),), ("failed", "comments_unreadable")),
                              ((ok([]), ok(None, 403)), ("refused", "token_refused")),
                              ((ok([]), ok(mine(9), 200)), ("failed", "write_refused"))):
            calls = [listed, ("POST", ISSUE + "/comments")]
            hub = GitHub(*zip(calls, answers))
            back = effects.role_write(hub, ITEM, "comment", req(0), LOGIN)
            self.assertEqual((back["state"], back["reason"]), want)
        hub = GitHub((listed, ok([])), (("POST", ISSUE + "/comments"), ok(mine(9), 201)),
                     (("GET", "/repos/%s/issues/comments/9" % ITEM["repo"]), ok(dict(mine(9), user={"login": "x"}))))
        self.assertEqual(effects.role_write(hub, ITEM, "comment", req(0), LOGIN)["state"], "sent")
        # A reply on a thread is not built yet: it fails, and claims nothing.
        self.assertEqual(effects.role_write(GitHub(), ITEM, "comment", dict(req(0), on="PRRT_kw7"), LOGIN)["reason"],
                         "not_built")

    def test_a_check_run_is_made_once_complete_and_read_back_with_its_annotations(self):  # sections 3.6, 4.3
        req = apply.requests(the_task(), result(), HEAD, ROLE)[1][2]
        listed = ("GET", "/repos/%s/commits/%s/check-runs?check_name=factory%%20%%2F%%20pr-review&per_page=100"
                  % (ITEM["repo"], HEAD))
        made = lambda **over: dict({"id": 77, "node_id": "CR_kwDOA7", "external_id": "%s:e2" % RUN, "head_sha": HEAD,
                                    "name": "factory / pr-review", "status": "completed", "conclusion": "success",
                                    "app": {"slug": "combsmith-sf-pr-review"}, "output": {"annotations_count": 1}},
                                   **over)
        got = ("GET", "/repos/%s/check-runs/77" % ITEM["repo"])
        hub = GitHub((listed, ok({"total_count": 0, "check_runs": []})),
                     (("POST", "/repos/%s/check-runs" % ITEM["repo"]), ok(made(), 201)), (got, ok(made())))
        self.assertEqual(effects.role_write(hub, ITEM, "create_check_run", req, LOGIN),
                         {"state": "applied", "key": "CR_kwDOA7", "surfaces": {"n2": "CR_kwDOA7:n2"}, "reason": None})
        sent = hub.sent[1]["body"]
        self.assertEqual((sent["name"], sent["head_sha"], sent["external_id"], sent["status"], sent["conclusion"]),
                         ("factory / pr-review", HEAD, "%s:e2" % RUN, "completed", "success"))
        self.assertEqual(sent["output"]["annotations"], [{"path": "tests/test_decide.py", "start_line": 410,
                                                          "end_line": 410, "annotation_level": "warning",
                                                          "message": result()["effects"]["create_check_run"][0]["annotations"][0]["body"]}])
        # This App's check run for another Run's Effect on the commit is not this one's: a new one is made.
        hub = GitHub((listed, ok({"total_count": 1, "check_runs": [made(external_id="r_01JA7Z:e2")]})),
                     (("POST", "/repos/%s/check-runs" % ITEM["repo"]), ok(made(), 201)), (got, ok(made())))
        self.assertEqual(effects.role_write(hub, ITEM, "create_check_run", req, LOGIN)["state"], "applied")
        # One this App made for this Effect on this commit is recovered, never made twice; another App's is not it.
        other = made(app={"slug": "coderabbitai"})
        hub = GitHub((listed, ok({"total_count": 2, "check_runs": [other, made()]})), (got, ok(made())))
        self.assertEqual(effects.role_write(hub, ITEM, "create_check_run", req, LOGIN)["state"], "already_applied")
        full = {"total_count": 100, "check_runs": [made(id=n, external_id="r_01JA7Z:e%d" % n) for n in range(100)]}
        for answers, want in (((ok({"total_count": 2, "check_runs": [made()]}),), ("failed", "checks_unreadable")),
                              ((ok(full),), ("failed", "checks_unreadable")),
                              ((ok({"total_count": 2, "check_runs": [made(), made(id=78)]}),), ("failed", "checked_twice")),
                              ((ok({"total_count": 0, "check_runs": []}), ok(None, 403)), ("refused", "token_refused")),
                              ((ok({"total_count": 0, "check_runs": []}), ok(made(), 200)), ("failed", "write_refused"))):
            hub = GitHub(*zip([listed, ("POST", "/repos/%s/check-runs" % ITEM["repo"])], answers))
            back = effects.role_write(hub, ITEM, "create_check_run", req, LOGIN)
            self.assertEqual((back["state"], back["reason"]), want, want)
        # What was read back is not what was asked: sent, and nothing claimed.
        for wrong in (made(external_id="r_01JA7Z:e2"), made(head_sha="0" * 40), made(app={"slug": "other"}),
                      made(output={"annotations_count": 0}), made(node_id=""), made(id=78), made(name="gates"),
                      made(status="in_progress"), made(conclusion="failure")):
            hub = GitHub((listed, ok({"total_count": 0, "check_runs": []})),
                         (("POST", "/repos/%s/check-runs" % ITEM["repo"]), ok(made(), 201)), (got, ok(wrong)))
            self.assertEqual(effects.role_write(hub, ITEM, "create_check_run", req, LOGIN)["state"], "sent", wrong)
        many = dict(req, annotations=req["annotations"] * (effects.ANNOTATIONS + 1))
        self.assertEqual(effects.role_write(GitHub(), ITEM, "create_check_run", many, LOGIN)["reason"],
                         "too_many_annotations")
        info = dict(req, annotations=[dict(req["annotations"][0], severity="info")])
        hub = GitHub((listed, ok({"total_count": 0, "check_runs": []})),
                     (("POST", "/repos/%s/check-runs" % ITEM["repo"]), ok(made(), 201)), (got, ok(made())))
        effects.role_write(hub, ITEM, "create_check_run", info, LOGIN)
        self.assertEqual(hub.sent[1]["body"]["output"]["annotations"][0]["annotation_level"], "notice")

    @support.pending
    def test_the_role_app_is_granted_what_apply_reads_again(self):  # the Maintainer, 2026-10-22
        # Waits on combsmith-sf-pr-review's registration of checks, actions and issues, and trial P-39 run again:
        # apply reads the item and the run records again with the Role App's own token, read-only.
        self.assertEqual(identity.granted(APPS["apps"]["pr-review"], APPS["needs"], apply.READS, "read"),
                         {"actions": "read", "checks": "read", "contents": "read", "issues": "read",
                          "metadata": "read", "pull_requests": "read"})

    def test_what_apply_reads_again_is_read_only_and_within_the_apps_grant(self):  # the Maintainer, 2026-10-22
        # As the App will be granted it: each read need served by its permission, and a read token is never a writer's.
        needs = dict(APPS["needs"], **{"read:facts.acceptance": {"permission": "issues", "level": "read"}})
        grants = {}
        for name in apply.READS:
            need = needs[name]
            level = "write" if need["permission"] in ("pull_requests", "checks") else "read"
            grants.setdefault(need["permission"], {"level": level, "needs": []})["needs"].append(name)
        app = dict(APPS["apps"]["pr-review"], permissions=grants)
        self.assertEqual(set(identity.granted(app, needs, apply.READS, "read").values()), {"read"})
        self.assertNotIn("read:facts.queue", apply.READS)       # its need waits, and the Kernel reads it as unknown
        for missing in ("read:records.runs", "read:facts.checks"):
            short = dict(app, permissions={p: dict(g, needs=[n for n in g["needs"] if n != missing])
                                           for p, g in grants.items()})
            with self.assertRaisesRegex(identity.Refused, "^read_not_granted$"):
                identity.granted(short, needs, apply.READS, "read")
        with self.assertRaisesRegex(identity.Refused, "^read_not_grantable$"):
            identity.granted(app, APPS["needs"], apply.READS, "read")

    @support.pending
    def test_the_role_app_is_granted_checks_to_write_its_check_run(self):  # the Maintainer, 2026-10-22
        # Waits on the registration of checks: write for combsmith-sf-pr-review and trial P-39 run again.
        self.assertEqual(identity.permissions(APPS["apps"]["pr-review"], APPS["needs"], ["create_check_run"]),
                         {"checks": "write"})

    def test_a_role_token_sends_only_its_writes_on_its_one_item(self):  # ruling 6, I-35
        permits, patterns = effects.role_permits(ITEM, HEAD, "factory / pr-review", ["PRRT_kw7"])
        hub = GitHub()
        allowed = effects.Allowed(hub, permits, patterns)
        owner, name = ITEM["repo"].split("/")
        fine = [github.request("GET", PULL + "/reviews?per_page=100"),
                github.request("POST", PULL + "/reviews", body={"commit_id": HEAD, "event": "COMMENT", "body": "",
                                                                "comments": []}),
                github.request("GET", PULL + "/reviews/5602757809"),
                github.request("POST", ISSUE + "/comments", body={"body": "x"}),
                github.request("GET", "/repos/%s/issues/comments/9" % ITEM["repo"]),
                github.request("GET", ISSUE + "/comments?since=2026-10-11T12:58:00Z&per_page=100"),
                github.request("POST", "/graphql", body={"query": effects.THREADS, "variables": {
                    "owner": owner, "name": name, "number": ITEM["number"]}}),
                github.request("POST", "/graphql", body={"query": effects.RESOLVE, "variables": {"id": "PRRT_kw7"}}),
                github.request("POST", "/graphql", body={"query": effects.THREAD, "variables": {"id": "PRRT_kw7"}}),
                github.request("POST", "/repos/%s/check-runs" % ITEM["repo"], body={
                    "name": "factory / pr-review", "head_sha": HEAD, "external_id": "%s:e2" % RUN, "status": "completed",
                    "conclusion": "success", "output": {}}),
                github.request("GET", "/repos/%s/check-runs/77" % ITEM["repo"]),
                github.request("GET", "/repos/%s/commits/%s/check-runs?check_name=factory%%20%%2F%%20pr-review&per_page=100"
                               % (ITEM["repo"], HEAD))]
        for req in fine:
            with self.assertRaisesRegex(github.Unanswered, "nothing left"):      # it reached the fake
                allowed.send(req)
        other = "/repos/%s/pulls/%d" % (ITEM["repo"], ITEM["number"] + 1)
        refused = [github.request("POST", PULL + "/reviews", body={"commit_id": HEAD, "event": "APPROVE", "body": "",
                                                                   "comments": []}),
                   github.request("POST", other + "/reviews", body={"commit_id": HEAD, "event": "COMMENT", "body": "",
                                                                    "comments": []}),
                   github.request("PUT", PULL + "/merge", body={}),
                   github.request("POST", "/repos/%s/check-runs" % ITEM["repo"], body={
                       "name": "factory / pr-review", "head_sha": HEAD, "external_id": "%s:e2" % RUN, "status": "in_progress",
                       "conclusion": "success", "output": {}}),
                   github.request("POST", "/repos/%s/check-runs" % ITEM["repo"], body={
                       "name": "factory / pr-review", "head_sha": "main", "external_id": "%s:e2" % RUN, "status": "completed",
                       "conclusion": "success", "output": {}}),
                   github.request("GET", "/repos/combsmith/other/check-runs/77"),
                   github.request("POST", PULL + "/reviews", body={"commit_id": "0" * 40, "event": "COMMENT", "body": "",
                                                                   "comments": []}),
                   github.request("POST", "/repos/%s/check-runs" % ITEM["repo"], body={
                       "name": "factory / pr-review", "head_sha": HEAD, "external_id": "%s:e2" % RUN,
                       "status": "completed", "conclusion": "failure", "output": {}}),
                   github.request("POST", "/repos/%s/check-runs" % ITEM["repo"], body={
                       "name": "factory / pr-review", "head_sha": HEAD, "external_id": "anything",
                       "status": "completed", "conclusion": "success", "output": {}}),
                   github.request("POST", "/graphql", body={"query": effects.RESOLVE,
                                                            "variables": {"id": "PRRT_onAnotherPR"}}),
                   github.request("POST", "/repos/%s/check-runs" % ITEM["repo"], body={
                       "name": "gates", "head_sha": HEAD, "external_id": "%s:e2" % RUN, "status": "completed",
                       "conclusion": "success", "output": {}}),
                   github.request("POST", "/repos/%s/check-runs" % ITEM["repo"], body={
                       "name": "factory / pr-review", "head_sha": "1" * 40, "external_id": "%s:e2" % RUN, "status": "completed",
                       "conclusion": "success", "output": {}}),
                   github.request("GET", PULL + "/reviews/5602757809/../../merge"),
                   github.request("GET", ISSUE + "/comments?since=yesterday&per_page=100"),
                   github.request("POST", ISSUE + "/comments", body={"body": "x", "extra": 1}),
                   github.request("POST", "/graphql", body={"query": effects.THREADS, "variables": {
                       "owner": owner, "name": name, "number": ITEM["number"] + 1}}),
                   github.request("POST", "/graphql", body={"query": effects.RESOLVE, "variables": {"id": "PR_kw7"}}),
                   github.request("POST", "/graphql", body={"query": "mutation { mergePullRequest }", "variables": {}}),
                   github.request("POST", "/graphql", body={"query": "mutation M($id: ID!) { deleteNode(id: $id) }",
                                                            "variables": {"id": "PRRT_kw7"}})]
        for req in refused:
            with self.assertRaisesRegex(github.Unanswered, "may not send"):
                allowed.send(req)
        # Each key of a check run is held on its own: the body the port sends, and that body with one key changed.
        good = {"name": "factory / pr-review", "head_sha": HEAD, "external_id": "%s:e2" % RUN, "status": "completed",
                "conclusion": "success", "output": {}}
        with self.assertRaisesRegex(github.Unanswered, "nothing left"):
            allowed.send(github.request("POST", "/repos/%s/check-runs" % ITEM["repo"], body=good))
        for key, value in (("name", "gates"), ("head_sha", "1" * 40), ("head_sha", "main"), ("status", "in_progress"),
                           ("conclusion", "failure"), ("external_id", "anything")):
            with self.assertRaisesRegex(github.Unanswered, "may not send", msg=key):
                allowed.send(github.request("POST", "/repos/%s/check-runs" % ITEM["repo"], body=dict(good, **{key: value})))
        self.assertEqual(len(hub.sent), len(fine) + 1)      # and the good check run


class Job(unittest.TestCase):
    CONFIG = {"kernel": support.CONFIG, "rubric": RUBRIC, "authority": AUTHORITY, "github_run": 4242,
              "app": APPS["apps"]["pr-review"], "needs": APPS["needs"]}

    def go(self, res, refusing=False, write=None, mint_refuses=None, task=None, records=None, context=None,
           revoked=True):
        calls = {"mint": [], "revoke": 0, "written": []}

        def read():
            facts = support.facts(state="closed") if refusing else support.facts()
            return (facts, HEAD, runs() if records is None else records,
                    support.context(active_runs=1) if context is None else context)

        def mint(wanted):
            calls["mint"].append(wanted)
            if mint_refuses:
                raise identity.Refused(mint_refuses)
            def revoke():
                calls["revoke"] += 1
                return revoked
            return "a transport with the token", revoke

        def wrote(transport, kind, req):
            calls["written"].append((transport, kind, req))
            if write:
                return write(kind, req)
            surfaces = {c["finding"]: "PRRT_kw7" for c in req.get("comments", ())}
            return {"state": "applied", "key": "PRR_kwDOA7", "surfaces": surfaces}
        record, ended = apply.job(task or the_task(), res, read, wrote, mint, ROLE, self.CONFIG, NOW)
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
        # A credential GitHub would not take ends every later write on it, which is never sent.
        twice = result(findings=result()["findings"][:1], effects={
            "submit_review": result()["effects"]["submit_review"], "comment": [{"id": "e3", "on": "item", "body": "x"}]})
        record, ended, calls = self.go(twice, write=lambda kind, req: {"state": "refused", "reason": "token_refused"},
                                       task=the_task(permitted_effects=["submit_review", "comment"]))
        self.assertEqual([(e["state"], e["reason"]) for e in record["effects"]],
                         [("refused", "token_refused"), ("refused", "token_refused")])
        self.assertEqual((len(calls["written"]), ended["outcome"], ended["reason"]), (1, "environment", "effect_failed"))
        # A token GitHub did not confirm revoked may still write: the Run ends the Factory's to look at (Codex's read).
        record, ended, calls = self.go(review_only, revoked=False)
        self.assertEqual((record["effects"][0]["state"], ended["outcome"], ended["reason"]),
                         ("applied", "environment", "token_not_revoked"))
        # A comment carries when the Run began, from its record or, listed before its name, its run's creation; its
        # place is among the Run's comments on the item; none is sent after one on the item that was not written.
        talk = the_task(permitted_effects=["comment"])
        said = result(findings=[], coverage=[dict(c, verdict="met", reason=None) if c["verdict"] == "finding" else c
                                             for c in result()["coverage"]],
                      effects={"comment": [{"id": "e1", "on": "PRRT_kw7", "body": "a"}, {"id": "e2", "on": "item", "body": "b"},
                                           {"id": "e3", "on": "item", "body": "c"}]})
        facts_threads = support.facts(threads=[support.thread("PRRT_kw7")])
        cases = ((runs(), support.context(active_runs=1), "2026-10-11T12:58:00Z"),
                 ([], support.context(active_runs=0, unidentified_runs=[
                     {"run": "4242", "created_at": "2026-10-11T12:57:00Z", "status": "in_progress"}]), "2026-10-11T12:57:00Z"))
        for records, context, since in cases:
            got = []
            def note(kind, req):
                got.append(req)
                return {"state": "applied", "key": "IC_%d" % len(got), "surfaces": {}}
            orig = support.facts
            support.facts = lambda **over: orig(**dict({"threads": facts_threads["threads"]}, **over))
            try:
                record, ended, calls = self.go(said, write=note, task=talk, records=records, context=context)
            finally:
                support.facts = orig
            self.assertEqual([(r["on"], r["index"], r["since"]) for r in got],
                             [("PRRT_kw7", 0, since), ("item", 0, since), ("item", 1, since)], since)
        # A comment on the item whose Run's start was not read mints nothing and writes nothing (Codex's read).
        support.facts = lambda **over: orig(**dict({"threads": facts_threads["threads"]}, **over))
        try:
            record, ended, calls = self.go(said, task=talk, records=[], context=support.context(active_runs=0))
        finally:
            support.facts = orig
        self.assertEqual((ended["outcome"], ended["reason"], calls["mint"]), ("environment", "run_start_unread", []))
        self.assertEqual({e["state"] for e in record["effects"]}, {"refused"})
        def first_fails(kind, req):
            return {"state": "failed", "reason": "write_refused"} if req["on"] == "item" else \
                {"state": "failed", "reason": "not_built"}
        support.facts = lambda **over: orig(**dict({"threads": facts_threads["threads"]}, **over))
        try:
            record, ended, calls = self.go(said, write=first_fails, task=talk)
        finally:
            support.facts = orig
        self.assertEqual([(e["id"], e["reason"]) for e in record["effects"]],
                         [("e1", "not_built"), ("e2", "write_refused"), ("e3", "earlier_comment_unwritten")])
        self.assertEqual(len(calls["written"]), 2)
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
