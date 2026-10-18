"""The boundary cases of the design, one test each. Add the case here before the code."""
from __future__ import annotations

import datetime
import json
import random
import re
import unittest

from kernel import derive
from kernel.decide import decide
from tests.support import (COMMIT, CONFIG, DIGEST, GREEN, LENS_OF, MAINTAINER, NOW, OTHER_APP, OTHER_WORKFLOW, REPORTER, ROOT,
                           changed, config, context, contract, evidence, facts, labelled, review, run, thread,
                           unlabelled)
from tools.jsonschema_lite import validate

DECISION_SCHEMA = json.loads((ROOT / "schemas" / "decision.schema.json").read_text())
REVIEWED = [run()]
# A dependency bot's pull request, whose head that bot pushed itself.
DEPENDENCY = {"class": "dependency", "author": "dependabot[bot]", "last_pusher": "dependabot[bot]"}
APPROVED = [review()]
LIMITS = CONFIG["limits"]
# An agent's pull request, which the Maintainer reviews as they would a colleague's (UJ-4).
AGENT = {"class": "agent", "author": "combsmith-sf-dev-lead[bot]", "last_pusher": "combsmith-sf-dev-lead[bot]"}
COLLEAGUE = {"kind": "human", "name": "a-colleague", "can_write": True}
STRANGER = {"kind": "human", "name": "stranger", "can_write": False}
# The reviewer's App: GitHub cannot grant it less than pull_requests: write, so it can dismiss a review.
REVIEWER_APP = {"kind": "lens", "name": "pr-review", "can_write": True}
ADVISORY = {"kind": "lens", "name": "coderabbit", "can_write": False}
# The author's App, whose push dismisses a stale approval: the bot that opens an agent's pull request.
AUTHOR_APP = {"kind": "app", "name": "combsmith-sf-dev-lead[bot]", "can_write": True}
# The machine user, which only approves: the approver the configuration names.
MACHINE = {"kind": "machine_user", "name": CONFIG["approver"], "can_write": True}
# Everyone who is not a person: an App, a Lens's App, a third-party reviewer, the machine user and a stranger.
NOT_PEOPLE = (AUTHOR_APP, REVIEWER_APP, ADVISORY, MACHINE, STRANGER)
# Kinds the Kernel cannot read: missing, null, a word GitHub uses for an account type, or one in another case.
NO_KIND = ("missing", None, "bot", "Bot", "User", "HUMAN", "", 1)
# The author's Run after the Maintainer asked for changes at minute 15.
ANSWERED = REVIEWED + [run(role="dev-lead", intent="fix-findings", at="2026-10-11T12:20:00Z", name="r2")]
# Every list the facts are read from, each with its flag in `complete`.
PARTS = ("acceptance", "reviews", "threads", "checks", "diff", "changed_paths", "runs", "timeline")
# What the session hooks are told, config/hooks.json: its protected paths and Lenses' inputs are the Kernel's list.
HOOKS = json.loads((ROOT / "config" / "hooks.json").read_text())
# A dependency update's pin of an Action, in the workflow file the verify Lens is read from (decision 0018).
PIN = ".github/workflows/verify.yml"
# What a review of a dependency update asks for, on its head.
REVIEW_IT = {"role": "pr-review", "intent": "review-change", "content_id": "sha256:aaaa"}


def at(minute: int) -> str:
    return "2026-10-11T12:%02d:00Z" % minute


def approvals(count, conclusion="failure", outcome="item", start=20):
    """Approval Runs. An approval is a Run with no Engine: only its `apply` holds the machine user's token."""
    return [run(intent="issue-approval", conclusion=conclusion, outcome=outcome, at=at(start + i), name="a%d" % i)
            for i in range(count)]


def dismissed(rv: dict, by, was: str = "changes_requested") -> dict:
    """`rv` once `by` has dismissed it. GitHub holds its state as dismissed; the timeline says what it was."""
    return dict(rv, state="dismissed", dismissed_by=dict(by) if isinstance(by, dict) else by, dismissed_from=was)


# The one form in which a Decision's evidence shows a workflow file's path: the configuration's own, and no longer than
# its limit. Any other text is shown as `unreadable`, so a path cannot carry a look-alike or a control character into it.
WORKFLOW_FORM = re.compile(r"^\.github/workflows/[A-Za-z0-9._-]+\.ya?ml$")


def shown(path) -> str:
    """How a Decision's evidence shows the workflow file a check names."""
    ok = isinstance(path, str) and WORKFLOW_FORM.match(path) and not path.endswith("\n")
    return path if ok and len(path) <= LIMITS["max_path_length"] else "unreadable"


def with_check(i: int, conclusion: str) -> list:
    """Every required check passing but the i-th, which concludes as GitHub says, or is not there ("absent")."""
    if conclusion == "absent":
        return GREEN[:i] + GREEN[i + 1:]
    return GREEN[:i] + [dict(GREEN[i], conclusion=conclusion)] + GREEN[i + 1:]


def example(pattern: str) -> str:
    """A path that a pattern of config/hooks.json names: each `*` as one letter, and a file below a directory."""
    return pattern.replace("*", "x") + ("a.txt" if pattern.endswith("/") else "")


def changing(**over) -> dict:
    """Facts for a pull request that changes `changed_paths`, given as paths, a rename or a copy as (path, previous):
    one file of the diff for each. Anything that is no list is given as it is, with one file in the diff."""
    paths = over.pop("changed_paths")
    if isinstance(paths, list):
        paths = [changed(*p) if isinstance(p, tuple) else changed(p) for p in paths]
    files = len(paths) if isinstance(paths, list) and paths else 1
    return facts(changed_paths=paths, diff={"files": files, "lines": 40, "truncated": False}, **over)


def later(time: str, minutes: int) -> str:
    """`time`, `minutes` later, as the calendar counts."""
    shape = "%Y-%m-%dT%H:%M:%SZ"
    return (datetime.datetime.strptime(time, shape) + datetime.timedelta(minutes=minutes)).strftime(shape)


def go(f, runs=(), ctx=None, cfg=None, now=NOW):
    d = decide(f, list(runs), context() if ctx is None else ctx, CONFIG if cfg is None else cfg, now)
    errors = validate(d, DECISION_SCHEMA)
    assert not errors, errors  # every Decision the Kernel emits is a valid one
    return d


class Readability(unittest.TestCase):
    def test_incomplete_facts_never_converge_or_admit(self):  # I-20
        # A list of Runs read short can hide a Run in progress or one that counts toward a ceiling (I-13).
        # A timeline read short undercounts the acts, and would let one past the act ceiling.
        for runs, whole in ((REVIEWED, "act"), ((), "admit")):
            self.assertEqual(go(facts(), runs)["outcome"], whole)
            for part in PARTS:
                f = facts()
                f["complete"][part] = False
                d = go(f, runs)
                self.assertEqual((d["outcome"], d["reason"], d["state"], d["evidence"]),
                                 ("defer", "facts_incomplete", None, [part]), part)

    def test_a_flag_that_is_not_exactly_true_is_incomplete(self):  # I-13, I-20
        # A fact read from outside is never given a default: a missing or malformed flag is not a whole list.
        approved = [review()]
        for runs in (REVIEWED, ()):
            for part in PARTS:
                for value in ("missing", "false", "no", "true", 1, 0, None):
                    f = facts(reviews=approved)
                    if value == "missing":
                        del f["complete"][part]
                    else:
                        f["complete"][part] = value
                    d = go(f, runs)
                    self.assertEqual((d["outcome"], d["reason"], d["evidence"]),
                                     ("defer", "facts_incomplete", [part]), (part, value))
        for flags in ("missing", True, None, ["runs"]):
            f = facts()
            if flags == "missing":
                del f["complete"]
            else:
                f["complete"] = flags
            d = go(f, REVIEWED)
            self.assertEqual((d["outcome"], d["reason"]), ("defer", "facts_incomplete"), flags)

    def test_the_kernel_reads_every_flag_the_facts_schema_requires(self):
        schema = json.loads((ROOT / "schemas" / "facts.schema.json").read_text())
        self.assertEqual(sorted(schema["properties"]["complete"]["required"]), sorted(facts()["complete"]))
        for part in schema["properties"]["complete"]["required"]:
            f = facts()
            del f["complete"][part]
            self.assertEqual(go(f, REVIEWED)["evidence"], [part], part)

    def test_incomplete_facts_are_read_after_a_merged_or_closed_item(self):  # I-20
        # The list of Runs is read once a pass for every item; cut short, it must not hide a merge or a close.
        for state in ("merged", "closed"):
            for part in PARTS:
                f = facts(state=state)
                f["complete"][part] = False
                d = go(f, REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["outcome"]), (state, state, "nothing"), part)

    def test_unreadable_pause_defers(self):  # I-13
        d = go(facts(), ctx={"active_runs": 0, "model_deferred_until": None})
        self.assertEqual((d["outcome"], d["reason"]), ("defer", "pause_unreadable"))

    def test_an_unreadable_pause_stops_approvals_and_merges(self):  # I-7, I-13
        approved = [review()]
        for reviews in ([], approved):
            unread = {"active_runs": 0, "model_deferred_until": None}
            for ctx in (unread, dict(unread, paused=None)):
                d = go(facts(reviews=reviews), REVIEWED, ctx=ctx)
                self.assertEqual((d["outcome"], d["reason"]), ("defer", "pause_unreadable"), ctx)

    def test_an_unknown_mergeable_never_converges(self):  # I-13, I-20
        approved = [review()]
        for reviews in ([], approved):
            d = go(facts(mergeable=None, reviews=reviews), REVIEWED)
            self.assertEqual((d["outcome"], d["reason"], d["state"]), ("defer", "mergeable_unreadable", None))
            d = go(facts(reviews=reviews), REVIEWED)
            self.assertEqual((d["outcome"], d["action"]), ("act", "enqueue" if reviews else "issue_approval"))

    def test_an_unknown_mergeable_is_read_after_what_needs_no_merge(self):  # I-13
        # GitHub reports a null merge state on merged and closed pull requests; read first, they would defer for ever.
        cases = [({"state": "merged"}, "merged", "merged"), ({"state": "closed"}, "closed", "closed"),
                 ({"label_events": [labelled("factory:hold")]}, "held", "human_hold"), ({"is_draft": True}, "draft", "draft")]
        for over, state, reason in cases:
            d = go(facts(mergeable=None, **over), REVIEWED)
            self.assertEqual((d["state"], d["reason"]), (state, reason), over)

    def test_an_unknown_mergeable_admits_nothing(self):  # I-13
        d = go(facts(mergeable=None))
        self.assertEqual((d["outcome"], d["reason"]), ("defer", "mergeable_unreadable"))
        self.assertEqual(go(facts())["outcome"], "admit")

    def test_only_true_or_false_is_a_known_merge_state(self):  # I-13
        absent = facts()
        del absent["mergeable"]
        for f in (absent, facts(mergeable="UNKNOWN"), facts(mergeable="true"), facts(mergeable=1)):
            d = go(f, REVIEWED)
            self.assertEqual((d["outcome"], d["reason"]), ("defer", "mergeable_unreadable"), f.get("mergeable"))

    def test_unreadable_capacity_defers(self):
        d = go(facts(), ctx={"paused": False, "model_deferred_until": None})
        self.assertEqual((d["outcome"], d["reason"]), ("defer", "capacity_unreadable"))


class Derived(unittest.TestCase):
    def test_the_same_inputs_give_the_same_decision(self):  # I-19: nothing is kept between calls
        f, runs = facts(threads=[thread()]), REVIEWED + [run(role="dev-lead", intent="fix-findings", name="r2")]
        before = json.dumps([f, runs], sort_keys=True)
        first = go(f, runs)
        go(facts(label_events=[labelled("factory:hold")]))
        self.assertEqual(go(f, runs), first)
        self.assertEqual(json.dumps([f, runs], sort_keys=True), before)

    def test_admission_is_given_facts_and_never_an_event(self):
        code = decide.__code__
        self.assertEqual(code.co_varnames[:code.co_argcount], ("facts", "runs", "context", "config", "now"))


class HumanControl(unittest.TestCase):
    def test_hold_label_binds(self):  # I-6
        d = go(facts(label_events=[labelled("factory:hold")]))
        self.assertEqual((d["outcome"], d["reason"], d["attention"]), ("hold", "human_hold", "needs_you"))

    def test_hands_off_is_left_alone(self):
        d = go(facts(label_events=[labelled("factory:hands-off")]))
        self.assertEqual((d["outcome"], d["reason"], d["attention"]), ("hold", "hands_off", "none"))

    def test_human_pause_admits_nothing(self):  # I-7
        d = go(facts(), ctx=context(paused=True))
        self.assertEqual((d["outcome"], d["reason"]), ("defer", "paused"))

    def test_a_pause_stops_approvals_and_merges_too(self):  # I-7
        approved = [review()]
        for reviews in ([], approved):
            d = go(facts(reviews=reviews), REVIEWED, ctx=context(paused=True))
            self.assertEqual((d["outcome"], d["reason"]), ("defer", "paused"))
            self.assertEqual(go(facts(reviews=reviews), REVIEWED)["outcome"], "act")

    def test_under_a_pause_a_hold_the_facts_establish_shows_first(self):  # I-7, I-26
        for paused in (True, None):
            d = go(facts(author="donpetry-bot"), REVIEWED, ctx=context(paused=paused))
            self.assertEqual((d["outcome"], d["reason"]), ("hold", "approver_is_author_or_last_pusher"))

    def test_draft_is_watched_only(self):
        self.assertEqual(go(facts(is_draft=True))["outcome"], "nothing")

    def test_a_writer_thread_gates_whatever_its_severity(self):
        f = facts(threads=[thread(kind="human", name="don-petry", severity=None)])
        self.assertEqual(go(f, REVIEWED)["reason"], "human_finding")

    def test_a_strangers_thread_does_not_gate(self):
        f = facts(threads=[thread(kind="human", name="stranger", can_write=False, severity=None)])
        self.assertEqual(go(f, REVIEWED)["state"], "converged")

    def test_a_writers_request_for_changes_does_not_converge(self):  # UJ-4, L-14
        # It gates as that person's thread does: the author answers it, then it waits for that person.
        asked = [review(state="changes_requested", **MAINTAINER)]
        d = go(facts(**AGENT, reviews=asked), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                         ("addressing", "human_finding", ["don-petry"], "admit", "needs_you"))
        self.assertEqual(d["admit"], {"role": "dev-lead", "intent": "fix-findings", "content_id": "sha256:aaaa"})
        d = go(facts(**AGENT, reviews=asked), ANSWERED)
        self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                         ("addressing", "awaiting_human", ["don-petry"], "nothing", "needs_you"))
        # The other side: with no request, the same item converges.
        d = go(facts(**AGENT), ANSWERED)
        self.assertEqual((d["state"], d["action"]), ("converged", "issue_approval"))

    def test_a_request_for_changes_stands_until_that_person_reviews_again(self):  # L-17
        asked = review(state="changes_requested", **MAINTAINER)
        # The author's answer is new content, and pr-review has reviewed it.
        f = dict(AGENT, content_id="sha256:bbbb")
        runs = ANSWERED + [run(content="sha256:bbbb", at=at(25), name="r3")]

        def after(*reviews):
            d = go(facts(**f, reviews=list(reviews)), runs)
            return d["state"], d["reason"]

        waits = ("addressing", "awaiting_human")
        # New content does not clear it: GitHub keeps it standing across pushes.
        self.assertEqual(after(asked), waits)
        # A later review that only comments does not clear it.
        self.assertEqual(after(asked, review(state="commented", **MAINTAINER, at=at(30))), waits)
        # Nor does an approval by anyone else: the approver's, or another writer's.
        self.assertEqual(after(asked, review(content="sha256:bbbb", at=at(30))), waits)
        self.assertEqual(after(asked, review(**COLLEAGUE, content="sha256:bbbb", at=at(30))), waits)
        # A dismissal clears it only if a person with write access made it. An App's does not (L-17).
        for who in (REVIEWER_APP, AUTHOR_APP, STRANGER, ADVISORY):
            self.assertEqual(after(dismissed(asked, who)), waits, who)
        # That person's approval clears it, whatever content it was given on, and wherever it is listed.
        approved = review(**MAINTAINER, content="sha256:bbbb", at=at(30))
        self.assertEqual(after(asked, approved), ("converged", "approval_due"))
        self.assertEqual(after(approved, asked), ("converged", "approval_due"))
        # So does a dismissal by a person with write access: that person, or another writer.
        for who in (MAINTAINER, COLLEAGUE):
            self.assertEqual(after(dismissed(asked, who)), ("converged", "approval_due"), who)
        # A request after the approval stands again, and is the author's to answer first.
        again = dict(asked, submitted_at=at(35))
        self.assertEqual(after(asked, approved, again), ("addressing", "human_finding"))

    def test_a_strangers_request_for_changes_does_not_gate(self):  # §4.6
        # A request from someone without write access, or from a Lens, gates nothing.
        for who in (STRANGER, REVIEWER_APP, ADVISORY):
            d = go(facts(**AGENT, reviews=[review(state="changes_requested", **who)]), REVIEWED)
            self.assertEqual((d["state"], d["outcome"], d["action"]), ("converged", "act", "issue_approval"), who)
        d = go(facts(**AGENT, reviews=[review(state="changes_requested", **MAINTAINER)]), REVIEWED)
        self.assertEqual((d["state"], d["reason"]), ("addressing", "human_finding"))

    def test_a_request_for_changes_is_read_after_the_checks_and_before_the_approval(self):
        asked = review(state="changes_requested", **MAINTAINER)
        # A failed check goes back to the author first, as it would with no request.
        d = go(facts(**AGENT, reviews=[asked], checks=with_check(0, "failure")), REVIEWED)
        self.assertEqual((d["reason"], d["evidence"]), ("check_failed", [LENS_OF[GREEN[0]["name"]]]))
        # A standing approval does not pass over the request: nothing is enqueued.
        d = go(facts(**AGENT, reviews=[review(), asked]), ANSWERED)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("addressing", "awaiting_human", "nothing"))
        self.assertEqual(go(facts(**AGENT, reviews=[review()]), ANSWERED)["action"], "enqueue")
        # One function says whose turn it is, for a thread and a request alike.
        f = facts(**AGENT, reviews=[asked], threads=[thread(kind="human", name="don-petry", severity=None)])
        d = go(f, REVIEWED)
        self.assertEqual((d["reason"], d["evidence"]), ("human_finding", ["T1", "don-petry"]))
        d = go(f, ANSWERED)
        self.assertEqual((d["reason"], d["evidence"]), ("awaiting_human", ["T1", "don-petry"]))

    def test_an_unreadable_review_never_converges(self):  # I-13
        # A fact read from outside is never given a default. A review whose author, write access, state or time
        # cannot be read defers: it is never counted as cleared, nor as a stranger's.
        asked = review(state="changes_requested", **MAINTAINER)
        unreadable = [{k: v for k, v in asked.items() if k != "by"}, dict(asked, by=None), dict(asked, by="don-petry"),
                      {k: v for k, v in asked.items() if k != "submitted_at"}, dict(asked, submitted_at=None),
                      dict(asked, state=None), dict(asked, state="CHANGES_REQUESTED"), dict(asked, state="pending"),
                      dismissed(asked, None), dismissed(asked, dict(COLLEAGUE, can_write=None)), "a review"]
        for value in ("missing", None, "true", 1, 0):
            by = dict(MAINTAINER)
            if value == "missing":
                del by["can_write"]
            else:
                by["can_write"] = value
            unreadable.append(dict(asked, by=by))
        for by in (dict(MAINTAINER, kind="bot"), dict(MAINTAINER, kind=None), dict(MAINTAINER, name=""),
                   dict(MAINTAINER, name=None), {"kind": "human", "can_write": True}):
            unreadable.append(dict(asked, by=by))
        for rv in unreadable:
            for runs, others in ((REVIEWED, []), (ANSWERED, []), (REVIEWED, [review()])):
                d = go(facts(**AGENT, reviews=others + [rv]), runs)
                # It needs the Maintainer, as a check with no verdict does: a port that misreads does not mend itself.
                self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                                 (None, "review_unreadable", "defer", "needs_you"), rv)
                self.assertNotIn("admit", d)
                self.assertNotIn("action", d)
        # The other side: read whole, the same item is enqueued, or waits on the request.
        self.assertEqual(go(facts(**AGENT, reviews=[review()]), REVIEWED)["action"], "enqueue")
        self.assertEqual(go(facts(**AGENT, reviews=[asked]), ANSWERED)["reason"], "awaiting_human")

    def test_a_dismissed_approval_neither_gates_nor_approves(self):
        # An App's push dismisses the Maintainer's stale approval. That person has not objected, so the item
        # waits for the approver as usual; and an approval that is dismissed approves nothing.
        approval = review(state="approved", **MAINTAINER)
        for was, rv in (("approved", approval), ("commented", review(state="commented", **MAINTAINER))):
            for who in (AUTHOR_APP, REVIEWER_APP, MAINTAINER):
                d = go(facts(**AGENT, reviews=[dismissed(rv, who, was)]), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["outcome"], d["action"]),
                                 ("converged", "approval_due", "act", "issue_approval"), (was, who))
        # The approver's own approval, once dismissed, is not standing: it is issued again, not enqueued.
        d = go(facts(**AGENT, reviews=[dismissed(review(), AUTHOR_APP, "approved")]), REVIEWED)
        self.assertEqual((d["reason"], d["action"]), ("approval_due", "issue_approval"))
        self.assertEqual(go(facts(**AGENT, reviews=[review()]), REVIEWED)["action"], "enqueue")
        # The Maintainer asks for changes, approves the fix, and an App's push dismisses that approval as stale.
        # The objection was answered, so nothing revives: the item waits only for the approver.
        asked = review(state="changes_requested", **MAINTAINER, at=at(12))
        for who in (AUTHOR_APP, REVIEWER_APP, MAINTAINER):
            d = go(facts(**AGENT, reviews=[asked, dismissed(approval, who, "approved")]), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["action"]), ("converged", "approval_due", "issue_approval"), who)
        # A dismissed comment was never a verdict, and answers nothing: the request stands.
        d = go(facts(**AGENT, reviews=[asked, dismissed(review(state="commented", **MAINTAINER), AUTHOR_APP, "commented")]),
               REVIEWED)
        self.assertEqual((d["state"], d["reason"]), ("addressing", "human_finding"))

    def test_neither_the_machine_user_nor_an_author_bot_ends_a_request(self):  # L-17, I-28
        # The approver and the bot that opened an agent's or a dependency update's pull request are not people. Read
        # as the kinds they are, their dismissal ends no request. Read as a person, the facts say what the configuration
        # or the class denies: the review cannot be read, and the item is the Maintainer's to see.
        asked = review(state="changes_requested", **MAINTAINER)
        for cls, who in (("agent", MACHINE), ("agent", AUTHOR_APP), ("dependency", AUTHOR_APP), ("maintainer", MACHINE)):
            f = dict(AGENT, **{"class": cls})
            d = go(facts(**f, reviews=[dismissed(asked, who)]), ANSWERED)
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("addressing", "awaiting_human", ["don-petry"]),
                             (cls, who))
            posing = dict(who, kind="human")
            for reviews in ([dismissed(asked, posing)], [asked, review(**posing, at=at(14))],
                            [review(state="changes_requested", **posing, at=at(12)), review(**posing, at=at(14))]):
                d = go(facts(**f, reviews=reviews), ANSWERED)
                self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                                 (None, "review_unreadable", "defer", "needs_you"), (cls, who))
        # The other side: on a maintainer's pull request its author is a person, and their dismissal ends it.
        f = dict(AGENT, **{"class": "maintainer"}, author="a-colleague")
        d = go(facts(**f, reviews=[dismissed(asked, COLLEAGUE)]), ANSWERED)
        self.assertEqual((d["state"], d["action"]), ("converged", "issue_approval"))
        d = go(facts(**f, reviews=[review(state="changes_requested", **COLLEAGUE, at=at(12)),
                                   review(**COLLEAGUE, at=at(14))]), ANSWERED)
        self.assertEqual((d["state"], d["action"]), ("converged", "issue_approval"))

    def test_a_review_time_in_another_format_is_unreadable(self):  # I-13
        # Times compare as text, so the one format is the contract: "9" would sort after every real time.
        asked = review(state="changes_requested", **MAINTAINER)
        approval = review(**MAINTAINER, at=at(30))
        for when in ("9", "2026-10-11T12:15:00.123Z", "2026-10-11T12:15Z", "2026-10-11 12:15:00Z", "2026-10-11T12:15:0aZ"):
            for reviews in ([dict(asked, submitted_at=when)], [asked, dict(approval, submitted_at=when)]):
                d = go(facts(**AGENT, reviews=reviews), ANSWERED)
                self.assertEqual((d["state"], d["reason"], d["outcome"]), (None, "review_unreadable", "defer"), when)
        self.assertEqual(go(facts(**AGENT, reviews=[asked, approval]), ANSWERED)["action"], "issue_approval")

    def test_a_request_and_an_approval_in_the_same_second_leave_the_request_standing(self):
        # Which came first cannot be told, so the objection stands: fail closed.
        asked = review(state="changes_requested", **MAINTAINER)
        approval = review(**MAINTAINER)
        for reviews in ([asked, approval], [approval, asked],
                        [dismissed(asked, AUTHOR_APP), approval], [approval, dismissed(asked, AUTHOR_APP)]):
            d = go(facts(**AGENT, reviews=reviews), REVIEWED)
            self.assertEqual((d["state"], d["reason"]), ("addressing", "human_finding"), [r["state"] for r in reviews])
        # The other side: an approval a second later answers it.
        d = go(facts(**AGENT, reviews=[review(**MAINTAINER, at="2026-10-11T12:15:01Z"), asked]), REVIEWED)
        self.assertEqual((d["state"], d["action"]), ("converged", "issue_approval"))

    def test_an_unreadable_review_admits_nothing(self):  # I-13
        # An unreadable fact never yields an action: not a model review, nor a fix for a conflict or a failed check.
        rv = dict(review(state="changes_requested", **MAINTAINER), by=None)
        for over in ({}, {"mergeable": False}, {"checks": with_check(0, "failure")}):
            for runs in ((), REVIEWED):
                d = go(facts(**AGENT, reviews=[rv], **over), runs)
                self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                                 (None, "review_unreadable", "defer", "needs_you"), (over, len(runs)))
                self.assertNotIn("admit", d)
        # The other side: read whole, the same item admits pr-review, or a fix.
        asked = review(state="changes_requested", **MAINTAINER)
        self.assertEqual(go(facts(**AGENT, reviews=[asked]))["admit"]["intent"], "review-change")
        self.assertEqual(go(facts(**AGENT, reviews=[asked], mergeable=False))["admit"]["intent"], "fix-findings")

    def test_an_unreadable_review_is_read_after_what_needs_no_review(self):  # I-13
        # A merged, closed, unserved, draft or held item is shown as it is, whatever its reviews say. A queued one is
        # not: whether it stays in the queue turns on its reviews.
        rv = dict(review(state="changes_requested", **MAINTAINER), by=None)
        cases = [({"state": "merged"}, "merged"), ({"state": "closed"}, "closed"), ({"targets_protected": False},
                 "base_not_protected"), ({"is_draft": True}, "draft"), ({"label_events": [labelled("factory:hold")]}, "human_hold"),
                 ({"diff": {"files": 0, "lines": 0, "truncated": False}}, "empty_diff")]
        for over, reason in cases:
            d = go(facts(**dict(AGENT, **over), reviews=[rv]), REVIEWED)
            self.assertEqual(d["reason"], reason, over)

    def test_a_review_not_dismissed_that_carries_dismissal_fields_is_unreadable(self):  # I-13
        # The schema cannot say "null unless dismissed", so the Kernel holds it. Read as given, an approval tagged
        # as dismissed from a request would sort as a request in the same second, replace it, and drop the gate.
        asked = review(state="changes_requested", **MAINTAINER)
        approval = review(**MAINTAINER)
        tagged = [dict(approval, dismissed_from="changes_requested"), dict(approval, dismissed_by=dict(COLLEAGUE)),
                  dict(approval, dismissed_from="approved", dismissed_by=dict(AUTHOR_APP)),
                  dict(asked, dismissed_from="approved"), dict(asked, dismissed_by=dict(MAINTAINER)),
                  dict(review(state="commented", **MAINTAINER), dismissed_from="commented")]
        for rv in tagged:
            for reviews in ([asked, rv], [rv, asked], [rv]):
                d = go(facts(**AGENT, reviews=reviews), ANSWERED)
                self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                                 (None, "review_unreadable", "defer", "needs_you"), rv)
                self.assertNotIn("action", d)
        # The other side: with both fields null, the request in the same second stands, and waits for that person.
        d = go(facts(**AGENT, reviews=[asked, approval]), ANSWERED)
        self.assertEqual((d["state"], d["reason"], d["attention"]), ("addressing", "awaiting_human", "needs_you"))

    def test_a_request_for_changes_an_app_dismissed_still_stands(self):  # L-17
        asked = review(state="changes_requested", **MAINTAINER)
        for who in (AUTHOR_APP, REVIEWER_APP):
            d = go(facts(**AGENT, reviews=[dismissed(asked, who)]), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("addressing", "human_finding", ["don-petry"]), who)
            d = go(facts(**AGENT, reviews=[dismissed(asked, who)]), ANSWERED)
            self.assertEqual((d["state"], d["reason"], d["attention"]), ("addressing", "awaiting_human", "needs_you"), who)
        # The other side: dismissed by a person with write access, it is gone.
        d = go(facts(**AGENT, reviews=[dismissed(asked, MAINTAINER)]), ANSWERED)
        self.assertEqual((d["state"], d["action"]), ("converged", "issue_approval"))

    def test_an_unreadable_dismissed_from_defers(self):  # I-13
        # What a dismissal took away decides whether anything stands. Unread, it is never read as cleared.
        asked = review(state="changes_requested", **MAINTAINER)
        for who in (AUTHOR_APP, MAINTAINER):
            for was in ("missing", None, "dismissed", "APPROVED", "", 0, True):
                rv = dismissed(asked, who, was)
                if was == "missing":
                    del rv["dismissed_from"]
                for runs, others in ((REVIEWED, []), (ANSWERED, []), (REVIEWED, [review()])):
                    d = go(facts(**AGENT, reviews=others + [rv]), runs)
                    self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                                     (None, "review_unreadable", "defer", "needs_you"), (who, was))
                    self.assertNotIn("action", d)
        # The other side: each readable earlier state is read.
        self.assertEqual(go(facts(**AGENT, reviews=[dismissed(asked, MAINTAINER, "approved")]), REVIEWED)["action"],
                         "issue_approval")
        self.assertEqual(go(facts(**AGENT, reviews=[dismissed(asked, AUTHOR_APP)]), REVIEWED)["reason"], "human_finding")


def without(actor: dict, kind) -> dict:
    """`actor` with a kind the Kernel cannot read: `kind`, or none at all if it is "missing"."""
    if kind == "missing":
        return {k: v for k, v in actor.items() if k != "kind"}
    return dict(actor, kind=kind)


class OnlyAPersonEnds(unittest.TestCase):
    """What a person placed, only a person ends. A person is an actor of kind `human` with write access; nobody else is.

    The port tells a person, an App, a Lens's App and the machine user apart from GitHub's account type and the
    configuration, never from a name's spelling (I-28, L-57).
    """

    def test_an_actor_whose_kind_cannot_be_read_defers(self):  # I-13, I-28
        # Whoever reviewed, dismissed, opened or resolved a thread, or added or removed a label: a kind the Kernel does
        # not know could be a person's, so nothing is decided on it. The item is the Maintainer's to see, and a queued
        # one leaves the queue.
        asked = review(state="changes_requested", **MAINTAINER)
        person = thread(kind="human", name="don-petry", severity=None)
        for kind in NO_KIND:
            posing = without(MAINTAINER, kind)
            cases = [({"reviews": [dict(asked, by=posing)]}, "review_unreadable", []),
                     ({"reviews": [dismissed(asked, posing)]}, "review_unreadable", []),
                     ({"threads": [dict(person, opened_by=posing)]}, "thread_unreadable", ["T1"]),
                     ({"threads": [dict(person, resolved=True, resolved_by=posing)]}, "thread_unreadable", ["T1"]),
                     ({"label_events": [labelled("factory:hold", posing)]}, "label_unreadable", []),
                     ({"label_events": [labelled("factory:hold"), unlabelled("factory:hold", posing)]},
                      "label_unreadable", [])]
            for over, reason, evidence in cases:
                for runs in ((), REVIEWED):
                    d = go(facts(**dict(AGENT, **over)), runs)
                    self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                     (None, reason, evidence, "defer", "needs_you"), (kind, over))
                    self.assertNotIn("admit", d)
                    self.assertNotIn("action", d)
                d = go(facts(**dict(AGENT, queue=True, **dict({"reviews": APPROVED}, **over))), ANSWERED)
                self.assertEqual((d["reason"], d["outcome"], d.get("action")), (reason, "act", "dequeue"), (kind, over))
        # The other side: read whole, the same actors are read.
        self.assertEqual(go(facts(**AGENT, reviews=[asked]), ANSWERED)["reason"], "awaiting_human")
        self.assertEqual(go(facts(**AGENT, threads=[person]), ANSWERED)["reason"], "awaiting_human")
        self.assertEqual(go(facts(**AGENT, label_events=[labelled("factory:hold")]), ANSWERED)["reason"], "human_hold")

    def test_the_approver_or_an_author_bot_read_as_another_kind_cannot_be_read(self):  # I-13, I-28
        # The machine user is the approver the configuration names, and nobody else; an agent's or a dependency update's
        # pull request was opened by an App. Facts that say otherwise contradict the configuration or the class.
        for cls, who, kinds in (("maintainer", MACHINE, ("human", "lens", "app")),
                                ("agent", AUTHOR_APP, ("human", "lens", "machine_user")),
                                ("dependency", AUTHOR_APP, ("human", "lens", "machine_user")),
                                ("maintainer", dict(MAINTAINER, kind="machine_user"), ("machine_user",))):
            f = dict(AGENT, **{"class": cls})
            for kind in kinds:
                posing = dict(who, kind=kind)
                cases = [({"reviews": [review(state="commented", **posing)]}, "review_unreadable"),
                         ({"threads": [thread(kind="human", name="don-petry", severity=None, resolved=True,
                                              resolved_by=posing)]}, "thread_unreadable"),
                         ({"label_events": [labelled("factory:admit", posing)]}, "label_unreadable")]
                for over, reason in cases:
                    d = go(facts(**dict(f, **over)), REVIEWED)
                    self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                                     (None, reason, "defer", "needs_you"), (cls, posing, reason))
        # The other side: each read as the kind it is, nothing defers.
        for cls, who in (("maintainer", MACHINE), ("agent", AUTHOR_APP), ("dependency", AUTHOR_APP),
                         ("maintainer", MAINTAINER), ("maintainer", AUTHOR_APP)):
            for over in ({"reviews": [review(state="commented", **who)]},
                         {"label_events": [labelled("factory:admit", who)]}):
                d = go(facts(**dict(AGENT, **{"class": cls}, **over)), REVIEWED)
                self.assertEqual((d["state"], d["action"]), ("converged", "issue_approval"), (cls, who, over))

    def test_a_hold_that_anyone_but_a_person_removed_still_binds(self):  # I-6, I-21, L-02
        # A Hold is a stop, so anyone may place one, and an App's binds as a person's does. Only a person ends it.
        for placed_by in (MAINTAINER, AUTHOR_APP):
            for who in NOT_PEOPLE:
                events = [labelled("factory:hold", placed_by), unlabelled("factory:hold", who)]
                d = go(facts(label_events=events), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                 ("held", "human_hold", ["factory:hold"], "hold", "needs_you"), (placed_by, who))
                d = go(facts(queue=True, reviews=APPROVED, label_events=events), REVIEWED)
                self.assertEqual((d["reason"], d["outcome"], d.get("action")), ("human_hold", "act", "dequeue"), who)
            # The other side: a person with write access removes it, the Maintainer or another writer, and work resumes.
            for who in (MAINTAINER, COLLEAGUE):
                d = go(facts(label_events=[labelled("factory:hold", placed_by), unlabelled("factory:hold", who)]),
                       REVIEWED)
                self.assertEqual((d["state"], d["action"]), ("converged", "issue_approval"), (placed_by, who))
        # A Hold an App removed binds until a person ends it: placed again and removed by a person, it is gone.
        events = [labelled("factory:hold"), unlabelled("factory:hold", AUTHOR_APP), labelled("factory:hold", at=at(3)),
                  unlabelled("factory:hold", at=at(4))]
        self.assertEqual(go(facts(label_events=events), REVIEWED)["action"], "issue_approval")

    def test_hands_off_binds_only_when_a_person_placed_it(self):
        hands_off = "factory:hands-off"
        for who in (MAINTAINER, COLLEAGUE):
            for queue in (False, True):
                d = go(facts(queue=queue, reviews=APPROVED, label_events=[labelled(hands_off, who)]), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                 ("held", "hands_off", [hands_off], "hold", "none"), (who, queue))
                self.assertNotIn("action", d)
        # Placed by anyone else it is read as a Hold: it stops, it is the Maintainer's to see, and it takes a queued
        # item out. An App adding hands-off can no longer freeze an item in the merge queue.
        for who in NOT_PEOPLE:
            d = go(facts(label_events=[labelled(hands_off, who)]), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                             ("held", "human_hold", [hands_off], "hold", "needs_you"), who)
            d = go(facts(queue=True, reviews=APPROVED, label_events=[labelled(hands_off, who)]), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d.get("action")),
                             ("held", "human_hold", "act", "dequeue"), who)
            # A person's hands-off that anyone else removed still binds, as it was placed.
            d = go(facts(queue=True, reviews=APPROVED, label_events=[labelled(hands_off), unlabelled(hands_off, who)]),
                   REVIEWED)
            self.assertEqual((d["reason"], d["outcome"]), ("hands_off", "hold"), who)
            self.assertNotIn("action", d)
            # An App's that anyone else removed still binds as a Hold.
            d = go(facts(label_events=[labelled(hands_off, AUTHOR_APP), unlabelled(hands_off, who)]), REVIEWED)
            self.assertEqual((d["reason"], d["outcome"]), ("human_hold", "hold"), who)
        # Who placed it last is who placed it: a person's, removed, then added again by an App, is a Hold.
        events = [labelled(hands_off), unlabelled(hands_off), labelled(hands_off, AUTHOR_APP, at=at(3))]
        self.assertEqual(go(facts(label_events=events), REVIEWED)["reason"], "human_hold")
        # The other side: a person removes it, whoever placed it, and the item is served.
        for placed_by in (MAINTAINER, AUTHOR_APP):
            d = go(facts(label_events=[labelled(hands_off, placed_by), unlabelled(hands_off, COLLEAGUE)]), REVIEWED)
            self.assertEqual((d["state"], d["action"]), ("converged", "issue_approval"), placed_by)

    def test_admit_admits_only_when_a_person_placed_it(self):  # I-25, I-36
        outside = {"class": "outside", "author": "stranger", "last_pusher": "stranger"}
        admit = "factory:admit"
        for who in NOT_PEOPLE:
            d = go(facts(**outside, label_events=[labelled(admit, who)]))
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "outside_not_admitted", "hold"), who)
            d = go(facts(**outside, queue=True, reviews=APPROVED, label_events=[labelled(admit, who)]), REVIEWED)
            self.assertEqual((d["reason"], d["outcome"], d.get("action")), ("outside_not_admitted", "act", "dequeue"))
            # A person's admission that anyone else removed stands, as it was placed.
            d = go(facts(**outside, label_events=[labelled(admit), unlabelled(admit, who)]))
            self.assertEqual(d["admit"]["intent"], "review-change", who)
        # Who placed it last is who placed it: a person's, removed, then added again by an App, admits nothing.
        events = [labelled(admit), unlabelled(admit), labelled(admit, AUTHOR_APP, at=at(3))]
        self.assertEqual(go(facts(**outside, label_events=events))["reason"], "outside_not_admitted")
        # The other side: placed by a person with write access after the latest push, it admits; removed by a person,
        # it no longer does.
        for who in (MAINTAINER, COLLEAGUE):
            self.assertEqual(go(facts(**outside, label_events=[labelled(admit, who)]))["admit"]["intent"],
                             "review-change", who)
            d = go(facts(**outside, label_events=[labelled(admit), unlabelled(admit, who)]))
            self.assertEqual(d["reason"], "outside_not_admitted", who)

    def test_label_events_are_read_in_the_order_they_happened(self):
        # The port lists them as the timeline does, and the Kernel reads them by their time, in either order.
        added, removed = labelled("factory:hold", at=at(3)), unlabelled("factory:hold", at=at(4))
        for events in ([added, removed], [removed, added]):
            self.assertEqual(go(facts(label_events=events), REVIEWED)["action"], "issue_approval")
        added, removed = labelled("factory:hold", at=at(4)), unlabelled("factory:hold", at=at(3))
        for events in ([added, removed], [removed, added]):
            self.assertEqual(go(facts(label_events=events), REVIEWED)["reason"], "human_hold")

    def test_in_the_same_second_each_label_fails_closed(self):  # I-6, I-13, I-25
        # Which came first cannot be told, so each label is read the way that stops work, as a request for changes
        # stands beside an approval in the same second. A Hold stands. An admission does not. Hands-off is read as a
        # Hold, since either reading of it fails open somewhere: standing, it would leave a queued item to merge; ended,
        # it would let the Factory act on an item a person marked.
        outside = {"class": "outside", "author": "stranger", "last_pusher": "stranger", "last_push_at": at(0)}
        for order in ((0, 1), (1, 0)):
            def tie(label):
                pair = [labelled(label, at=at(3)), unlabelled(label, at=at(3))]
                return [pair[i] for i in order]
            d = go(facts(label_events=tie("factory:hold")), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("held", "human_hold", ["factory:hold"]), order)
            d = go(facts(**outside, label_events=tie("factory:admit")))
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "outside_not_admitted", "hold"), order)
            d = go(facts(label_events=tie("factory:hands-off")), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["attention"]),
                             ("held", "human_hold", ["factory:hands-off"], "needs_you"), order)
            d = go(facts(queue=True, reviews=APPROVED, checks=with_check(0, "failure"),
                         label_events=tie("factory:hands-off")), REVIEWED)
            self.assertEqual((d["reason"], d["outcome"], d.get("action")), ("human_hold", "act", "dequeue"), order)
        # An admission an App removed in the same second still stands: an App's removal ends nothing.
        d = go(facts(**outside, label_events=[unlabelled("factory:admit", AUTHOR_APP, at=at(3)),
                                              labelled("factory:admit", at=at(3))]))
        self.assertEqual(d["admit"]["intent"], "review-change")
        # The other side: a second apart, the later event decides.
        later_ = "2026-10-11T12:03:01Z"
        events = [labelled("factory:hold", at=at(3)), unlabelled("factory:hold", at=later_)]
        self.assertEqual(go(facts(label_events=events), REVIEWED)["action"], "issue_approval")
        events = [unlabelled("factory:admit", at=at(3)), labelled("factory:admit", at=later_)]
        self.assertEqual(go(facts(**outside, label_events=events))["admit"]["intent"], "review-change")
        events = [unlabelled("factory:hands-off", at=at(3)), labelled("factory:hands-off", at=later_)]
        d = go(facts(queue=True, reviews=APPROVED, checks=with_check(0, "failure"), label_events=events), REVIEWED)
        self.assertEqual((d["reason"], d["outcome"]), ("hands_off", "hold"))
        self.assertNotIn("action", d)

    def test_only_a_persons_removal_in_the_same_second_is_a_tie(self):  # L-17, I-6
        # A removal by anyone but a person ends nothing, so in the same second it changes nothing either: a person's
        # hands-off stays theirs, a Hold stands, and an admission stands.
        outside = {"class": "outside", "author": "stranger", "last_pusher": "stranger", "last_push_at": at(0)}
        for who in NOT_PEOPLE:
            for order in ((0, 1), (1, 0)):
                def tie(label):
                    pair = [labelled(label, MAINTAINER, at=at(3)), unlabelled(label, who, at=at(3))]
                    return [pair[i] for i in order]
                d = go(facts(queue=True, reviews=[review()], label_events=tie("factory:hands-off")), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "hands_off", "hold"), (who, order))
                self.assertNotIn("action", d)
                d = go(facts(label_events=tie("factory:hold")), REVIEWED)
                self.assertEqual(d["reason"], "human_hold", (who, order))
                self.assertEqual(go(facts(**outside, label_events=tie("factory:admit")))["admit"]["intent"],
                                 "review-change", (who, order))
        # The other side: a person's removal in the same second is a tie, and hands-off is read as a Hold.
        events = [labelled("factory:hands-off", at=at(3)), unlabelled("factory:hands-off", COLLEAGUE, at=at(3))]
        self.assertEqual(go(facts(label_events=events), REVIEWED)["reason"], "human_hold")

    def test_hands_off_ties_only_with_its_own_removal_in_that_second(self):  # I-6
        # Another label removed in the same second, or hands-off removed at another time, is no tie.
        events = [labelled("factory:hold"), unlabelled("factory:hold", at=at(3)), labelled("factory:hands-off", at=at(3))]
        d = go(facts(queue=True, reviews=APPROVED, label_events=events), REVIEWED)
        self.assertEqual((d["reason"], d["evidence"], d["outcome"]), ("hands_off", ["factory:hands-off"], "hold"))
        self.assertNotIn("action", d)
        events = [labelled("factory:hands-off"), unlabelled("factory:hands-off"), labelled("factory:hands-off", at=at(3))]
        d = go(facts(queue=True, reviews=APPROVED, label_events=events), REVIEWED)
        self.assertEqual((d["reason"], d["outcome"]), ("hands_off", "hold"))
        self.assertNotIn("action", d)

    def test_a_resolver_with_the_openers_name_who_is_not_a_person_closes_nothing(self):  # L-17, L-57
        # A thread is closed by who resolved it, as the kind and access say, never by the name alone.
        for who in ({"kind": "app", "name": "don-petry", "can_write": True},
                    {"kind": "human", "name": "don-petry", "can_write": False},
                    {"kind": "lens", "name": "don-petry", "can_write": True}):
            th = thread(kind="human", name="don-petry", severity=None, resolved=True, resolved_by=who)
            self.assertEqual(go(facts(threads=[th]), REVIEWED)["reason"], "human_finding", who)
        for who in ({"kind": "app", "name": "pr-review", "can_write": True},
                    {"kind": "human", "name": "pr-review", "can_write": False}):
            th = thread(resolved=True, resolved_by=who)
            self.assertEqual(go(facts(threads=[th]), REVIEWED)["reason"], "findings_open", who)
        # The other side: the opener itself, read as what it is, closes it.
        for th in (thread(kind="human", name="don-petry", severity=None, resolved=True), thread(resolved=True)):
            self.assertEqual(go(facts(threads=[th]), REVIEWED)["action"], "issue_approval")

    def test_what_a_person_placed_is_not_replaced_by_anyone_else_placing_it(self):  # L-17, I-36
        # An App that takes a person's label off and puts it back has not placed it: it stands as the person placed it.
        outside = {"class": "outside", "author": "stranger", "last_pusher": "stranger"}
        for who in NOT_PEOPLE:
            again = [unlabelled("factory:hands-off", who), labelled("factory:hands-off", who, at=at(3))]
            d = go(facts(queue=True, reviews=APPROVED, label_events=[labelled("factory:hands-off")] + again), REVIEWED)
            self.assertEqual((d["reason"], d["outcome"]), ("hands_off", "hold"), who)
            self.assertNotIn("action", d)
            again = [unlabelled("factory:admit", who), labelled("factory:admit", who, at=at(3))]
            d = go(facts(**outside, label_events=[labelled("factory:admit")] + again))
            self.assertEqual(d["admit"]["intent"], "review-change", who)
            # Nor does it renew an admission the author's push has lapsed.
            d = go(facts(**outside, last_push_at=at(2), label_events=[labelled("factory:admit")] + again))
            self.assertEqual(d["reason"], "outside_not_admitted", who)
        # The other side: a person who places it again places it anew, and after a person's removal anyone's counts.
        d = go(facts(**outside, last_push_at=at(2), label_events=[labelled("factory:admit"),
                                                                  labelled("factory:admit", COLLEAGUE, at=at(3))]))
        self.assertEqual(d["admit"]["intent"], "review-change")
        events = [labelled("factory:hands-off"), unlabelled("factory:hands-off"),
                  labelled("factory:hands-off", AUTHOR_APP, at=at(3))]
        self.assertEqual(go(facts(label_events=events), REVIEWED)["reason"], "human_hold")

    def test_hands_off_is_not_read_from_a_timeline_read_short(self):  # I-13, I-20
        # GitHub pages the timeline oldest first, so a read cut short can drop a person's later removal. Hands-off read
        # from it would leave a queued item in the queue, to merge over whatever else the read missed.
        for who in (MAINTAINER, COLLEAGUE):
            f = facts(queue=True, reviews=APPROVED, label_events=[labelled("factory:hands-off", who)])
            f["complete"]["timeline"] = False
            d = go(f, REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d.get("action")),
                             (None, "facts_incomplete", "act", "dequeue"), who)
        # The other side: read in full, a person's hands-off leaves it where it is, whatever else was read short.
        f = facts(queue=True, reviews=APPROVED, label_events=[labelled("factory:hands-off")])
        f["complete"]["threads"] = False
        d = go(f, REVIEWED)
        self.assertEqual((d["reason"], d["outcome"]), ("facts_incomplete", "defer"))
        self.assertNotIn("action", d)

    def test_a_person_whose_login_is_a_bots_is_unreadable(self):  # I-13, L-57
        # GitHub gives no person a login with a bracket, so a human that ends in [bot] was misread. A name's spelling
        # only ever refuses an actor: it never makes one a person, nor anything else.
        posing = {"kind": "human", "name": "some-app[bot]", "can_write": True}
        cases = [({"reviews": [review(state="commented", **posing)]}, "review_unreadable"),
                 ({"threads": [thread(kind="human", name="don-petry", severity=None, resolved=True,
                                      resolved_by=posing)]}, "thread_unreadable"),
                 ({"label_events": [labelled("factory:hold"), unlabelled("factory:hold", posing)]}, "label_unreadable")]
        for over, reason in cases:
            d = go(facts(**over), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                             (None, reason, "defer", "needs_you"), reason)
        # The other side: an App of that name, read as one, is read.
        app = dict(posing, kind="app")
        self.assertEqual(go(facts(reviews=[review(state="commented", **app)]), REVIEWED)["action"], "issue_approval")

    def test_a_label_event_that_cannot_be_read_defers(self):  # I-13
        # Who added or removed a control label, what was done and when decide whether it binds. A fact read from outside
        # is never given a default.
        broken = []
        for label in ("factory:hold", "factory:hands-off", "factory:admit"):
            for ev in (labelled(label), unlabelled(label)):
                broken += [dict(ev, by=None), dict(ev, by="don-petry"), dict(ev, by=dict(MAINTAINER, can_write=None)),
                           dict(ev, by=dict(MAINTAINER, can_write="true")), dict(ev, by=dict(MAINTAINER, name="")),
                           dict(ev, at=None), dict(ev, at="2026-10-11 12:01:00Z"), dict(ev, at="2026-02-30T12:01:00Z"),
                           dict(ev, action=None), dict(ev, action="added"), dict(ev, action="LABELED")]
                for field in ("by", "at", "action"):
                    broken.append({k: v for k, v in ev.items() if k != field})
        broken += [dict(labelled("factory:hold"), label=None), {"action": "labeled", "by": dict(MAINTAINER), "at": at(1)},
                   "factory:hold"]
        outside = {"class": "outside", "author": "stranger", "last_pusher": "stranger"}
        for ev in broken:
            for over in ({}, outside):
                for runs in ((), REVIEWED):
                    d = go(facts(**over, label_events=[labelled("factory:admit"), ev]), runs)
                    self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                                     (None, "label_unreadable", "defer", "needs_you"), ev)
                    self.assertNotIn("admit", d)
            # It is read before a Hold, and before hands-off: on a queued item it is a stop.
            for placed in ("factory:hold", "factory:hands-off"):
                d = go(facts(queue=True, reviews=APPROVED, label_events=[labelled(placed), ev]), REVIEWED)
                self.assertEqual((d["reason"], d["outcome"], d.get("action")), ("label_unreadable", "act", "dequeue"), ev)
            # It is read after what needs no label.
            for over, reason in (({"state": "merged"}, "merged"), ({"is_draft": True}, "draft"),
                                 ({"targets_protected": False}, "base_not_protected")):
                self.assertEqual(go(facts(**over, label_events=[ev]), REVIEWED)["reason"], reason, (over, ev))
        # The other side: an event of a label the Factory does not read is not read, whoever made it.
        other = {"label": "bug", "action": "labeled", "by": dict(MAINTAINER, kind="bot"), "at": "yesterday"}
        self.assertEqual(go(facts(label_events=[other]), REVIEWED)["action"], "issue_approval")

    def test_a_persons_thread_resolved_by_anyone_but_that_person_stays_open(self):  # L-17
        for who in NOT_PEOPLE + (COLLEAGUE,):
            th = thread(kind="human", name="don-petry", severity=None, resolved=True, resolved_by=who)
            d = go(facts(threads=[th]), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("addressing", "human_finding", ["T1"]), who)
            d = go(facts(threads=[th]), ANSWERED)
            self.assertEqual((d["reason"], d["outcome"], d["attention"]), ("awaiting_human", "nothing", "needs_you"), who)
            d = go(facts(queue=True, reviews=APPROVED, threads=[th]), REVIEWED)
            self.assertEqual((d["reason"], d["evidence"], d.get("action")), ("gate_open", ["T1"], "dequeue"), who)
        # The other side: resolved by that person, it is closed.
        th = thread(kind="human", name="don-petry", severity=None, resolved=True)
        self.assertEqual(go(facts(threads=[th]), REVIEWED)["action"], "issue_approval")
        self.assertEqual(go(facts(queue=True, reviews=APPROVED, threads=[th]), REVIEWED)["reason"], "in_merge_queue")

    def test_a_lens_thread_resolved_by_anyone_but_that_lens_or_a_writer_stays_open(self):  # L-17
        # The author agent resolving the threads that hold it among them: no Role decides a Finding about its own work.
        another_lens = dict(REVIEWER_APP, name="security-review")
        for who in (AUTHOR_APP, ADVISORY, another_lens, MACHINE, STRANGER):
            for category in ("functional", "security"):
                th = thread(category=category, resolved=True, resolved_by=who)
                d = go(facts(threads=[th]), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"]), ("addressing", "findings_open", ["T1"]), who)
                d = go(facts(queue=True, reviews=APPROVED, threads=[th]), REVIEWED)
                self.assertEqual((d["reason"], d.get("action")), ("gate_open", "dequeue"), who)
            # Still open, it is read: a category or severity it cannot be read is unreadable.
            th = thread(severity=None, category=None, resolved=True, resolved_by=who)
            self.assertEqual(go(facts(threads=[th]), REVIEWED)["reason"], "thread_unreadable", who)
        # The other side: that Lens's own App, or a person with write access, closes it.
        for who in (REVIEWER_APP, MAINTAINER, COLLEAGUE):
            for th in (thread(resolved=True, resolved_by=who), thread(severity=None, category=None, resolved=True,
                                                                       resolved_by=who)):
                self.assertEqual(go(facts(threads=[th]), REVIEWED)["action"], "issue_approval", who)

    def test_a_thread_whose_resolution_cannot_be_read_defers(self):  # I-13
        # A thread says whether it is resolved, exactly, and a resolved one says who resolved it: without them, a
        # person's thread could be read as closed. One that is not resolved names nobody.
        person = thread(kind="human", name="don-petry", severity=None)
        broken = [dict(person, resolved=True, resolved_by=None), dict(person, resolved=True, resolved_by="don-petry"),
                  dict(person, resolved=False, resolved_by=dict(MAINTAINER)), dict(person, resolved="true"),
                  dict(person, resolved=None), {k: v for k, v in person.items() if k != "resolved"},
                  dict(thread(kind="human", name="don-petry", severity=None, resolved=True), resolved_by=None)]
        for th in broken:
            for queue in (False, True):
                d = go(facts(queue=queue, reviews=APPROVED, threads=[th]), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["attention"]),
                                 (None, "thread_unreadable", ["T1"], "needs_you"), th)
                self.assertEqual((d["outcome"], d.get("action")), ("act", "dequeue") if queue else ("defer", None), th)
        # The other side: open and naming nobody, or resolved and naming who, it is read.
        self.assertEqual(go(facts(threads=[person]), REVIEWED)["reason"], "human_finding")
        resolved = thread(kind="human", name="don-petry", severity=None, resolved=True)
        self.assertEqual(go(facts(threads=[resolved]), REVIEWED)["action"], "issue_approval")

    def test_only_the_approvers_approval_stands(self):  # I-9, decision 0005
        # A person's approval answers that person's request, and approves no content: the approver's alone stands.
        for who in (MAINTAINER, COLLEAGUE, REVIEWER_APP, AUTHOR_APP, ADVISORY):
            d = go(facts(reviews=[review(**who)]), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["action"]), ("converged", "approval_due", "issue_approval"), who)
            d = go(facts(queue=True, reviews=[review(**who)]), REVIEWED)
            self.assertEqual((d["reason"], d.get("action")), ("approval_lost", "dequeue"), who)
        # Nor does the machine user's without write access: GitHub would not count it.
        d = go(facts(reviews=[review(**dict(MACHINE, can_write=False))]), REVIEWED)
        self.assertEqual((d["reason"], d["action"]), ("approval_due", "issue_approval"))
        # The other side: the machine user's approval of this content stands.
        self.assertEqual(go(facts(reviews=[review(**MACHINE)]), REVIEWED)["action"], "enqueue")

    def test_only_a_person_ends_a_request_for_changes(self):  # L-17
        asked = review(state="changes_requested", **MAINTAINER)
        for who in NOT_PEOPLE:
            d = go(facts(**AGENT, reviews=[dismissed(asked, who)]), ANSWERED)
            self.assertEqual((d["reason"], d["evidence"]), ("awaiting_human", ["don-petry"]), who)
            # Nor does an approval by anyone but that person.
            d = go(facts(**AGENT, reviews=[asked, review(**who, at=at(30))]), ANSWERED)
            self.assertEqual((d["reason"], d["evidence"]), ("awaiting_human", ["don-petry"]), who)
        # The other side: a person with write access dismisses it.
        for who in (MAINTAINER, COLLEAGUE):
            d = go(facts(**AGENT, reviews=[dismissed(asked, who)]), ANSWERED)
            self.assertEqual(d["action"], "issue_approval", who)


class Classes(unittest.TestCase):
    def test_outside_item_gets_no_run_until_admitted(self):  # I-25
        d = go(facts(**{"class": "outside"}))
        self.assertEqual((d["outcome"], d["reason"]), ("hold", "outside_not_admitted"))

    def test_admission_lapses_on_the_next_push(self):  # I-36
        f = facts(**{"class": "outside"}, label_events=[labelled("factory:admit", at="2026-10-11T11:00:00Z")],
                  last_push_at="2026-10-11T12:00:00Z")
        self.assertEqual(go(f)["reason"], "outside_not_admitted")
        f["label_events"] = [labelled("factory:admit", at="2026-10-11T12:30:00Z")]
        self.assertEqual(go(f)["outcome"], "admit")

    def test_stacked_pull_request_is_not_served(self):
        d = go(facts(targets_protected=False))
        self.assertEqual((d["state"], d["outcome"]), ("not_served", "nothing"))

    def test_a_state_that_admits_nothing_is_nobodys_to_see(self):
        # Merged, closed and not served admit nothing, and are shown as nothing, a Run still in progress or not. Not
        # served is no end of the Lifecycle: GitHub serves the item again when it retargets it.
        for over in ({"state": "merged"}, {"state": "closed"}, {"targets_protected": False}):
            for runs in ([], [run(status="in_progress")]):
                d = go(facts(**over), runs)
                self.assertEqual((d["outcome"], d["attention"]), ("nothing", "none"), (over, runs))
        # The other side: on an item that is served, a Run in progress is shown as working, and with none it waits.
        d = go(facts(), [run(status="in_progress")])
        self.assertEqual((d["state"], d["outcome"], d["attention"]), ("verifying", "nothing", "working"))
        d = go(facts(), [run()])
        self.assertEqual((d["state"], d["attention"]), ("converged", "ready"))

    def test_a_dependency_update_needs_no_model_review(self):  # §4.2
        self.assertEqual(go(facts(**{"class": "dependency"}))["state"], "converged")
        d = go(facts(**DEPENDENCY))
        self.assertEqual((d["state"], d["outcome"], d["action"]), ("converged", "act", "issue_approval"))
        d = go(facts(**dict(DEPENDENCY, **{"class": "maintainer"})))
        self.assertEqual(d["admit"], {"role": "pr-review", "intent": "review-change", "content_id": "sha256:aaaa"})

    def test_every_other_class_needs_a_model_review(self):
        admitted = {"label_events": [labelled("factory:admit", at="2026-10-11T12:30:00Z")]}
        for cls, over in (("agent", {}), ("maintainer", {}), ("outside", admitted)):
            d = go(facts(**dict(DEPENDENCY, **{"class": cls}, **over)))
            self.assertEqual((d["reason"], d["admit"]["intent"]), ("awaiting_review", "review-change"), cls)

    def test_a_dependency_update_someone_else_pushed_to_needs_a_model_review(self):
        # The class is worked out from who opened the pull request; whoever pushed its head put content in it.
        for pusher in ("dev-lead[bot]", "don-petry"):
            f = facts(**dict(DEPENDENCY, last_pusher=pusher))
            d = go(f)
            self.assertEqual((d["reason"], d["admit"]["intent"]), ("awaiting_review", "review-change"), pusher)
            self.assertEqual(go(f, REVIEWED)["action"], "issue_approval")

    def test_a_dependency_update_is_judged_by_every_deterministic_lens(self):  # I-27
        # secret-scan and code-scanning judge security; a dependency update meets them as any change does.
        for i, check in enumerate(GREEN):
            failed = GREEN[:i] + [dict(check, conclusion="failure")] + GREEN[i + 1:]
            d = go(facts(**DEPENDENCY, checks=failed))
            self.assertEqual((d["state"], d["reason"], d["evidence"]),
                             ("addressing", "check_failed", [LENS_OF[check["name"]]]))
            self.assertEqual(d["admit"]["intent"], "fix-findings")
            waiting = GREEN[:i] + [dict(check, conclusion="pending")] + GREEN[i + 1:]
            d = go(facts(**DEPENDENCY, checks=waiting))
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("verifying", "awaiting_checks", "nothing"))

    def test_a_writers_thread_still_gates_a_dependency_update(self):
        d = go(facts(**DEPENDENCY, threads=[thread(kind="human", name="don-petry", severity=None)]))
        self.assertEqual((d["state"], d["reason"]), ("addressing", "human_finding"))
        f = facts(**DEPENDENCY, threads=[thread(kind="human", name="stranger", can_write=False, severity=None)])
        self.assertEqual(go(f)["state"], "converged")
        # So does a writer's request for changes; a stranger's does not.
        d = go(facts(**DEPENDENCY, reviews=[review(state="changes_requested", **MAINTAINER)]))
        self.assertEqual((d["state"], d["reason"]), ("addressing", "human_finding"))
        f = facts(**DEPENDENCY, reviews=[review(state="changes_requested", **STRANGER)])
        self.assertEqual(go(f)["state"], "converged")

    def test_a_model_lens_thread_gates_a_dependency_update(self):  # I-16: a Finding raised is never dropped
        d = go(facts(**DEPENDENCY, threads=[thread()]))
        self.assertEqual((d["state"], d["reason"]), ("addressing", "findings_open"))
        # Someone else pushes, pr-review reviews and opens a thread, then the bot recreates the branch.
        for content in ("sha256:aaaa", "sha256:bbbb"):
            d = go(facts(**DEPENDENCY, content_id=content, threads=[thread()]), REVIEWED)
            self.assertEqual((d["state"], d["reason"]), ("addressing", "findings_open"), content)

    def test_a_neutral_check_does_not_pass_a_dependency_update(self):
        for i, check in enumerate(GREEN):
            neutral = GREEN[:i] + [dict(check, conclusion="neutral")] + GREEN[i + 1:]
            d = go(facts(**DEPENDENCY, checks=neutral))
            self.assertNotEqual(d["state"], "converged", LENS_OF[check["name"]])
            self.assertNotEqual(d["outcome"], "act", LENS_OF[check["name"]])

    def test_a_dependency_update_skips_the_model_review_and_nothing_else(self):
        approved = [review()]
        cases = [({"label_events": [labelled("factory:hold")]}, None, ("held", "human_hold", "hold")),
                 ({"mergeable": None}, None, (None, "mergeable_unreadable", "defer")),
                 ({"mergeable": False}, None, ("addressing", "conflict", "admit")),
                 ({}, context(paused=True), ("converged", "paused", "defer")),
                 ({"reviews": approved}, None, ("converged", "approved", "act"))]
        for over, ctx, want in cases:
            d = go(facts(**DEPENDENCY, **over), ctx=ctx)
            self.assertEqual((d["state"], d["reason"], d["outcome"]), want, over)

    def test_each_lap_of_a_dependency_rebase_spends_an_approval_act(self):  # decisions 0003, 0007; I-8
        # The dependency bot rebases an approved update: new content, which the approval does not cover. Once the
        # checks pass, the lap ends in an approval act, which the act ceiling counts. No Run is made, so the Run ceiling
        # never bounds the lap; the act ceiling does.
        limit = LIMITS["max_acts_per_item"]
        approved = facts(**DEPENDENCY, reviews=[review()], acts_since_writer=limit - 1)
        self.assertEqual((go(approved)["reason"], go(approved)["action"]), ("approved", "enqueue"))
        rebased = dict(approved, content_id="sha256:bbbb", checks=[dict(c, conclusion="queued") for c in GREEN])
        self.assertEqual((go(rebased)["state"], go(rebased)["outcome"]), ("verifying", "nothing"))
        passed = dict(rebased, checks=GREEN)
        d = go(passed)
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["action"]),
                         ("converged", "approval_due", "act", "issue_approval"))
        # At the ceiling the lap makes no act: the update is held, and what the bot does next is its own churn.
        d = go(dict(passed, acts_since_writer=limit))
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "act_ceiling", "hold"))
        self.assertEqual(go(dict(rebased, acts_since_writer=limit))["outcome"], "nothing")


class Content(unittest.TestCase):
    def test_empty_diff_never_converges(self):  # I-24
        f = facts(diff={"files": 0, "lines": 0, "truncated": False})
        self.assertEqual(go(f, REVIEWED)["reason"], "empty_diff")

    def test_truncated_or_oversized_diff_is_held_without_a_run(self):
        self.assertEqual(go(facts(diff={"files": 9, "lines": 10, "truncated": True}))["reason"], "too_large")
        self.assertEqual(go(facts(diff={"files": 9, "lines": 99999, "truncated": False}))["reason"], "too_large")

    def test_no_model_review_before_deterministic_checks_pass(self):  # I-27
        pending = facts(checks=[dict(GREEN[0], conclusion="pending")])
        d = go(pending)
        self.assertEqual((d["outcome"], d["reason"]), ("nothing", "awaiting_checks"))
        d = go(facts())
        self.assertEqual(d["admit"], {"role": "pr-review", "intent": "review-change", "content_id": "sha256:aaaa"})

    def test_a_failed_required_check_goes_back_to_the_author(self):
        f = facts(checks=[dict(GREEN[0], conclusion="failure")] + GREEN[1:])
        d = go(f, REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("addressing", "check_failed", ["verify"]))
        self.assertEqual(d["admit"]["intent"], "fix-findings")

    def test_a_timed_out_required_check_goes_back_to_the_author(self):  # L-39
        # A hung test usually belongs to the content, and attempts bound the fixes.
        for i, check in enumerate(GREEN):
            d = go(facts(checks=with_check(i, "timed_out")), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"]),
                             ("addressing", "check_failed", [LENS_OF[check["name"]]]))
            self.assertEqual(d["admit"]["intent"], "fix-findings")
        self.assertEqual(go(facts(), REVIEWED)["action"], "issue_approval")

    def test_a_neutral_required_check_defers(self):  # I-13, I-27, L-07
        # A required Lens that gave no verdict has not judged the content. It has not passed, and it has
        # not failed: there is nothing to fix. So does a conclusion the map does not name.
        no_verdict = ("neutral", "skipped", "cancelled", "stale", "action_required", "startup_failure", "error",
                      "a_value_github_adds_later")
        for value in no_verdict:
            for i, check in enumerate(GREEN):
                for runs, reviews in (((), []), (REVIEWED, []), (REVIEWED, APPROVED)):
                    d = go(facts(checks=with_check(i, value), reviews=reviews), runs)
                    self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                     ("verifying", "check_unreadable", [LENS_OF[check["name"]]], "defer", "needs_you"),
                                     (value, LENS_OF[check["name"]]))
                    self.assertNotIn("admit", d)
                    self.assertNotIn("action", d)
        # The other side: every required check passed, so the review is admitted, then the approval issued.
        self.assertEqual(go(facts())["admit"]["intent"], "review-change")
        self.assertEqual(go(facts(), REVIEWED)["action"], "issue_approval")
        self.assertEqual(go(facts(reviews=APPROVED), REVIEWED)["action"], "enqueue")

    def test_a_queued_running_or_absent_required_check_is_waited_for(self):  # I-27
        # A normal wait is pending, not unreadable: it ends on its own.
        for value in ("queued", "in_progress", "pending", "waiting", "requested", "expected", "absent"):
            for i, check in enumerate(GREEN):
                d = go(facts(checks=with_check(i, value)), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"]),
                                 ("verifying", "awaiting_checks", [LENS_OF[check["name"]]], "nothing"),
                                 (value, check["name"]))

    def test_a_failed_check_is_read_before_an_unreadable_or_waiting_one(self):  # I-13
        # A failure is readable and decisive: whatever the check with no verdict would say, the content
        # goes back to the author. Read the other way, an ordinary failure would wait for a person.
        failed, neutral, waiting = (dict(c, conclusion=v) for c, v in zip(GREEN, ("failure", "neutral", "queued")))
        d = go(facts(checks=[failed, neutral, waiting]), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"]),
                         ("addressing", "check_failed", [LENS_OF[failed["name"]]], "admit"))
        self.assertEqual(d["admit"]["intent"], "fix-findings")
        d = go(facts(checks=[neutral, waiting]), REVIEWED)
        self.assertEqual((d["reason"], d["evidence"], d["outcome"]),
                         ("check_unreadable", [LENS_OF[neutral["name"]]], "defer"))
        d = go(facts(checks=[waiting]), REVIEWED)
        self.assertEqual((d["reason"], d["outcome"]), ("awaiting_checks", "nothing"))

    def test_a_failure_with_cancelled_or_skipped_siblings_goes_back_to_the_author(self):  # I-13
        # GitHub's fail-fast cancels the jobs beside a failure, and a job that needs the failed one is skipped.
        for sibling in ("cancelled", "skipped"):
            for i, check in enumerate(GREEN):
                checks = [dict(c, conclusion="failure" if j == i else sibling) for j, c in enumerate(GREEN)]
                d = go(facts(checks=checks), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"]),
                                 ("addressing", "check_failed", [LENS_OF[check["name"]]], "admit"),
                                 (sibling, check["name"]))
                self.assertEqual(d["admit"]["intent"], "fix-findings")

    def test_a_reading_the_kernel_does_not_know_is_unreadable(self):  # I-13
        # The configuration's schema refuses such a map. A Kernel given one anyway passes nothing on it.
        for reading in ("ignored", "", "PASSING", None, True):
            cfg = config(check_conclusions=dict(CONFIG["check_conclusions"], neutral=reading))
            d = go(facts(checks=with_check(0, "neutral")), REVIEWED, cfg=cfg)
            self.assertEqual((d["reason"], d["outcome"]), ("check_unreadable", "defer"), reading)

    def test_a_conflict_goes_back_to_the_author(self):
        d = go(facts(mergeable=False), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("addressing", "conflict", "admit"))
        self.assertEqual(d["admit"]["intent"], "fix-findings")

    def test_a_failed_check_that_is_not_required_does_not_gate(self):
        f = facts(checks=GREEN + [{"name": "template-drift", "app_id": OTHER_APP, "conclusion": "failure",
                                   "completed_at": None}])
        self.assertEqual(go(f, REVIEWED)["state"], "converged")

    def test_a_check_from_another_app_is_unreadable_for_its_lens(self):  # I-13, I-27
        # Any App with checks: write can post a check under any name. The ruleset pins `verify` to its App, and the
        # Kernel pins every required Lens: a check with a required Lens's name from any other App, or with an App id
        # that is not a whole number, makes that Lens unreadable, whatever it concludes and whatever the Lens's own App
        # says beside it. The evidence names the Lens and the App, so it is not taken for a cancelled check.
        for i, check in enumerate(GREEN):
            lens = LENS_OF[check["name"]]
            # An App no Lens is read from, another required Lens's own App, and an App that cannot be read.
            others = [OTHER_APP] + sorted({c["app_id"] for c in GREEN} - {check["app_id"]})
            for app in others + [None, True, float(check["app_id"]), str(check["app_id"]), "absent"]:
                said = "%s:from_app:%s" % (lens, app if type(app) is int else "unreadable")
                for conclusion in ("success", "failure"):
                    impostor = dict(check, app_id=app, conclusion=conclusion)
                    if app == "absent":
                        del impostor["app_id"]
                    for entries in ([impostor], [check, impostor], [impostor, check],
                                    [dict(check, conclusion="failure"), impostor]):
                        checks = GREEN[:i] + entries + GREEN[i + 1:]
                        for runs, reviews in (((), []), (REVIEWED, []), (REVIEWED, APPROVED)):
                            d = go(facts(checks=checks, reviews=reviews), runs)
                            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                             ("verifying", "check_unreadable", [said], "defer", "needs_you"),
                                             (lens, app, conclusion, len(checks)))
                            self.assertNotIn("admit", d)
                            self.assertNotIn("action", d)
        # It is read before any Lens's failure, and before a conflict: a fix Run is an action, and an unreadable fact
        # never yields one (I-13). Where another App writes under a Lens's name, a person looks first.
        impostor = dict(GREEN[0], app_id=OTHER_APP)
        said = ["%s:from_app:%d" % (LENS_OF[GREEN[0]["name"]], OTHER_APP)]
        for f in (facts(checks=[impostor, dict(GREEN[1], conclusion="failure")] + GREEN[2:]),
                  facts(checks=[impostor, dict(GREEN[1], conclusion="failure")] + GREEN[1:]),
                  facts(checks=[impostor] + GREEN[1:], mergeable=False)):
            d = go(f, REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                             ("verifying", "check_unreadable", said, "defer", "needs_you"))
        # A configuration whose App id is not a whole number reads no check as that Lens's: the schema refuses it.
        for app in (float(GREEN[0]["app_id"]), True, str(GREEN[0]["app_id"])):
            lenses = [dict(CONFIG["required_lenses"]["deterministic"][0], app_id=app)]
            cfg = config(required_lenses=dict(CONFIG["required_lenses"],
                                              deterministic=lenses + CONFIG["required_lenses"]["deterministic"][1:]))
            self.assertEqual(go(facts(), REVIEWED, cfg=cfg)["reason"], "check_unreadable", app)
        # The other side: from its own App, the Lens is read; a check from another App under a name no Lens has is
        # not read at all.
        self.assertEqual(go(facts(), REVIEWED)["action"], "issue_approval")
        other = {"name": "template-drift", "app_id": OTHER_APP, "conclusion": "failure", "completed_at": None}
        self.assertEqual(go(facts(checks=GREEN + [other]), REVIEWED)["action"], "issue_approval")

    def test_a_check_from_another_workflow_is_unreadable_for_its_lens(self):  # I-13, I-27
        # GitHub Actions is one App for every job in the repo, one a pull request adds on its own branch among them, so a
        # Lens it runs is read only from the workflow file the configuration names for it: a check under the Lens's
        # check name from another file of its own App, or with no file read, leaves it unreadable, as one from another
        # App does. A Lens no workflow runs names none, and so must its check. The evidence names the Lens and the file.
        for i, check in enumerate(GREEN):
            lens = CONFIG["required_lenses"]["deterministic"][i]
            self.assertEqual(lens["check"], check["name"])
            others = [OTHER_WORKFLOW] + sorted({c["workflow"] for c in GREEN if isinstance(c["workflow"], str)}
                                               - {check["workflow"]})
            if isinstance(check["workflow"], str):
                # The same file in another case, or from another directory, is another file; and null is no file read.
                others += [check["workflow"].upper(), "x/" + check["workflow"], None]
            for path in others + ["absent"]:
                said = "%s:from_workflow:%s" % (lens["lens"], shown(None if path == "absent" else path))
                for conclusion in ("success", "failure"):
                    impostor = dict(check, workflow=path, conclusion=conclusion)
                    if path == "absent":
                        del impostor["workflow"]
                    for entries in ([impostor], [check, impostor], [impostor, check],
                                    [dict(check, conclusion="failure"), impostor]):
                        checks = GREEN[:i] + entries + GREEN[i + 1:]
                        for runs, reviews in (((), []), (REVIEWED, []), (REVIEWED, APPROVED)):
                            d = go(facts(checks=checks, reviews=reviews), runs)
                            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                             ("verifying", "check_unreadable", [said], "defer", "needs_you"),
                                             (lens["lens"], path, conclusion, len(checks)))
                            self.assertNotIn("admit", d)
                            self.assertNotIn("action", d)
        # It is read before any Lens's failure, and before a conflict, as another App's check is.
        actions = next(c for c in GREEN if isinstance(c["workflow"], str))
        i = GREEN.index(actions)
        impostor = dict(actions, workflow=OTHER_WORKFLOW)
        said = ["%s:from_workflow:%s" % (LENS_OF[actions["name"]], OTHER_WORKFLOW)]
        rest = GREEN[:i] + GREEN[i + 1:]
        failing = [dict(rest[0], conclusion="failure")] + rest[1:]
        for f in (facts(checks=[impostor] + failing), facts(checks=[impostor, actions] + failing),
                  facts(checks=[impostor] + GREEN, mergeable=False)):
            d = go(f, REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                             ("verifying", "check_unreadable", said, "defer", "needs_you"))
        # From another App, it is shown as another App's, whatever file it names.
        d = go(facts(checks=[dict(actions, app_id=OTHER_APP, workflow=OTHER_WORKFLOW)] + GREEN), REVIEWED)
        self.assertEqual(d["evidence"], ["%s:from_app:%d" % (LENS_OF[actions["name"]], OTHER_APP)])
        # A configuration that names another file reads none of these checks as its Lens's.
        lenses = [dict(lens, workflow=OTHER_WORKFLOW) if lens["check"] == actions["name"] else lens
                  for lens in CONFIG["required_lenses"]["deterministic"]]
        cfg = config(required_lenses=dict(CONFIG["required_lenses"], deterministic=lenses))
        d = go(facts(), REVIEWED, cfg=cfg)
        self.assertEqual((d["reason"], d["evidence"]),
                         ("check_unreadable", ["%s:from_workflow:%s" % (LENS_OF[actions["name"]], actions["workflow"])]))
        # The other side: from its own App and its own file, the Lens is read, every one of its checks; and a job under a
        # name no Lens has, from any file, is not read at all.
        self.assertEqual(go(facts(), REVIEWED)["action"], "issue_approval")
        self.assertEqual(go(facts(checks=[dict(actions)] + GREEN), REVIEWED)["action"], "issue_approval")
        other = dict(actions, name="template-drift", workflow=OTHER_WORKFLOW, conclusion="failure")
        self.assertEqual(go(facts(checks=GREEN + [other]), REVIEWED)["action"], "issue_approval")

    def test_a_workflow_path_is_shown_only_in_its_form(self):  # I-13
        # The evidence shows the path of another workflow file only in the form the configuration names one in, and no
        # longer than the configuration's limit: anything else could carry text from outside into a Decision, a
        # look-alike of a Lens's own file or a control character that turns the text round, and is shown `unreadable`.
        # Whatever it shows, the check is not the Lens's.
        actions = next(c for c in GREEN if isinstance(c["workflow"], str))
        lens = LENS_OF[actions["name"]]
        limit = LIMITS["max_path_length"]
        longest = ".github/workflows/" + "a" * (limit - len(".github/workflows/.yml")) + ".yml"
        self.assertEqual(len(longest), limit)
        for path in (OTHER_WORKFLOW, ".github/workflows/x.yaml", ".github/workflows/a_b-c.1.yml", longest):
            d = go(facts(checks=GREEN + [dict(actions, workflow=path)]), REVIEWED)
            self.assertEqual((d["reason"], d["evidence"]), ("check_unreadable", ["%s:from_workflow:%s" % (lens, path)]),
                             path)
        unshown = ["", " ", ".github/workflows/verify .yml", ".github/workflows/v\u0435rify.yml",
                   "\u202e.github/workflows/verify.yml", ".github/workflows/verify.yml\u200b",
                   ".github/workflows/" + "a" * 5000 + ".yml", longest[:-4] + "a.yml",
                   "dynamic/github-code-scanning/codeql", "dynamic/workflows/x.yml", ".github/workflows_a.yml",
                   ".github/workflows/sub/x.yml", "../.github/workflows/x.yml",
                   ".github/workflows/x.yml\n", ".github/workflows/.yml", ".github/workflows/x.YML",
                   ".github/workflows/x.json", "x/" + actions["workflow"], actions["workflow"].upper(), 1, [], {}]
        for path in unshown:
            self.assertEqual(shown(path), "unreadable", path)
            d = go(facts(checks=GREEN + [dict(actions, workflow=path)]), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"]),
                             ("verifying", "check_unreadable", ["%s:from_workflow:unreadable" % lens], "defer"), path)

    def test_every_check_a_lens_reports_from_its_own_app_is_read(self):  # I-13, I-27
        # GitHub can hold several checks with one name from one App: two workflows with the same job name, say. Each
        # is read, never the last alone. Any that fails fails the Lens; failing none, any that gave no verdict leaves
        # it unreadable; then any still running is a wait. The Lens passes only when every one of them passes.
        for i, check in enumerate(GREEN):
            lens = LENS_OF[check["name"]]
            for other, reason in (("failure", "check_failed"), ("timed_out", "check_failed"),
                                  ("neutral", "check_unreadable"), ("skipped", "check_unreadable"),
                                  ("in_progress", "awaiting_checks"), ("queued", "awaiting_checks")):
                for pair in ((check, dict(check, conclusion=other)), (dict(check, conclusion=other), check)):
                    d = go(facts(checks=GREEN[:i] + list(pair) + GREEN[i + 1:]), REVIEWED)
                    self.assertEqual((d["reason"], d["evidence"]), (reason, [lens]),
                                     (lens, other, pair[0]["conclusion"]))
            # A failure beside an entry with no verdict, from the same App, is still a failure.
            for pair in ((dict(check, conclusion="failure"), dict(check, conclusion="cancelled")),
                         (dict(check, conclusion="cancelled"), dict(check, conclusion="failure"))):
                d = go(facts(checks=GREEN[:i] + list(pair) + GREEN[i + 1:]), REVIEWED)
                self.assertEqual((d["reason"], d["evidence"]), ("check_failed", [lens]), lens)
            # The other side: every one of them passing, the Lens passes.
            d = go(facts(checks=GREEN[:i] + [check, dict(check)] + GREEN[i + 1:]), REVIEWED)
            self.assertEqual(d["action"], "issue_approval", lens)

    def test_a_check_is_matched_to_a_lens_by_its_check_name_alone(self):  # I-13, I-27
        # The facts carry each check run under the name GitHub gives it, and a Lens is the check the configuration
        # names for it, exactly. A job that its own App runs under the Lens's own name, or under the check's name in
        # another case or with space around it, is some other check: it neither passes the Lens nor makes it unreadable.
        for i, lens in enumerate(CONFIG["required_lenses"]["deterministic"]):
            others = [dict(GREEN[i], name=lens["lens"]), dict(GREEN[i], name=lens["check"].upper()),
                      dict(GREEN[i], name=" %s" % lens["check"])]
            for other in [o for o in others if o["name"] != lens["check"]]:
                for wrong_app in (False, True):
                    check = dict(other, app_id=OTHER_APP) if wrong_app else other
                    d = go(facts(checks=GREEN[:i] + [check] + GREEN[i + 1:]), REVIEWED)
                    self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"]),
                                     ("verifying", "awaiting_checks", [lens["lens"]], "nothing"), check)
                    d = go(facts(checks=GREEN[:i] + [check, dict(GREEN[i], conclusion="failure")] + GREEN[i + 1:]),
                           REVIEWED)
                    self.assertEqual((d["reason"], d["evidence"]), ("check_failed", [lens["lens"]]), check)
            # The other side: the check under its exact name passes the Lens.
            self.assertEqual(go(facts(checks=GREEN[:i] + [GREEN[i]] + GREEN[i + 1:]), REVIEWED)["action"],
                             "issue_approval", lens["lens"])

    def test_a_review_of_other_content_does_not_count(self):  # I-11, the other way round
        d = go(facts(content_id="sha256:bbbb"), REVIEWED)
        self.assertEqual(d["admit"]["intent"], "review-change")

    def test_unchanged_content_causes_no_new_review(self):  # I-11
        self.assertNotEqual(go(facts(), REVIEWED)["outcome"], "admit")


class Convergence(unittest.TestCase):
    def test_required_lens_major_finding_gates(self):
        d = go(facts(threads=[thread()]), REVIEWED)
        self.assertEqual((d["state"], d["admit"]["role"]), ("addressing", "dev-lead"))

    def test_minor_finding_and_unrequired_lens_do_not_gate(self):
        f = facts(threads=[thread(severity="minor"), thread(tid="T2", name="coderabbit", can_write=False)])
        self.assertEqual(go(f, REVIEWED)["state"], "converged")

    def test_a_minor_security_finding_gates(self):  # FR-33, I-16: severity is never how a security defect is merged
        # A required Lens's `security` Finding gates at any severity, a dependency update's too. One with no severity
        # cannot be read at all (test_a_required_lens_thread_that_cannot_be_read_defers).
        for severity in ("minor", "info"):
            for over in ({}, DEPENDENCY):
                f = facts(**over, threads=[thread(severity=severity, category="security")])
                d = go(f, REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"]), ("addressing", "findings_open", ["T1"]),
                                 (severity, over))
                self.assertEqual(d["admit"]["intent"], "fix-findings")
        # The other side: a Finding of any other category gates by its severity alone.
        for category in ("functional", "architecture", "mechanical", "uncategorised"):
            f = facts(threads=[thread(severity="minor", category=category)])
            self.assertEqual(go(f, REVIEWED)["state"], "converged", category)

    def test_a_security_finding_from_a_lens_that_is_not_required_does_not_gate(self):  # FR-32
        # A Lens outside the required set gates only when a required Lens adopts its Finding, whatever the category.
        for severity in ("blocking", "minor"):
            f = facts(threads=[thread(name="coderabbit", can_write=False, severity=severity, category="security")])
            self.assertEqual(go(f, REVIEWED)["state"], "converged", severity)
        # Adopted, it is the required Lens's own, and gates.
        adopted = [thread(name="coderabbit", can_write=False, severity="minor", category="security"),
                   thread(tid="T2", severity="minor", category="security")]
        d = go(facts(threads=adopted), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("addressing", "findings_open", ["T2"]))

    def test_a_required_lens_thread_that_cannot_be_read_defers(self):  # I-13, FR-33
        # Whether a required Lens's thread gates is read from its category and severity, and a security Finding gates
        # at any severity. Either missing, null, or a word the Kernel does not know could hide one: nothing converges,
        # nothing is admitted, and the item is the Maintainer's to see, as for a review that cannot be read.
        unreadable = [{"category": None}, {"category": "Security"}, {"category": "security "}, {"category": "secret"},
                      {"severity": None}, {"severity": "Minor"}, {"severity": "critical"},
                      {"category": None, "severity": None}, "category", "severity"]
        for bad in unreadable:
            th = thread(severity="minor", category="security")
            if isinstance(bad, str):
                del th[bad]
            else:
                th.update(bad)
            for reviews in ([], APPROVED):
                d = go(facts(reviews=reviews, threads=[thread(tid="T0", severity="minor"), th]), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                 (None, "thread_unreadable", ["T1"], "defer", "needs_you"), (bad, reviews))
            # It is read after what needs no thread, a Hold among them, and before a model review is admitted.
            self.assertEqual(go(facts(label_events=[labelled("factory:hold")], threads=[th]))["reason"], "human_hold", bad)
            self.assertEqual(go(facts(threads=[th]))["reason"], "thread_unreadable", bad)
            # A model Lens's thread is read whatever the class, as it gates whatever the class.
            self.assertEqual(go(facts(**DEPENDENCY, threads=[th]))["reason"], "thread_unreadable", bad)
        # The other side: every category and severity the schema names can be read, and one resolved is not read.
        for category in ("functional", "security", "architecture", "delivery", "reliability", "requirements",
                         "mechanical", "uncategorised", "human"):
            for severity in ("blocking", "major", "minor", "info"):
                d = go(facts(threads=[thread(severity=severity, category=category)]), REVIEWED)
                self.assertNotEqual(d["reason"], "thread_unreadable", (category, severity))
        resolved = thread(severity=None, category=None, resolved=True)
        self.assertEqual(go(facts(threads=[resolved]), REVIEWED)["state"], "converged")
        # A Lens that is not required gates nothing, and may write both only as prose; a person's thread has no
        # severity, and gates whatever it says.
        advisory = thread(name="coderabbit", can_write=False, severity=None, category=None)
        self.assertEqual(go(facts(threads=[advisory]), REVIEWED)["state"], "converged")
        person = thread(kind="human", name="don-petry", severity=None, category=None)
        self.assertEqual(go(facts(threads=[person]), REVIEWED)["reason"], "human_finding")

    def test_after_the_author_it_is_the_owners_turn(self):
        runs = REVIEWED + [run(role="dev-lead", intent="fix-findings", at="2026-10-11T12:20:00Z", name="r2")]
        d = go(facts(threads=[thread()]), runs)
        self.assertEqual((d["state"], d["admit"]["intent"]), ("adjudicating", "adjudicate-findings"))

    def test_an_answer_that_is_new_content_still_goes_to_the_owner(self):
        # Found by the simulator: the fix pushes new content, so "the last Run on this content"
        # is the re-review, and the thread was never judged.
        runs = [run(),
                run(role="dev-lead", intent="fix-findings", at="2026-10-11T12:20:00Z", name="r2"),
                run(content="sha256:bbbb", at="2026-10-11T12:30:00Z", name="r3")]
        d = go(facts(content_id="sha256:bbbb", threads=[thread()]), runs)
        self.assertEqual((d["state"], d["admit"]["intent"]), ("adjudicating", "adjudicate-findings"))

    def test_a_rejected_answer_returns_to_the_author(self):
        runs = REVIEWED + [run(role="dev-lead", intent="fix-findings", at="2026-10-11T12:20:00Z", name="r2"),
                           run(intent="adjudicate-findings", at="2026-10-11T12:25:00Z", name="r3")]
        d = go(facts(threads=[thread()]), runs)
        self.assertEqual((d["state"], d["admit"]["role"]), ("addressing", "dev-lead"))

    def test_an_answered_human_thread_waits_for_that_person(self):
        runs = REVIEWED + [run(role="dev-lead", intent="fix-findings", at="2026-10-11T12:20:00Z", name="r2")]
        d = go(facts(threads=[thread(kind="human", name="don-petry", severity=None)]), runs)
        self.assertEqual((d["outcome"], d["reason"], d["attention"]), ("nothing", "awaiting_human", "needs_you"))

    def test_approval_is_issued_only_when_converged(self):  # I-9
        d = go(facts(), REVIEWED)
        self.assertEqual((d["outcome"], d["action"], d["content_id"]), ("act", "issue_approval", "sha256:aaaa"))

    def test_approved_content_is_enqueued(self):
        rv = [review()]
        self.assertEqual(go(facts(reviews=rv), REVIEWED)["action"], "enqueue")

    def test_an_approval_of_other_content_does_not_stand(self):
        rv = [review(commit="c0", content="sha256:0000")]
        self.assertEqual(go(facts(reviews=rv), REVIEWED)["action"], "issue_approval")

    def test_approver_is_never_the_author_or_last_pusher(self):  # I-26
        for who in ("author", "last_pusher"):
            d = go(facts(**{who: "donpetry-bot"}), REVIEWED)
            self.assertEqual((d["outcome"], d["reason"]), ("hold", "approver_is_author_or_last_pusher"))


class Acceptance(unittest.TestCase):
    """Convergence's fourth condition (§4.2 item 4, §4.8, I-31): where the item has an acceptance contract, every
    criterion has passing evidence on this content. The facts carry the contract's criteria by id and each result read
    for one, with the content it was given on; an item with no contract carries none, and converges as it always did."""

    BOTH = [evidence("AC-1"), evidence("AC-2")]

    def test_with_a_contract_it_converges_only_when_every_criterion_has_passing_evidence(self):  # I-31
        # No evidence yet, or for one criterion of two: a wait for the evidence, like a Lens that has not reported. It
        # needs no Run, and is the Maintainer's to see only once it has waited past its limit.
        for given, lacking in (([], ["AC-1", "AC-2"]), ([evidence("AC-1")], ["AC-2"]), ([evidence("AC-2")], ["AC-1"])):
            d = go(facts(acceptance=contract(results=given)), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                             ("verifying", "acceptance_evidence_missing", lacking, "nothing", "review"), given)
            # An approval that already stands does not pass over it.
            d = go(facts(acceptance=contract(results=given), reviews=APPROVED), REVIEWED)
            self.assertEqual((d["reason"], d["outcome"]), ("acceptance_evidence_missing", "nothing"), given)
        # The other side: every criterion passing on this content converges, and the approval is issued, then enqueued.
        d = go(facts(acceptance=contract(results=self.BOTH)), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["action"]),
                         ("converged", "approval_due", "act", "issue_approval"))
        d = go(facts(acceptance=contract(results=self.BOTH), reviews=APPROVED), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["action"]), ("converged", "approved", "enqueue"))
        # One criterion, passing, is a whole contract too.
        d = go(facts(acceptance=contract(["AC-7"], [evidence("AC-7")])), REVIEWED)
        self.assertEqual(d["reason"], "approval_due")

    def test_evidence_for_other_content_does_not_count(self):  # I-31
        # Evidence given on earlier content says nothing of this content, passing or failing.
        old = "sha256:0000"
        for given, lacking in (([evidence("AC-1", content=old), evidence("AC-2", content=old)], ["AC-1", "AC-2"]),
                               ([evidence("AC-1"), evidence("AC-2", content=old)], ["AC-2"]),
                               ([evidence("AC-1"), evidence("AC-2", "failing", old)], ["AC-2"])):
            d = go(facts(acceptance=contract(results=given), reviews=APPROVED), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"]),
                             ("verifying", "acceptance_evidence_missing", lacking, "nothing"), given)
        # The other side: a failure on earlier content does not hold content that passes now.
        given = self.BOTH + [evidence("AC-1", "failing", old)]
        self.assertEqual(go(facts(acceptance=contract(results=given)), REVIEWED)["reason"], "approval_due")

    def test_a_failing_criterion_goes_back_to_the_author(self):  # I-31
        # A failing result on this content is readable and decisive, as a failed check is: the author's fix Run.
        for given in ([evidence("AC-1", "failing"), evidence("AC-2")], [evidence("AC-1", "failing")],
                      # Two results for one criterion on this content that disagree: the failure is read.
                      self.BOTH + [evidence("AC-1", "failing")], [evidence("AC-1", "failing")] + self.BOTH):
            d = go(facts(acceptance=contract(results=given)), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                             ("addressing", "acceptance_failed", ["AC-1"], "admit", "failed"), given)
            self.assertEqual(d["admit"], {"role": "dev-lead", "intent": "fix-findings", "content_id": "sha256:aaaa"})
        # A failure is read before a criterion still waiting for its evidence.
        d = go(facts(acceptance=contract(results=[evidence("AC-2", "failing")])), REVIEWED)
        self.assertEqual((d["reason"], d["evidence"]), ("acceptance_failed", ["AC-2"]))
        # Every criterion that failed is named, in the contract's order.
        d = go(facts(acceptance=contract(["AC-1", "AC-2", "AC-3"], [evidence("AC-3", "failing"), evidence("AC-2"),
                                                                     evidence("AC-1", "failing")])), REVIEWED)
        self.assertEqual((d["reason"], d["evidence"]), ("acceptance_failed", ["AC-1", "AC-3"]))
        # The fix Run is a Run like any other: a Run in progress holds the item.
        busy = [run(role="dev-lead", intent="fix-findings", status="in_progress", at=at(20), name="r2")]
        d = go(facts(acceptance=contract(results=[evidence("AC-1", "failing")])), REVIEWED + busy)
        self.assertEqual((d["reason"], d["outcome"], d["attention"]), ("acceptance_failed", "nothing", "working"))

    def test_an_item_with_no_contract_converges_as_it_did(self):  # I-31, the other way round
        # No contract, as the facts carry it: the fourth condition asks nothing, and every other reading is unchanged.
        for runs, reason in (((), "awaiting_review"), (REVIEWED, "approval_due")):
            self.assertEqual(go(facts(acceptance=None), runs)["reason"], reason)
        self.assertEqual(go(facts(acceptance=None, reviews=APPROVED), REVIEWED)["action"], "enqueue")

    def test_acceptance_is_read_after_every_other_condition_of_convergence(self):  # §4.2
        # The first three conditions are read first, whatever the evidence says: a failed check, a check or a review not
        # yet reported and an open gate each give their own reading. The contract's own identity, whether a person
        # approved it, unchanged, and whether it can be read, comes before them all, and admits nothing
        # (test_no_run_is_admitted_on_a_contract_not_approved, test_an_unreadable_contract_admits_nothing); its evidence
        # comes here.
        for acceptance in (contract(), contract(results=[evidence("AC-1", "failing")])):
            cases = [(facts(acceptance=acceptance, checks=with_check(0, "failure")), (), "check_failed"),
                     (facts(acceptance=acceptance, checks=with_check(0, "pending")), (), "awaiting_checks"),
                     (facts(acceptance=acceptance), (), "awaiting_review"),
                     (facts(acceptance=acceptance, threads=[thread()]), REVIEWED, "findings_open"),
                     (facts(acceptance=acceptance, label_events=[labelled("factory:hold")]), REVIEWED, "human_hold")]
            for f, runs, reason in cases:
                self.assertEqual(go(f, runs)["reason"], reason, (acceptance, reason))
        # And before the Hold for an approver who is the author: that Hold is about the approval, which is issued only
        # on what has converged.
        d = go(facts(acceptance=contract(), last_pusher=CONFIG["approver"]), REVIEWED)
        self.assertEqual(d["reason"], "acceptance_evidence_missing")
        d = go(facts(acceptance=contract(results=self.BOTH), last_pusher=CONFIG["approver"]), REVIEWED)
        self.assertEqual(d["reason"], "approver_is_author_or_last_pusher")

    def test_unreadable_acceptance_never_converges(self):  # I-13, I-31
        # A contract, an approval of one, or a result on this content, that the Kernel cannot read could hide a criterion
        # with no passing evidence, or a contract no person approved: it defers, for the Maintainer, since a port that
        # misreads does not mend itself. A fact read from outside is never given a default, so facts that say nothing of
        # a contract are not "no contract", and a contract that says nothing of its approval or its head is not one
        # unapproved or deleted.
        def bad(**over):
            return dict(contract(results=self.BOTH), **over)

        def without(name):
            return {k: v for k, v in bad().items() if k != name}

        def approval(results=None, **over):
            return dict(contract(results=self.BOTH if results is None else results),
                        approved=dict(contract()["approved"], **over))

        def criteria(*listed):
            # Each with AC-1 passing alone, so that nothing but the criteria is unreadable.
            return approval([evidence("AC-1")], criteria=[{"id": "AC-1", "kind": "test"}] + list(listed))

        def by(**over):
            return approval(by=dict(MAINTAINER, **over))

        unreadable = {
            "missing": "missing", "not an object": ["AC-1"], "an empty object": {},
            "with no results": without("results"), "with no head": without("head"),
            "with no approval": without("approved"),
            "an approval that is no object": bad(approved=["AC-1"]),
            "an approval with no criteria": approval([], criteria=[]),
            "an approval's criteria that are no list": approval(criteria="AC-1"),
            "an approval with no list of criteria": {"approved": {"digest": DIGEST, "by": dict(MAINTAINER)},
                                                     "head": DIGEST, "results": []},
            "a criterion named twice": criteria({"id": "AC-1", "kind": "test"}),
            "a criterion named twice, of another kind": criteria({"id": "AC-1", "kind": "human"}),
            "a criterion that is no object": criteria("AC-2"),
            "a criterion that is no name": criteria({"id": None, "kind": "test"}),
            "an empty name": criteria({"id": "", "kind": "test"}),
            "a criterion in another form": criteria({"id": "ac-2", "kind": "test"}),
            "a criterion with no number": criteria({"id": "AC-", "kind": "test"}),
            "a criterion's number in other digits": criteria({"id": "AC-2a", "kind": "test"}),
            "a criterion with no id": criteria({"kind": "test"}),
            "a criterion with no kind": criteria({"id": "AC-2"}),
            "a kind the Kernel does not know": criteria({"id": "AC-2", "kind": "manual"}),
            "a kind in capitals": criteria({"id": "AC-2", "kind": "Test"}),
            "a kind that is no word": criteria({"id": "AC-2", "kind": None}),
            "an approval with no digest": {"approved": {"by": dict(MAINTAINER), "criteria": [{"id": "AC-1",
                                                                                            "kind": "test"}]},
                                           "head": DIGEST, "results": []},
            "an empty digest": approval(digest=""), "a digest with no hash": approval(digest="sha256:"),
            "a digest in capitals": approval(digest=DIGEST.upper().replace("SHA256", "sha256")),
            "a digest of another kind": approval(digest="md5:" + DIGEST[len("sha256:"):]),
            "a digest cut short": approval(digest=DIGEST[:-1]), "a digest of a few digits": approval(digest="sha256:c0de"),
            "a digest padded": approval(digest=DIGEST + "0"),
            "an approval with no commit": bad(approved={k: v for k, v in contract()["approved"].items() if k != "commit"}),
            "an approval on an empty commit": approval(commit=""), "an approval on no commit": approval(commit=None),
            "a digest that is no text": approval(digest=None),
            "an approval by a name alone": approval(by=MAINTAINER["name"]),
            "an approval by nobody": approval(by=None),
            "an approval by a kind the Kernel does not know": by(kind="bot"),
            "an approval by a person named like an App's bot": by(name="don-petry[bot]"),
            "an approval by the machine user under another name": by(kind="machine_user"),
            "an approval whose access is not true or false": by(can_write="yes"),
            "an empty head": bad(head=""), "a head with no hash": bad(head="sha256:"),
            "a head in capitals": bad(head=DIGEST.upper().replace("SHA256", "sha256")),
            "a head that is no text": bad(head=1), "a head cut short": bad(head=DIGEST[:-1]),
            "a head of a few digits": bad(head="sha256:c0de"), "a head padded": bad(head=DIGEST + "0"),
            "results that are no list": bad(results=None),
            "a result that is no object": bad(results=self.BOTH + ["AC-1"]),
            "a result for a criterion the contract does not name": bad(results=self.BOTH + [evidence("AC-9")]),
            "a result naming no criterion": bad(results=self.BOTH + [evidence(None)]),
            "a result naming an empty criterion": bad(results=self.BOTH + [evidence("", content="sha256:0000")]),
            "a result naming a criterion that is no name": bad(results=self.BOTH + [evidence(["AC-1"])]),
            "a result in words": bad(results=self.BOTH + [evidence("AC-1", "skipped")]),
            "a result in capitals": bad(results=[evidence("AC-1", "PASSING"), evidence("AC-2")]),
            "no result": bad(results=self.BOTH + [{"criterion": "AC-1", "content_id": "sha256:aaaa",
                                                   "check": dict(REPORTER)}]),
            "no check": bad(results=self.BOTH + [{"criterion": "AC-1", "content_id": "sha256:aaaa",
                                                  "result": "passing"}]),
            "a check that is no object": bad(results=self.BOTH + [dict(evidence("AC-1"), check="verify")]),
            "no content": bad(results=self.BOTH + [{"criterion": "AC-1", "result": "passing", "check": dict(REPORTER)}]),
            "content that is no hash": bad(results=self.BOTH + [evidence("AC-1", content=None)]),
            # A content id in any other form than the schema's could be this content misread: it is no earlier one.
            "an empty content id": bad(results=self.BOTH + [evidence("AC-1", "failing", content="")]),
            "a content id with no hash": bad(results=self.BOTH + [evidence("AC-1", "failing", content="sha256:")]),
            "a content id in capitals": bad(results=self.BOTH + [evidence("AC-1", "failing", content="sha256:AAAA")]),
            "a content id of another kind": bad(results=self.BOTH + [evidence("AC-1", "failing", content="md5:aaaa")]),
        }
        for name, acceptance in unreadable.items():
            for reviews in ([], APPROVED):
                f = facts(acceptance=acceptance, reviews=reviews)
                if acceptance == "missing":
                    del f["acceptance"]
                d = go(f, REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                 (None, "acceptance_unreadable", [], "defer", "needs_you"), name)
                self.assertNotIn("action", d)
        # The other side: the same contract read whole converges, and so does one whose approval is a colleague's.
        self.assertEqual(go(facts(acceptance=bad()), REVIEWED)["reason"], "approval_due")
        self.assertEqual(go(facts(acceptance=approval(by=COLLEAGUE)), REVIEWED)["reason"], "approval_due")

    def test_only_this_contents_results_are_judged(self):  # I-31, the ruling on #17
        # A result on earlier content is not read past its content and criterion ids: a criterion the contract no longer
        # lists, as after a waiver or a revision, or a word the Kernel does not know, there makes nothing unreadable.
        old = "sha256:0000"
        # Nor is who reported it: a result there from another App, or with no check at all, says nothing of this content.
        for earlier in ([evidence("AC-2", "failing", old)], [evidence("AC-9", "passing", old)],
                        [evidence("AC-1", "neutral", old)], [{"criterion": "AC-2", "content_id": old}],
                        [evidence("AC-1", content=old, check=dict(REPORTER, app_id=OTHER_APP))],
                        [{"criterion": "AC-1", "content_id": old, "result": "passing"}]):
            d = go(facts(acceptance=contract(["AC-1"], [evidence("AC-1")] + earlier)), REVIEWED)
            self.assertEqual((d["state"], d["reason"]), ("converged", "approval_due"), earlier)
        # The other side: the same result on this content makes the contract unreadable.
        for now in ([evidence("AC-2", "failing")], [evidence("AC-9")], [evidence("AC-1", "neutral")]):
            d = go(facts(acceptance=contract(["AC-1"], [evidence("AC-1")] + now)), REVIEWED)
            self.assertEqual((d["state"], d["reason"]), (None, "acceptance_unreadable"), now)

    def test_a_contract_read_short_is_incomplete(self):  # I-13, I-20, the ruling on #17
        # Whether the contract, or that there is none, was read in full is `complete.acceptance`, read with the other
        # flags: a read short defers as facts_incomplete, a wait that needs no person. No contract read short is not
        # "no contract": it converges nothing. Only a full read confirms that there is none.
        short = dict(facts()["complete"], acceptance=False)
        for acceptance in (None, contract(), contract(results=self.BOTH)):
            for reviews in ([], APPROVED):
                d = go(facts(acceptance=acceptance, reviews=reviews, complete=short), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                 (None, "facts_incomplete", ["acceptance"], "defer", "none"), acceptance)
        # The other side: read in full, no contract converges, and so does a contract with every criterion passing.
        for acceptance in (None, contract(results=self.BOTH)):
            self.assertEqual(go(facts(acceptance=acceptance), REVIEWED)["reason"], "approval_due")


    def test_a_contract_no_person_approved_is_a_hold(self):  # I-29, decision 0007
        # The head is the author's: the contract that counts is the one a person approved, at one commit. None approved,
        # or one approved by anyone who is not a person, is a Hold for the Maintainer, whatever its evidence says, and it
        # takes a queued item out. The machine user's approval, or an App's, approves no contract, as with an admission.
        for by in (None, MACHINE, AUTHOR_APP, REVIEWER_APP, ADVISORY, STRANGER):
            for given in ([], self.BOTH, [evidence("AC-1", "failing")]):
                d = go(facts(acceptance=contract(results=given, by=by)), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                 ("held", "contract_not_approved", [], "hold", "needs_you"), (by, given))
            d = go(facts(acceptance=contract(results=self.BOTH, by=by), queue=True, reviews=APPROVED), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["action"]),
                             ("held", "contract_not_approved", "act", "dequeue"), by)
        # Nor does a person's approving review of the content, or of the commit, where the facts name no approval at all.
        for reviews in ([review(kind="human", name=MAINTAINER["name"])],
                        [review(kind="human", name=MAINTAINER["name"], content="sha256:c0c0", commit=COMMIT)]):
            d = go(facts(acceptance=contract(results=self.BOTH, by=None), reviews=reviews, **AGENT), REVIEWED)
            self.assertEqual((d["state"], d["reason"]), ("held", "contract_not_approved"), reviews)
        # Nor does a person's review under the same name: the approval is read as the approver's, of the kind it names.
        for by in (REVIEWER_APP, ADVISORY, STRANGER):
            namesake = review(kind="human", name=by["name"], content="sha256:c0c0", commit=COMMIT)
            d = go(facts(acceptance=contract(results=self.BOTH, by=by), reviews=[namesake], armed=False), REVIEWED)
            self.assertEqual((d["state"], d["reason"]), ("held", "contract_not_approved"), by)
        # The other side: a person approved it, the Maintainer or a colleague, and it converges, then stays queued.
        for by in (MAINTAINER, COLLEAGUE):
            self.assertEqual(go(facts(acceptance=contract(results=self.BOTH, by=by)), REVIEWED)["reason"],
                             "approval_due", by)
            d = go(facts(acceptance=contract(results=self.BOTH, by=by), queue=True, reviews=APPROVED), REVIEWED)
            self.assertEqual((d["state"], d["reason"]), ("queued", "in_merge_queue"), by)

    def test_a_contract_changed_since_its_approval_is_a_hold(self):  # I-29, I-30
        # A digest covers the contract and every path it protects, so a push that edits a test the contract names changes
        # it. A head whose digest differs from the one approved is a Hold until a person approves again, and so is a head
        # with no contract at all: a deleted contract is a change, never "no contract".
        for head in ("sha256:" + "0" * 64, DIGEST[:-1] + "f", None):
            for given in ([], self.BOTH, [evidence("AC-1", "failing")]):
                d = go(facts(acceptance=contract(results=given, head=head)), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                 ("held", "contract_changed", [], "hold", "needs_you"), (head, given))
            d = go(facts(acceptance=contract(results=self.BOTH, head=head), queue=True, reviews=APPROVED), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["action"]),
                             ("held", "contract_changed", "act", "dequeue"), head)
            # A contract no person approved is read first: nothing was approved for it to differ from.
            d = go(facts(acceptance=contract(results=self.BOTH, by=None, head=head)), REVIEWED)
            self.assertEqual(d["reason"], "contract_not_approved", head)
        # The other side: the head's contract is the one approved, and it converges.
        self.assertEqual(go(facts(acceptance=contract(results=self.BOTH, head=DIGEST)), REVIEWED)["reason"],
                         "approval_due")

    def test_no_run_is_admitted_on_a_contract_not_approved(self):  # I-29
        # Every implementing Run is barred until a person has approved the contract, and while the head differs from it.
        # A conflict, a failed check, an open Finding, a failing criterion and a wait for the model review each admit a
        # Run otherwise; under either Hold, each holds instead. Read after a foreign check, which admits nothing either.
        person = thread(kind="human", name=COLLEAGUE["name"], severity=None)
        cases = [(dict(mergeable=False), REVIEWED, "conflict"),
                 (dict(checks=with_check(0, "failure")), (), "check_failed"),
                 (dict(threads=[thread()]), REVIEWED, "findings_open"),
                 (dict(threads=[person]), REVIEWED, "human_finding"),
                 ({}, (), "awaiting_review")]
        for over, runs, reason in cases:
            for given in ([], [evidence("AC-1", "failing")]):
                d = go(facts(acceptance=contract(results=given), **over), runs)
                self.assertEqual((d["reason"], d["outcome"]), (reason, "admit"), (reason, given))
                for acceptance, hold in ((contract(results=given, by=None), "contract_not_approved"),
                                         (contract(results=given, head=None), "contract_changed")):
                    d = go(facts(acceptance=acceptance, **over), runs)
                    self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", hold, "hold"), (reason, given))
                    self.assertNotIn("admit", d)
        # A failing criterion itself: the author's fix Run only on the contract a person approved, unchanged.
        failing = [evidence("AC-1", "failing")]
        d = go(facts(acceptance=contract(results=failing)), REVIEWED)
        self.assertEqual((d["reason"], d["admit"]["intent"]), ("acceptance_failed", "fix-findings"))
        for acceptance in (contract(results=failing, by=None), contract(results=failing, head="sha256:" + "0" * 64)):
            self.assertEqual(go(facts(acceptance=acceptance), REVIEWED)["outcome"], "hold")
        # A check another App posted under a Lens's name is read first: it admits nothing either, and only a push clears it.
        d = go(facts(acceptance=contract(by=None), checks=GREEN + [dict(GREEN[0], app_id=OTHER_APP)]))
        self.assertEqual((d["reason"], d["outcome"]), ("check_unreadable", "defer"))

    def test_a_result_counts_only_from_the_reporter_its_kind_names(self):  # I-10, FR-30
        # Any App with checks: write can report a result, the implementing Role's own among them, and GitHub Actions runs
        # any job a pull request adds. A result counts only from the check of the Lens the configuration names for its
        # criterion's kind, read as that Lens's check is: its name, from its App and its workflow file. Any other is
        # unreadable, read before any failure, and the Decision says which App or file it came from, as for a check.
        scan = next(lens for lens in CONFIG["required_lenses"]["deterministic"] if lens["lens"] == "secret-scan")
        codeql = next(lens for lens in CONFIG["required_lenses"]["deterministic"] if lens["workflow"] is None)
        cases = [("AC-1:from_app:%d" % OTHER_APP, dict(REPORTER, app_id=OTHER_APP)),
                 ("AC-1:from_app:%d" % codeql["app_id"],
                  {"name": codeql["check"], "app_id": codeql["app_id"], "workflow": None}),
                 ("AC-1:from_app:unreadable", dict(REPORTER, app_id=str(REPORTER["app_id"]))),
                 ("AC-1:from_app:unreadable", {"name": REPORTER["name"], "workflow": REPORTER["workflow"]}),
                 ("AC-1:from_workflow:%s" % OTHER_WORKFLOW, dict(REPORTER, workflow=OTHER_WORKFLOW)),
                 ("AC-1:from_workflow:%s" % scan["workflow"],
                  {"name": scan["check"], "app_id": scan["app_id"], "workflow": scan["workflow"]}),
                 ("AC-1:from_workflow:unreadable", dict(REPORTER, workflow=None)),
                 ("AC-1:from_workflow:unreadable", dict(REPORTER, workflow=REPORTER["workflow"] + "\n")),
                 ("AC-1:from_workflow:unreadable", {"name": REPORTER["name"], "app_id": REPORTER["app_id"]}),
                 ("AC-1:from_another_check", dict(REPORTER, name="mutants")),
                 ("AC-1:from_another_check", dict(REPORTER, name=REPORTER["name"].upper())),
                 ("AC-1:from_another_check", dict(REPORTER, name=REPORTER["name"] + " ")),
                 ("AC-1:from_another_check", {"app_id": REPORTER["app_id"], "workflow": REPORTER["workflow"]})]
        for shown, check in cases:
            for given in ([evidence("AC-1", check=check), evidence("AC-2")],
                          # beside a pass from its reporter
                          self.BOTH + [evidence("AC-1", check=check)],
                          # failing, and beside a failure from its reporter: read before any failure
                          [evidence("AC-1", "failing", check=check), evidence("AC-2")],
                          [evidence("AC-1", "failing"), evidence("AC-1", check=check), evidence("AC-2")]):
                for reviews in ([], APPROVED):
                    d = go(facts(acceptance=contract(results=given), reviews=reviews), REVIEWED)
                    self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                     (None, "acceptance_unreadable", [shown], "defer", "needs_you"), (check, given))
                    self.assertNotIn("action", d)
            # On a queued item it takes it out.
            d = go(facts(acceptance=contract(results=self.BOTH + [evidence("AC-1", check=check)]), queue=True,
                         reviews=APPROVED), REVIEWED)
            self.assertEqual((d["reason"], d["evidence"], d["action"]), ("acceptance_unreadable", [shown], "dequeue"))
        # Each such result is named once, in the order given, and so is each criterion's.
        other = dict(REPORTER, app_id=OTHER_APP)
        given = [evidence("AC-2", check=other), evidence("AC-1", check=dict(REPORTER, workflow=OTHER_WORKFLOW)),
                 evidence("AC-2", "failing", check=other)]
        d = go(facts(acceptance=contract(results=given)), REVIEWED)
        self.assertEqual(d["evidence"], ["AC-2:from_app:%d" % OTHER_APP, "AC-1:from_workflow:%s" % OTHER_WORKFLOW])
        # The other side: from its reporter a result counts, passing or failing.
        self.assertEqual(go(facts(acceptance=contract(results=self.BOTH)), REVIEWED)["reason"], "approval_due")
        d = go(facts(acceptance=contract(results=[evidence("AC-1", "failing"), evidence("AC-2")])), REVIEWED)
        self.assertEqual((d["reason"], d["evidence"]), ("acceptance_failed", ["AC-1"]))

    def test_a_kind_with_no_reporter_cannot_pass(self):  # I-10
        # No Lens reports a criterion of kind scenario, mutation, static or role yet: a result for one, from any check,
        # is unreadable, so such a contract converges nothing until the configuration names its reporter.
        for kind in ("scenario", "mutation", "static", "role"):
            for check in (REPORTER, dict(REPORTER, app_id=OTHER_APP)):
                for result in ("passing", "failing"):
                    given = [evidence("AC-1", result, check=check), evidence("AC-2")]
                    d = go(facts(acceptance=contract([("AC-1", kind), "AC-2"], given)), REVIEWED)
                    self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                     (None, "acceptance_unreadable", ["AC-1:no_reporter"], "defer", "needs_you"),
                                     (kind, check, result))
            # With no result, it waits for one, as any criterion does.
            d = go(facts(acceptance=contract([("AC-1", kind), "AC-2"], [evidence("AC-2")])), REVIEWED)
            self.assertEqual((d["reason"], d["evidence"]), ("acceptance_evidence_missing", ["AC-1"]), kind)
            # The other side: once the configuration names a Lens for the kind, a result from its check counts.
            given = [evidence("AC-1", check=REPORTER), evidence("AC-2")]
            named = config(acceptance_reporters=dict(CONFIG["acceptance_reporters"], **{kind: "verify"}))
            d = go(facts(acceptance=contract([("AC-1", kind), "AC-2"], given)), REVIEWED, cfg=named)
            self.assertEqual(d["reason"], "approval_due", kind)
            # A name that is no required deterministic Lens's reports nothing.
            nobody = config(acceptance_reporters=dict(CONFIG["acceptance_reporters"], **{kind: "pr-review"}))
            d = go(facts(acceptance=contract([("AC-1", kind), "AC-2"], given)), REVIEWED, cfg=nobody)
            self.assertEqual((d["reason"], d["evidence"]), ("acceptance_unreadable", ["AC-1:no_reporter"]), kind)

    def test_a_human_criterion_is_passed_only_by_a_persons_approval_of_this_content(self):  # §3.13, I-10
        # One approving review by a person, of this content, confirms every human criterion there (the Maintainer's ruling
        # of 2026-10-17). It stands until a person dismisses it: an App's dismissal ends nothing a person did (L-17), as
        # it ends no request for changes, and leaves the contract's approval standing too. The review approves no
        # content: the approver's approval still does.
        def f(reviews, given=(evidence("AC-2"),), **over):
            return facts(acceptance=contract([("AC-1", "human"), "AC-2", ("AC-3", "human")], given), reviews=reviews,
                         **dict(AGENT, **over))

        person = review(kind="human", name=MAINTAINER["name"])
        for who in (person, review(kind="human", name=COLLEAGUE["name"]), dismissed(person, REVIEWER_APP, "approved"),
                    dismissed(person, AUTHOR_APP, "approved"), dismissed(person, MACHINE, "approved")):
            d = go(f([who]), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["action"]),
                             ("converged", "approval_due", "act", "issue_approval"), who)
            self.assertEqual(go(f([who] + APPROVED), REVIEWED)["action"], "enqueue")
        # Not passed by the machine user's approval, an App's, a Lens's or a stranger's; by a person's of other content;
        # by a person's approval a person dismissed, or a request for changes or a comment an App dismissed.
        others = ([], APPROVED, [review(kind="app", name=AGENT["author"])], [review(kind="lens", name="pr-review")],
                  [review(kind="human", name="stranger", can_write=False)],
                  [review(kind="human", name=MAINTAINER["name"], content="sha256:0000")],
                  [dismissed(person, MAINTAINER, "approved")], [dismissed(person, COLLEAGUE, "approved")],
                  [dismissed(review("commented", kind="human", name=MAINTAINER["name"]), REVIEWER_APP, "commented")],
                  [review("commented", kind="human", name=MAINTAINER["name"])])
        for reviews in others:
            d = go(f(reviews), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"]),
                             ("verifying", "acceptance_evidence_missing", ["AC-1", "AC-3"], "nothing"), reviews)
        # A check's result for it is unreadable, from any check, even beside a person's approval; and whatever the
        # configuration names for the kind, only a person passes it.
        for check in (REPORTER, dict(REPORTER, app_id=OTHER_APP)):
            given = [evidence("AC-1", check=check), evidence("AC-2")]
            for cfg in (None, config(acceptance_reporters=dict(CONFIG["acceptance_reporters"], human="verify"))):
                d = go(f([person], given), REVIEWED, cfg=cfg)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"]),
                                 (None, "acceptance_unreadable", ["AC-1:no_reporter"], "defer"), check)
        # It never fails: a person objects with a request for changes, which gates as it always did.
        d = go(f([review("changes_requested", kind="human", name=MAINTAINER["name"])]), REVIEWED)
        self.assertEqual((d["reason"], d["outcome"]), ("human_finding", "admit"))

    def test_an_unreadable_contract_admits_nothing(self):  # I-13
        # A contract whose approval or criteria cannot be read is read early, as an unreadable fact is, so it admits no
        # Run, not even for a conflict, a failed check or an open Finding: it waits for the Maintainer.
        def approval(**over):
            return dict(contract(), approved=dict(contract()["approved"], **over))

        unread = {"an approval by the machine user under another name": approval(by=dict(MAINTAINER,
                                                                                          kind="machine_user")),
                  "an approval by someone named like an App's bot": approval(by=dict(COLLEAGUE, name="x[bot]")),
                  "an approval by an actor of no kind": approval(by={"name": "don-petry", "can_write": True}),
                  "a kind the Kernel does not know": approval(criteria=[{"id": "AC-1", "kind": "manual"}]),
                  "a kind in capitals": approval(criteria=[{"id": "AC-1", "kind": "HUMAN"}]),
                  "a criterion named twice": approval(criteria=[{"id": "AC-1", "kind": "test"},
                                                                {"id": "AC-1", "kind": "human"}])}
        cases = [(dict(mergeable=False), REVIEWED), (dict(checks=with_check(0, "failure")), ()),
                 (dict(threads=[thread()]), REVIEWED), ({}, ()), ({}, REVIEWED)]
        for name, acceptance in unread.items():
            for over, runs in cases:
                d = go(facts(acceptance=acceptance, **over), runs)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                 (None, "acceptance_unreadable", [], "defer", "needs_you"), (name, over))
        # Each Hold, too, is the Maintainer's to see, and never stale however long it waits.
        later_on = later(NOW, 10 * CONFIG["lifecycle"]["stale_after_minutes"]["held"])
        for acceptance, hold in ((contract(by=None), "contract_not_approved"), (contract(head=None),
                                                                                "contract_changed")):
            d = go(facts(acceptance=acceptance), REVIEWED, context(passes_since="2026-10-11T12:00:00Z"), now=later_on)
            self.assertEqual((d["reason"], d["attention"]), (hold, "needs_you"))
        # The other side: read whole, the same contract admits the Run each case asks for.
        for over, runs in cases[:3]:
            self.assertEqual(go(facts(acceptance=contract(), **over), runs)["outcome"], "admit", over)

    def test_an_approval_of_the_contract_is_a_review_github_holds(self):  # I-29, decision 0007
        # The facts' word that a person approved the contract is held to a review GitHub holds: by that person, with
        # write access, approving, on the commit the contract was approved at, and not dismissed by a person. Without
        # one, no person approved anything, and the contract is not approved.
        approval = review(kind="human", name=MAINTAINER["name"], content="sha256:c0c0", commit=COMMIT)
        unheld = {"no review at all": [],
                  "a review on another commit": [dict(approval, commit="c9")],
                  "a review by another person": [dict(approval, by=dict(COLLEAGUE))],
                  "a review that only comments": [dict(approval, state="commented")],
                  "a request for changes": [dict(approval, state="changes_requested")],
                  "a review a person dismissed": [dismissed(approval, MAINTAINER, "approved")],
                  "a review a colleague dismissed": [dismissed(approval, COLLEAGUE, "approved")],
                  "a review its author can no longer write as": [dict(approval, by=dict(MAINTAINER, can_write=False))],
                  "the machine user's approval on that commit": [review(commit=COMMIT)]}
        for name, reviews in unheld.items():
            for given in ([], self.BOTH):
                d = go(facts(acceptance=contract(results=given), reviews=reviews, armed=False), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                                 ("held", "contract_not_approved", "hold", "needs_you"), name)
        # The other side: that review, standing or dismissed by an App, as GitHub dismisses one as stale on a push.
        for reviews in ([approval], [dismissed(approval, REVIEWER_APP, "approved")],
                        [dismissed(approval, AUTHOR_APP, "approved")], [dict(approval, state="commented"), approval]):
            d = go(facts(acceptance=contract(results=self.BOTH), reviews=reviews, armed=False), REVIEWED)
            self.assertEqual(d["reason"], "approval_due", reviews)

    def test_every_field_of_a_review_the_kernel_reads_is_read_whole(self):  # I-13
        # The commit and content a review was given on, and who dismissed it and what it was, are read for the gate, for
        # a person's approval of the contract and for a human criterion. A review missing any of them, a person's or
        # anyone's, dismissed or not, defers for the Maintainer: never a crash, and never read as absent.
        person = review(kind="human", name=COLLEAGUE["name"])
        for rv in (person, review("commented", kind="human", name=COLLEAGUE["name"]), review()):
            for field in ("commit", "content_id", "dismissed_by", "dismissed_from"):
                broken = {k: v for k, v in rv.items() if k != field}
                for acceptance in (None, contract(results=self.BOTH),
                                   contract([("AC-1", "human"), "AC-2"], [evidence("AC-2")])):
                    d = go(facts(acceptance=acceptance, reviews=[broken], **AGENT), REVIEWED)
                    self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                                     (None, "review_unreadable", "defer", "needs_you"), (rv["state"], field))
            for field, value in (("commit", ""), ("commit", None), ("content_id", "sha256:"), ("content_id", None)):
                d = go(facts(reviews=[dict(rv, **{field: value})], **AGENT), REVIEWED)
                self.assertEqual(d["reason"], "review_unreadable", (field, value))
        # The other side: read whole, each is read as it always was.
        self.assertEqual(go(facts(reviews=[person], **AGENT), REVIEWED)["reason"], "approval_due")

    def test_a_contract_whose_reporters_cannot_be_read_defers(self):  # I-13
        # Which Lens reports each kind is read from the configuration: missing, or of another shape, it could make a
        # result count from anyone, so an item with a contract defers for the Maintainer. One with none needs none.
        for reporters in ("missing", None, [], "verify", {"test": 1}, {"test": ["verify"]}):
            cfg = config()
            if reporters == "missing":
                del cfg["acceptance_reporters"]
            else:
                cfg["acceptance_reporters"] = reporters
            for over, runs in ((dict(mergeable=False), REVIEWED), ({}, REVIEWED), ({}, ())):
                d = go(facts(acceptance=contract(results=self.BOTH), **over), runs, cfg=cfg)
                self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                                 (None, "acceptance_reporters_unreadable", "defer", "needs_you"), reporters)
            # The other side: an item with no contract reads no reporter.
            self.assertEqual(go(facts(acceptance=None), REVIEWED, cfg=cfg)["reason"], "approval_due", reporters)
        # A kind the configuration leaves out has no reporter.
        cfg = config(acceptance_reporters={})
        d = go(facts(acceptance=contract(results=self.BOTH)), REVIEWED, cfg=cfg)
        self.assertEqual((d["reason"], d["evidence"]), ("acceptance_unreadable", ["AC-1:no_reporter", "AC-2:no_reporter"]))

    def test_a_digest_is_a_whole_sha256(self):  # I-29, I-30
        # A digest of the approved contract, or of the head's, is `sha256:` and 64 lower-case hexadecimal digits. Cut
        # short, padded or in capitals, either could pass for the one approved, so the contract cannot be read.
        for digest in (DIGEST[:-1], DIGEST + "c", "sha256:c0de", DIGEST.replace("c", "C"), DIGEST[:-1] + "g"):
            for acceptance in (contract(results=self.BOTH, head=digest),
                               dict(contract(results=self.BOTH, head=digest),
                                    approved=dict(contract()["approved"], digest=digest))):
                d = go(facts(acceptance=acceptance), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["outcome"]), (None, "acceptance_unreadable", "defer"),
                                 digest)
        # The other side: a whole one is read, and compared whole.
        self.assertEqual(go(facts(acceptance=contract(results=self.BOTH)), REVIEWED)["reason"], "approval_due")
        other = DIGEST[:-1] + "f"
        self.assertEqual(go(facts(acceptance=contract(results=self.BOTH, head=other)), REVIEWED)["reason"],
                         "contract_changed")


class AReviewThatReported(unittest.TestCase):
    """A required model Lens has reported on this content only through a Run of its review of it that succeeded
    (decision 0029). A Run whose Result left a criterion of its rubric uncovered failed, by a fault of the item."""

    def test_a_review_run_that_failed_has_not_reported(self):  # I-37
        for conclusion in ("failure", "timed_out", "cancelled"):
            failed = [run(conclusion=conclusion, outcome="item", name="u0")]
            d = go(facts(), failed)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d.get("admit")),
                             ("verifying", "awaiting_review", "admit", REVIEW_IT), conclusion)
            # A later review of the same content that succeeded has reported.
            d = go(facts(), failed + [run(at=at(20), name="r2")])
            self.assertEqual((d["outcome"], d.get("action")), ("act", "issue_approval"), conclusion)
        # Each such Run is an attempt: at the limit since a writer acted, the item is held with their ids.
        failed = [run(conclusion="failure", outcome="item", at=at(10 + i), name="u%d" % i)
                  for i in range(LIMITS["max_attempts"])]
        d = go(facts(), failed)
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"], d["evidence"]),
                         ("held", "attempts_exhausted", "hold", "needs_you", [r["run"] for r in failed]))
        self.assertEqual(go(facts(), failed[1:]).get("admit"), REVIEW_IT)
        # One that failed with no outcome has not reported either. It is no attempt, so the Run ceiling bounds it.
        unread = [run(conclusion="failure", outcome=None, at=at(10 + i), name="n%d" % i)
                  for i in range(LIMITS["max_runs_per_item"])]
        d = go(facts(), unread[:LIMITS["max_attempts"]])
        self.assertEqual((d["state"], d["reason"], d["outcome"], d.get("admit")),
                         ("verifying", "awaiting_review", "admit", REVIEW_IT))
        d = go(facts(), unread)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "run_ceiling", "hold"))

    def test_a_review_that_succeeded_with_a_fault_is_unreadable(self):  # I-13
        # A Run that succeeded and names whose fault its failure was contradicts itself: no report is read from it,
        # beside a review that reported or not, and it takes a queued item out.
        for outcome in ("item", "capacity", "environment", "superseded"):
            odd = run(outcome=outcome, at=at(20), name="r9")
            for runs in ([odd], REVIEWED + [odd]):
                d = go(facts(), runs)
                self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"], d["evidence"]),
                                 (None, "run_unreadable", "defer", "needs_you", ["r9"]), (outcome, len(runs)))
            d = go(facts(queue=True, reviews=APPROVED), REVIEWED + [odd])
            self.assertEqual((d["state"], d["reason"], d["outcome"], d.get("action")),
                             (None, "run_unreadable", "act", "dequeue"), outcome)
            # One on other content, or another Intent's, is not this review's.
            for other in (dict(odd, content_id="sha256:bbbb"), dict(odd, intent="issue-approval")):
                d = go(facts(), REVIEWED + [other])
                self.assertEqual((d["outcome"], d.get("action")), ("act", "issue_approval"), (outcome, other["intent"]))
        # Nor is one by a Role no required Lens is, the author's among them, or on an update no model Lens reviews.
        for role in (CONFIG["author_role"], "someone-else"):
            d = go(facts(), REVIEWED + [run(role=role, outcome="item", at=at(20), name="r9")])
            self.assertEqual((d["outcome"], d.get("action")), ("act", "issue_approval"), role)
        d = go(facts(reviews=APPROVED, **DEPENDENCY), [run(outcome="item", at=at(20), name="r9")])
        self.assertEqual((d["outcome"], d.get("action")), ("act", "enqueue"))
        # Nor is one not yet completed, which holds the item as any Run does, nor one that failed by a fault.
        d = go(facts(), REVIEWED + [dict(run(outcome="item", at=at(20), name="r9"), status="queued")])
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                         ("converged", "approval_due", "nothing", "working"))
        d = go(facts(), REVIEWED + [run(conclusion="failure", outcome="environment", at=at(20), name="r9")])
        self.assertEqual((d["outcome"], d.get("action")), ("act", "issue_approval"))
        # The other side: a review that succeeded with no fault named has reported.
        d = go(facts(), REVIEWED)
        self.assertEqual((d["outcome"], d.get("action")), ("act", "issue_approval"))


class Ceilings(unittest.TestCase):
    def test_one_writer_per_item(self):  # I-2
        for status in ("in_progress", "queued"):     # a Run waiting for a runner holds the item too
            d = go(facts(), [run(status=status, conclusion=None)])
            self.assertEqual((d["outcome"], d["attention"]), ("nothing", "working"), status)

    def test_item_faults_exhaust_attempts(self):
        failures = [run(conclusion="failure", outcome="item", at="2026-10-11T12:1%d:00Z" % i, name="f%d" % i) for i in range(3)]
        d = go(facts(), failures)
        self.assertEqual((d["outcome"], d["reason"]), ("hold", "attempts_exhausted"))

    def test_capacity_and_environment_faults_are_not_attempts(self):  # I-23
        for kind in ("capacity", "environment", "superseded"):
            failures = [run(conclusion="failure", outcome=kind, at="2026-10-11T12:1%d:00Z" % i, name="f%d" % i) for i in range(3)]
            self.assertEqual(go(facts(), failures)["outcome"], "admit", kind)

    def test_a_writers_action_grants_a_fresh_allowance(self):  # I-28
        failures = [run(conclusion="failure", outcome="item", at="2026-10-11T12:1%d:00Z" % i, name="f%d" % i) for i in range(3)]
        d = go(facts(last_writer_action_at="2026-10-11T12:30:00Z"), failures)
        self.assertEqual(d["outcome"], "admit")

    def test_with_no_writers_action_every_run_counts(self):  # I-8, I-28
        # No person with write access has acted on the item yet: no allowance was renewed, so every Run on it counts
        # toward its attempts and the Run ceiling, and none is passed over.
        none = facts(last_writer_action_at=None)
        d = go(none, REVIEWED + approvals(LIMITS["max_runs_per_item"] + 5, outcome="environment"))
        self.assertEqual((d["state"], d["outcome"], d["reason"]), ("held", "hold", "run_ceiling"))
        d = go(none, REVIEWED + approvals(LIMITS["max_attempts"]))
        self.assertEqual((d["outcome"], d["reason"]), ("hold", "attempts_exhausted"))
        failures = [run(conclusion="failure", outcome="item", at=at(10 + i), name="f%d" % i)
                    for i in range(LIMITS["max_attempts"])]
        d = go(none, failures)
        self.assertEqual((d["outcome"], d["reason"]), ("hold", "attempts_exhausted"))
        # Below each ceiling, the next Run or approval goes ahead.
        self.assertEqual(go(none, failures[1:])["outcome"], "admit")
        d = go(none, REVIEWED + approvals(LIMITS["max_attempts"] - 1))
        self.assertEqual((d["outcome"], d["action"]), ("act", "issue_approval"))

    def test_spent_attempts_hold_the_item_while_a_run_waits(self):  # I-8, I-12, I-23
        # The simulator's seed 297: a review superseded, three that failed by a fault of the item, and a fourth admitted
        # on a list read one Run short. No Run in flight lowers a count, so the item is held while it waits, and a
        # superseded Run is no attempt.
        r0 = run(conclusion="failure", outcome="superseded", at=at(10), name="r0")
        failed = [run(conclusion="failure", outcome="item", at=at(11 + i), name="r%d" % (i + 1)) for i in range(3)]
        for status in ("queued", "in_progress"):
            r4 = dict(run(status="in_progress", at=at(14), name="r4"), status=status)
            d = go(facts(), [r0] + failed + [r4])
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"], d["evidence"]),
                             ("held", "attempts_exhausted", "hold", "needs_you", ["r1", "r2", "r3"]), status)
            # The other side: without r3 the attempts are not spent, and r0 is none of them. The Run waits.
            d = go(facts(), [r0] + failed[:2] + [r4])
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                             ("verifying", "awaiting_review", "nothing", "working"), status)
        # When the lane supersedes r4, as `apply` does on a held item, the evidence is still r1 to r3, and it stays held.
        d = go(facts(), [r0] + failed + [run(conclusion="failure", outcome="superseded", at=at(14), name="r4")])
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["evidence"]),
                         ("held", "attempts_exhausted", "hold", ["r1", "r2", "r3"]))
        # A converged item's approval attempts hold it the same way, whatever Run waits.
        waiting = [dict(run(intent="issue-approval", status="in_progress", at=at(40), name="a9"), status="queued")]
        failed = approvals(LIMITS["max_attempts"])
        d = go(facts(), REVIEWED + failed + waiting)
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["evidence"]),
                         ("held", "attempts_exhausted", "hold", [r["run"] for r in failed]))
        d = go(facts(), REVIEWED + failed[1:] + waiting)
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                         ("converged", "approval_due", "nothing", "working"))

    def test_a_spent_count_holds_whatever_would_defer_while_a_run_waits(self):  # I-8, I-12
        # A Pause, one that cannot be read, or an unreadable count of acts does not hide a count already spent while a
        # Run is in flight: the ceilings are asked alone.
        r0 = run(conclusion="failure", outcome="superseded", at=at(10), name="r0")
        failed = [run(conclusion="failure", outcome="item", at=at(11 + i), name="r%d" % (i + 1)) for i in range(3)]
        approvals_failed = approvals(LIMITS["max_attempts"])
        waiting = [dict(run(intent="issue-approval", status="in_progress", at=at(40), name="a9"), status="queued")]
        for status in ("queued", "in_progress"):
            r4 = dict(run(status="in_progress", at=at(14), name="r4"), status=status)
            for paused in (True, None):
                d = go(facts(), [r0] + failed + [r4], ctx=context(paused=paused))
                self.assertEqual((d["state"], d["reason"], d["outcome"], d["evidence"]),
                                 ("held", "attempts_exhausted", "hold", ["r1", "r2", "r3"]), (status, paused))
                d = go(facts(), REVIEWED + approvals_failed + waiting, ctx=context(paused=paused))
                self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "attempts_exhausted", "hold"), paused)
                # The other side: with the count not spent, the Run in flight keeps the item working, as it did.
                d = go(facts(), [r0] + failed[:2] + [r4], ctx=context(paused=paused))
                self.assertEqual((d["state"], d["outcome"], d["attention"]), ("verifying", "nothing", "working"))
        d = go(facts(acts_since_writer=None), REVIEWED + approvals_failed + waiting)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "attempts_exhausted", "hold"))
        d = go(facts(acts_since_writer=None), REVIEWED + approvals_failed[1:] + waiting)
        self.assertEqual((d["state"], d["outcome"], d["attention"]), ("converged", "nothing", "working"))

    def test_an_act_waits_for_a_run_in_flight(self):  # I-12
        # The act ceiling counts acts, not Runs, and stops only an act: none is decided while a Run waits.
        ceiling = facts(acts_since_writer=LIMITS["max_acts_per_item"])
        waiting = dict(run(intent="adjudicate-findings", status="in_progress", at=at(40), name="o9"), status="queued")
        d = go(ceiling, REVIEWED + [waiting])
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                         ("converged", "approval_due", "nothing", "working"))
        d = go(ceiling, REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "act_ceiling", "hold"))
        # An approval that landed is enqueued whatever failed before, so failed approvals do not hold it either.
        landed = facts(reviews=APPROVED)
        d = go(landed, REVIEWED + approvals(LIMITS["max_attempts"]) + [waiting])
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                         ("converged", "approved", "nothing", "working"))

    def test_spent_rounds_hold_the_item_while_a_run_waits(self):  # I-14
        # An item whose owner's rulings are at `max_rounds` is held while another Run is queued or in progress, as with
        # none in flight. One round short, the Run in flight keeps it working.
        rounds = LIMITS["max_rounds"]
        laps = [r for i in range(rounds) for r in (run(intent="adjudicate-findings", at=at(20 + 2 * i), name="o%d" % i),
                                                   run(role="dev-lead", intent="fix-findings", at=at(21 + 2 * i),
                                                       name="a%d" % i))]
        short = [r for r in laps if r["run"] not in ("o%d" % (rounds - 1), "a%d" % (rounds - 1))]
        for status in ("queued", "in_progress"):
            waiting = dict(run(intent="adjudicate-findings", status="in_progress", at=at(40), name="o9"), status=status)
            d = go(facts(threads=[thread()]), REVIEWED + laps + [waiting])
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                             ("held", "max_rounds", "hold", "needs_you"), status)
            d = go(facts(threads=[thread()]), REVIEWED + short + [waiting])
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                             ("adjudicating", "proposals_await_owner", "nothing", "working"), status)
        # The other side of the Run in flight: with none, the same rounds hold it and one short admits a ruling.
        self.assertEqual(go(facts(threads=[thread()]), REVIEWED + laps)["reason"], "max_rounds")
        self.assertEqual(go(facts(threads=[thread()]), REVIEWED + short)["admit"]["intent"], "adjudicate-findings")

    def test_a_run_in_flight_is_held_by_the_completed_runs_alone(self):  # I-8
        # The Run ceiling counts the Runs that completed: the tenth Run, admitted with nine completed, is not held at
        # the ceiling it was admitted under. Ten completed hold the item while another waits.
        ceiling = LIMITS["max_runs_per_item"]
        spent = [run(conclusion="failure", outcome="environment", at=at(10 + i), name="e%d" % i) for i in range(ceiling)]
        waiting = dict(run(status="in_progress", at=at(40), name="w"), status="queued")
        d = go(facts(), spent[1:] + [waiting])
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                         ("verifying", "awaiting_review", "nothing", "working"))
        d = go(facts(), spent + [waiting])
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                         ("held", "run_ceiling", "hold", "needs_you"))

    def test_under_a_pause_spent_attempts_hold_the_item_with_no_run_in_flight(self):  # I-8, I-23, decision 0003
        # Seed 297's Runs with none in flight. A Hold of the brakes is a reading, not an act, and a Pause leaves each
        # item where it is: the count already spent holds it under a Pause, or one that cannot be read, as without one.
        r0 = run(conclusion="failure", outcome="superseded", at=at(10), name="r0")
        failed = [run(conclusion="failure", outcome="item", at=at(11 + i), name="r%d" % (i + 1)) for i in range(3)]
        for paused, why in ((True, "paused"), (None, "pause_unreadable")):
            d = go(facts(), [r0] + failed, ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"], d["evidence"]),
                             ("held", "attempts_exhausted", "hold", "needs_you", ["r1", "r2", "r3"]), paused)
            # The other side: without r3 nothing is spent, and the Pause defers the review.
            d = go(facts(), [r0] + failed[:2], ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("verifying", why, "defer"), paused)

    def test_under_a_pause_spent_rounds_hold_the_item(self):  # I-14, decision 0003
        rounds = LIMITS["max_rounds"]
        laps = [r for i in range(rounds) for r in (run(intent="adjudicate-findings", at=at(20 + 2 * i), name="o%d" % i),
                                                   run(role="dev-lead", intent="fix-findings", at=at(21 + 2 * i),
                                                       name="a%d" % i))]
        short = [r for r in laps if r["run"] not in ("o%d" % (rounds - 1), "a%d" % (rounds - 1))]
        for paused, why in ((True, "paused"), (None, "pause_unreadable")):
            d = go(facts(threads=[thread()]), REVIEWED + laps, ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                             ("held", "max_rounds", "hold", "needs_you"), paused)
            d = go(facts(threads=[thread()]), REVIEWED + short, ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("adjudicating", why, "defer"), paused)

    def test_under_a_pause_a_spent_run_ceiling_holds_the_item(self):  # I-8, FR-39, decision 0003
        ceiling = LIMITS["max_runs_per_item"]
        fixes = [run(role="dev-lead", intent="fix-findings", at=at(10 + i), name="f%d" % i) for i in range(ceiling)]
        for paused, why in ((True, "paused"), (None, "pause_unreadable")):
            d = go(facts(), fixes, ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                             ("held", "run_ceiling", "hold", "needs_you"), paused)
            d = go(facts(), fixes[1:], ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("verifying", why, "defer"), paused)

    def test_under_a_pause_spent_approvals_hold_the_item(self):  # I-8, I-28, decision 0003
        failed = approvals(LIMITS["max_attempts"])
        for paused, why in ((True, "paused"), (None, "pause_unreadable")):
            d = go(facts(), REVIEWED + failed, ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"], d["evidence"]),
                             ("held", "attempts_exhausted", "hold", "needs_you", [r["run"] for r in failed]), paused)
            d = go(facts(), REVIEWED + failed[1:], ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("converged", why, "defer"), paused)

    def test_under_a_pause_the_act_ceiling_holds_the_item(self):  # I-8, FR-17, decision 0003
        limit = LIMITS["max_acts_per_item"]
        for paused, why in ((True, "paused"), (None, "pause_unreadable")):
            d = go(facts(acts_since_writer=limit), REVIEWED, ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                             ("held", "act_ceiling", "hold", "needs_you"), paused)
            d = go(facts(acts_since_writer=limit - 1), REVIEWED, ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("converged", why, "defer"), paused)
            # A count of acts that cannot be read holds nothing: the Pause defers first, and without one the count does.
            d = go(facts(acts_since_writer=None), REVIEWED, ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("converged", why, "defer"), paused)
        d = go(facts(acts_since_writer=None), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("converged", "acts_unreadable", "defer"))

    def test_the_run_ceiling_holds_no_item_that_wants_no_run(self):  # FR-39, I-13, I-23
        # The Run ceiling bounds model spend. A required check that gave no verdict wants no Run: the item defers for a
        # person, who is called for that cause alone. Once a Run is wanted again, the ceiling holds before any is
        # admitted. An approved item's enqueue spends no model, and goes ahead.
        ceiling = LIMITS["max_runs_per_item"]
        spent = [run(conclusion="failure", outcome="environment", at=at(10 + i), name="e%d" % i) for i in range(ceiling)]
        neutral, failing = with_check(1, "neutral"), with_check(1, "failure")
        for paused in (False, True, None):
            d = go(facts(checks=neutral), spent, ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                             ("verifying", "check_unreadable", "defer", "needs_you"), paused)
            d = go(facts(checks=failing), spent, ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "run_ceiling", "hold"), paused)
        d = go(facts(reviews=APPROVED), REVIEWED + spent)
        self.assertEqual((d["state"], d["reason"], d["outcome"], d.get("action")),
                         ("converged", "approved", "act", "enqueue"))

    def test_the_run_ceiling_holds_no_item_that_wants_no_run_while_a_run_waits(self):  # FR-39, I-2
        ceiling = LIMITS["max_runs_per_item"]
        spent = [run(conclusion="failure", outcome="environment", at=at(10 + i), name="e%d" % i) for i in range(ceiling)]
        waiting = dict(run(status="in_progress", at=at(40), name="w"), status="queued")
        neutral, failing = with_check(1, "neutral"), with_check(1, "failure")
        for paused in (False, True, None):
            d = go(facts(checks=neutral), spent + [waiting], ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                             ("verifying", "check_unreadable", "nothing", "working"), paused)
            d = go(facts(checks=failing), spent + [waiting], ctx=context(paused=paused))
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "run_ceiling", "hold"), paused)
        d = go(facts(reviews=APPROVED), REVIEWED + spent + [waiting])
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                         ("converged", "approved", "nothing", "working"))

    def test_an_approval_that_does_not_land_is_bounded(self):  # I-8, I-28
        failed = approvals(LIMITS["max_attempts"])
        d = go(facts(), REVIEWED + failed)
        self.assertEqual((d["state"], d["outcome"], d["reason"], d["attention"], d["evidence"]),
                         ("held", "hold", "attempts_exhausted", "needs_you", [r["run"] for r in failed]))
        d = go(facts(), REVIEWED + failed[1:])
        self.assertEqual((d["outcome"], d["action"]), ("act", "issue_approval"))
        # A writer's action grants a fresh allowance.
        d = go(facts(last_writer_action_at=at(40)), REVIEWED + failed)
        self.assertEqual((d["outcome"], d["action"]), ("act", "issue_approval"))
        # An approval Run in progress holds the item, as any Run does (I-2).
        d = go(facts(), REVIEWED + [run(intent="issue-approval", status="in_progress", at=at(20), name="a0")])
        self.assertEqual((d["outcome"], d["attention"]), ("nothing", "working"))

    def test_an_approval_that_fails_for_capacity_or_environment_is_not_an_attempt(self):  # I-23
        for kind in ("capacity", "environment", "superseded"):
            d = go(facts(), REVIEWED + approvals(LIMITS["max_attempts"], outcome=kind))
            self.assertEqual((d["outcome"], d["action"]), ("act", "issue_approval"), kind)

    def test_an_approval_that_keeps_failing_for_the_environment_is_bounded(self):  # I-8
        # Not an attempt, and never landed, so not an act: only the Run ceiling can bound it.
        ceiling = LIMITS["max_runs_per_item"]
        for kind in ("environment", "capacity", "superseded", None):
            d = go(facts(), REVIEWED + approvals(ceiling - 1, outcome=kind))
            self.assertEqual((d["state"], d["outcome"], d["reason"], d["attention"]),
                             ("held", "hold", "run_ceiling", "needs_you"), kind)
            d = go(facts(), REVIEWED + approvals(ceiling - 2, outcome=kind))
            self.assertEqual((d["outcome"], d["action"]), ("act", "issue_approval"), kind)
            # A writer's action renews the allowance, as for any Run.
            d = go(facts(last_writer_action_at=at(40)), REVIEWED + approvals(ceiling - 1, outcome=kind))
            self.assertEqual((d["outcome"], d["action"]), ("act", "issue_approval"), kind)

    def test_a_failed_model_run_is_not_an_approval_attempt(self):
        fixes = [run(role="dev-lead", intent="fix-findings", conclusion="failure", outcome="item",
                     at=at(20 + i), name="f%d" % i) for i in range(LIMITS["max_attempts"])]
        d = go(facts(), REVIEWED + fixes)
        self.assertEqual((d["outcome"], d["action"]), ("act", "issue_approval"))

    def test_an_approval_that_landed_is_enqueued_whatever_failed_before(self):
        d = go(facts(reviews=APPROVED), REVIEWED + approvals(LIMITS["max_attempts"]))
        self.assertEqual((d["outcome"], d["action"]), ("act", "enqueue"))

    def test_an_approval_run_does_not_count_toward_the_run_ceiling(self):  # FR-39: the Run ceiling is the cost ceiling
        ceiling = LIMITS["max_runs_per_item"]
        model = REVIEWED + [run(content="sha256:%04x" % i, at=at(20 + i), name="v%d" % i) for i in range(ceiling - 2)]
        landed = approvals(LIMITS["max_attempts"], conclusion="success", outcome=None, start=40)
        d = go(facts(threads=[thread()]), model + landed)
        self.assertEqual((d["outcome"], d["admit"]["intent"]), ("admit", "fix-findings"))
        d = go(facts(threads=[thread()]), model + [run(content="sha256:ffff", at=at(35), name="v")] + landed)
        self.assertEqual((d["outcome"], d["reason"]), ("hold", "run_ceiling"))

    def test_acts_are_bounded(self):  # I-8, FR-17
        limit = LIMITS["max_acts_per_item"]
        for reviews, action in (([], "issue_approval"), (APPROVED, "enqueue")):
            d = go(facts(reviews=reviews, acts_since_writer=limit - 1), REVIEWED)
            self.assertEqual((d["outcome"], d["action"]), ("act", action))
            for acts in (limit, limit + 1):
                d = go(facts(reviews=reviews, acts_since_writer=acts), REVIEWED)
                self.assertEqual((d["state"], d["outcome"], d["reason"], d["attention"]),
                                 ("held", "hold", "act_ceiling", "needs_you"), (action, acts))

    def test_an_unreadable_count_of_acts_makes_no_act(self):  # I-13
        # A fact read from outside is never given a default: a count that is not a whole number is unreadable.
        for reviews in ([], APPROVED):
            for value in ("missing", None, "0", 0.0, True, False, -1):
                f = facts(reviews=reviews)
                if value == "missing":
                    del f["acts_since_writer"]
                else:
                    f["acts_since_writer"] = value
                d = go(f, REVIEWED)
                self.assertEqual((d["state"], d["outcome"], d["reason"]), ("converged", "defer", "acts_unreadable"),
                                 (reviews, value))

    def test_the_act_ceiling_stops_acts_and_nothing_else(self):
        # A Run is bounded by the Run ceiling. A Hold is an act that stops work: counted, and never refused.
        over = LIMITS["max_acts_per_item"] + 1
        for value in (over, None):
            d = go(facts(acts_since_writer=value))
            self.assertEqual((d["outcome"], d["admit"]["intent"]), ("admit", "review-change"), value)
        failing = approvals(LIMITS["max_runs_per_item"] - 1, outcome="environment")
        cases = [({"last_pusher": "donpetry-bot"}, REVIEWED, "approver_is_author_or_last_pusher"),
                 ({}, REVIEWED + approvals(LIMITS["max_attempts"]), "attempts_exhausted"),
                 ({}, REVIEWED + failing, "run_ceiling")]
        for over_, runs, reason in cases:
            d = go(facts(acts_since_writer=over, **over_), runs)
            self.assertEqual((d["outcome"], d["reason"]), ("hold", reason), reason)

    def test_rounds_are_bounded(self):  # I-14
        runs = list(REVIEWED)
        for i in range(3):
            runs.append(run(intent="adjudicate-findings", at="2026-10-11T12:2%d:00Z" % (2 * i), name="o%d" % i))
            runs.append(run(role="dev-lead", intent="fix-findings", at="2026-10-11T12:2%d:00Z" % (2 * i + 1), name="a%d" % i))
        d = go(facts(threads=[thread()]), runs)
        self.assertEqual((d["outcome"], d["reason"]), ("hold", "max_rounds"))

    def test_org_concurrency_defers(self):  # I-3
        self.assertEqual(go(facts(), ctx=context(active_runs=4))["reason"], "concurrency")

    def test_observed_capacity_fault_defers_model_runs(self):
        d = go(facts(), ctx=context(model_deferred_until="2026-10-11T14:00:00Z"))
        self.assertEqual((d["outcome"], d["reason"]), ("defer", "capacity"))
        self.assertEqual(go(facts(), ctx=context(model_deferred_until="2026-10-11T12:00:00Z"))["outcome"], "admit")

    def test_no_author_role_means_nobody_is_admitted_to_fix(self):
        d = go(facts(threads=[thread()]), REVIEWED, cfg=config(author_role=None))
        self.assertEqual((d["outcome"], d["attention"]), ("nothing", "failed"))


class Queue(unittest.TestCase):
    """What takes a pull request out of the merge queue: GitHub reads its reviews only on the way in (L-19).

    It stays only while, read as if it were not queued, it would be approved and ready to merge. Any other reading
    takes it out, with that reading's State and reason. Hands-off never acts, and under a Pause the dequeue defers.
    """

    def test_a_queued_pull_request_with_no_approval_leaves_the_queue(self):  # I-9, FR-31
        # Its approval no longer stands for its content: there is none, it is of other content, or it was dismissed.
        lost = ([], [review(commit="c0", content="sha256:0000")], [dismissed(review(), MAINTAINER, "approved")])
        for reviews in lost:
            d = go(facts(queue=True, reviews=reviews), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["action"], d["content_id"]),
                             ("converged", "approval_lost", "act", "dequeue", "sha256:aaaa"), reviews)
        # An open gate takes it out too, whatever approval stands: a writer's thread, or a required Lens's Finding.
        for th in (thread(kind="human", name="don-petry", severity=None), thread()):
            for reviews in (APPROVED, []):
                d = go(facts(queue=True, reviews=reviews, threads=[th]), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["action"]),
                                 ("addressing", "gate_open", ["T1"], "act", "dequeue"), (th["opened_by"], reviews))
        # The other side: a standing approval with no open gate stays in the queue, and so does one that a
        # stranger's thread or a minor Finding is open on.
        for threads in ([], [thread(kind="human", name="stranger", can_write=False, severity=None)],
                        [thread(severity="minor")]):
            d = go(facts(queue=True, reviews=APPROVED, threads=threads), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("queued", "in_merge_queue", "nothing"), threads)
            self.assertNotIn("action", d)

    def test_a_minor_security_finding_opened_while_queued_takes_it_out_of_the_queue(self):  # FR-33, I-16
        # A required Lens's security Finding is a gate at any severity, so it is one in the merge queue too.
        for severity in ("minor", "info"):
            d = go(facts(queue=True, reviews=APPROVED, threads=[thread(severity=severity, category="security")]),
                   REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["action"]),
                             ("addressing", "gate_open", ["T1"], "act", "dequeue"), severity)
        # The other side: a minor Finding of another category, or from a Lens that is not required, leaves it there.
        for th in (thread(severity="minor"), thread(name="coderabbit", can_write=False, severity="minor",
                                                    category="security")):
            d = go(facts(queue=True, reviews=APPROVED, threads=[th]), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("queued", "in_merge_queue", "nothing"), th)

    def test_a_request_for_changes_made_while_queued_takes_it_out_of_the_queue(self):  # L-14
        # A writer's request gates as that person's thread does, made before the item entered the queue or after.
        asked = review(state="changes_requested", **MAINTAINER, at=at(30))
        d = go(facts(**AGENT, queue=True, reviews=[review(), asked]), ANSWERED)
        self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d.get("action")),
                         ("addressing", "gate_open", ["don-petry"], "act", "dequeue"))
        # The other side: that person's approval answers it, and the item stays in the queue.
        d = go(facts(**AGENT, queue=True, reviews=[review(), asked, review(**MAINTAINER, at=at(35))]), ANSWERED)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("queued", "in_merge_queue", "nothing"))
        # A stranger's or a Lens's request gates nothing here either.
        for who in (STRANGER, REVIEWER_APP):
            d = go(facts(**AGENT, queue=True, reviews=[review(), review(state="changes_requested", **who)]), ANSWERED)
            self.assertEqual((d["reason"], d["outcome"]), ("in_merge_queue", "nothing"), who)

    def test_a_hold_takes_a_queued_pull_request_out(self):  # FR-23, I-21
        # Taking it out of the queue is the one change the Factory makes to a held item: a merge is the last Effect.
        for reviews in (APPROVED, []):
            d = go(facts(queue=True, label_events=[labelled("factory:hold")], reviews=reviews), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["action"], d["attention"]),
                             ("held", "human_hold", "act", "dequeue", "needs_you"), reviews)
        # Hands-off means the Factory never acts: the item stays where the Maintainer left it, whatever else holds.
        incomplete = facts()["complete"]
        incomplete["threads"] = False
        for over in ({}, {"label_events": [labelled("factory:hold")]}, {"is_draft": True}, {"reviews": []}, {"complete": incomplete},
                     {"checks": with_check(0, "failure")}):
            f = facts(queue=True, **dict({"reviews": APPROVED}, **over))
            f["label_events"] = f["label_events"] + [labelled("factory:hands-off")]
            d = go(f, REVIEWED)
            self.assertNotEqual(d["outcome"], "act", over)
            self.assertNotIn("action", d)
        d = go(facts(queue=True, label_events=[labelled("factory:hands-off")], reviews=[]), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "hands_off", "hold"))
        # A held item that is not queued is only held.
        d = go(facts(label_events=[labelled("factory:hold")], reviews=APPROVED), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "human_hold", "hold"))
        self.assertNotIn("action", d)

    def test_an_approver_who_is_the_author_or_last_pusher_takes_it_out_of_the_queue(self):  # I-26, L-18
        # GitHub does not count that approval, so the item may not merge on it: the Hold the facts establish on the
        # converged path takes a queued item out too.
        for who in ("author", "last_pusher"):
            d = go(facts(queue=True, reviews=APPROVED, **{who: "donpetry-bot"}), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d.get("action"), d["attention"]),
                             ("held", "approver_is_author_or_last_pusher", "act", "dequeue", "needs_you"), who)
            # Under a Pause the dequeue defers, for the Maintainer to see.
            d = go(facts(queue=True, reviews=APPROVED, **{who: "donpetry-bot"}), REVIEWED, ctx=context(paused=True))
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                             ("held", "paused", "defer", "needs_you"), who)
            # The other side: not queued, it is held, as it always was.
            d = go(facts(reviews=APPROVED, **{who: "donpetry-bot"}), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "approver_is_author_or_last_pusher", "hold"))
        # An item with a gate open goes back to its author first, queued or not, as on the converged path.
        for queue, outcome in ((True, "act"), (False, "admit")):
            d = go(facts(queue=queue, reviews=APPROVED, threads=[thread()], author="donpetry-bot"), REVIEWED)
            self.assertEqual((d["reason"], d["outcome"]), ("gate_open" if queue else "findings_open", outcome), queue)

    def test_every_hold_takes_a_queued_pull_request_out(self):  # FR-23
        # A Hold the facts establish stops every Effect as a person's does: an outside item whose admission was taken
        # away, a diff too large or read short, an empty one.
        outside = {"class": "outside", "author": "stranger", "last_pusher": "stranger"}
        holds = [(outside, "outside_not_admitted"),
                 (dict(outside, label_events=[labelled("factory:admit", at=at(5))], last_push_at=at(10)), "outside_not_admitted"),
                 ({"diff": {"files": 2, "lines": 40, "truncated": True}}, "too_large"),
                 ({"diff": {"files": 2, "lines": LIMITS["max_diff_lines"] + 1, "truncated": False}}, "too_large"),
                 ({"diff": {"files": 0, "lines": 0, "truncated": False}}, "empty_diff")]
        for over, reason in holds:
            d = go(facts(queue=True, reviews=APPROVED, **over), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d.get("action")),
                             ("held", reason, "act", "dequeue"), over)
            # The other side: not queued, it is only held.
            d = go(facts(reviews=APPROVED, **over), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", reason, "hold"), over)
        # An outside item admitted after its author's latest push stays in the queue.
        d = go(facts(queue=True, reviews=APPROVED, **dict(outside, label_events=[labelled("factory:admit", at=at(5))]),
                     last_push_at=at(1)), REVIEWED)
        self.assertEqual((d["reason"], d["outcome"]), ("in_merge_queue", "nothing"))

    def test_a_read_that_fails_takes_a_pull_request_out_of_the_queue(self):  # I-13
        # A dequeue is a stop, not work: a fact that cannot be read takes the item out rather than leaving it to merge.
        rv = dict(review(state="changes_requested", **MAINTAINER), by=None)
        for part in PARTS:
            f = facts(queue=True, reviews=APPROVED)
            f["complete"][part] = False
            d = go(f, REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["action"]),
                             (None, "facts_incomplete", [part], "act", "dequeue"), part)
        d = go(facts(**AGENT, queue=True, reviews=[review(), rv]), ANSWERED)
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["action"]), (None, "review_unreadable", "act", "dequeue"))
        # So does a required Lens's thread whose category or severity cannot be read.
        th = thread(severity="minor", category=None)
        d = go(facts(queue=True, reviews=APPROVED, threads=[th]), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["action"]),
                         (None, "thread_unreadable", ["T1"], "act", "dequeue"))
        self.assertEqual(go(facts(reviews=APPROVED, threads=[th]), REVIEWED)["outcome"], "defer")
        # The other side: not queued, the same read defers and acts on nothing.
        d = go(facts(**AGENT, reviews=[review(), rv]), ANSWERED)
        self.assertEqual((d["reason"], d["outcome"]), ("review_unreadable", "defer"))
        self.assertNotIn("action", d)

    def test_a_check_that_no_longer_passes_takes_it_out_of_the_queue(self):  # I-9, I-27
        # Convergence must still hold on the content: a required check that now fails or gives no verdict, or a
        # conflict with the base. Each is a definite answer, and none ends on its own.
        lens = LENS_OF[GREEN[0]["name"]]
        cases = [({"checks": with_check(0, "failure")}, "addressing", "check_failed", [lens]),
                 ({"checks": with_check(0, "timed_out")}, "addressing", "check_failed", [lens]),
                 ({"checks": with_check(0, "neutral")}, "verifying", "check_unreadable", [lens]),
                 ({"mergeable": False}, "addressing", "conflict", [])]
        for over, state, reason, evidence in cases:
            d = go(facts(queue=True, reviews=APPROVED, **over), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["action"]),
                             (state, reason, evidence, "act", "dequeue"), reason)
        # The other side: every check passing and the review there, it stays.
        self.assertEqual(go(facts(queue=True, reviews=APPROVED), REVIEWED)["reason"], "in_merge_queue")

    def test_a_check_from_another_app_or_a_failure_beside_a_pass_takes_it_out_of_the_queue(self):  # I-9, I-27
        # A Lens is read from its own App alone, and from every check it reports there, on a queued item too.
        lens = LENS_OF[GREEN[0]["name"]]
        foreign = "%s:from_app:%d" % (lens, OTHER_APP)
        cases = [([dict(GREEN[0], app_id=OTHER_APP)], "verifying", "check_unreadable", foreign),
                 ([GREEN[0], dict(GREEN[0], app_id=OTHER_APP)], "verifying", "check_unreadable", foreign),
                 ([dict(GREEN[0], app_id=OTHER_APP), dict(GREEN[1], conclusion="failure")], "verifying",
                  "check_unreadable", foreign),
                 ([dict(GREEN[0], conclusion="failure"), GREEN[0]], "addressing", "check_failed", lens),
                 ([GREEN[0], dict(GREEN[0], conclusion="failure")], "addressing", "check_failed", lens),
                 ([GREEN[0], dict(GREEN[0], conclusion="neutral")], "verifying", "check_unreadable", lens)]
        for entries, state, reason, evidence in cases:
            d = go(facts(queue=True, reviews=APPROVED, checks=entries + GREEN[1:]), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["action"]),
                             (state, reason, [evidence], "act", "dequeue"), entries)
        # The other side: one still running beside a pass is a wait, and a wait takes nothing out; nor do two passes.
        for entries in ([GREEN[0], dict(GREEN[0], conclusion="in_progress")], [GREEN[0], dict(GREEN[0])]):
            d = go(facts(queue=True, reviews=APPROVED, checks=entries + GREEN[1:]), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("queued", "in_merge_queue", "nothing"), entries)

    def test_a_check_from_another_workflow_takes_it_out_of_the_queue(self):  # I-9, I-27
        # A Lens GitHub Actions runs is read from its own workflow file alone, on a queued item too.
        actions = next(c for c in GREEN if isinstance(c["workflow"], str))
        lens = LENS_OF[actions["name"]]
        for path, shown in ((OTHER_WORKFLOW, OTHER_WORKFLOW), (None, "unreadable")):
            for entries in ([dict(actions, workflow=path)] + GREEN, GREEN + [dict(actions, workflow=path)]):
                d = go(facts(queue=True, reviews=APPROVED, checks=entries), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["action"]),
                                 ("verifying", "check_unreadable", ["%s:from_workflow:%s" % (lens, shown)], "act",
                                  "dequeue"), path)
        # The other side: two checks from its own file, both passing, take nothing out.
        d = go(facts(queue=True, reviews=APPROVED, checks=GREEN + [dict(actions)]), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("queued", "in_merge_queue", "nothing"))

    def test_a_queued_item_whose_evidence_goes_missing_or_unreadable_leaves_the_queue(self):  # I-31, I-13
        # GitHub's merge queue knows nothing of an acceptance contract, so a queued item stays only while every
        # criterion has passing evidence on its content. Evidence that is gone, as an artifact is after its retention,
        # or is for other content, takes it out, and so does a failure or evidence that cannot be read.
        both = [evidence("AC-1"), evidence("AC-2")]
        cases = [(contract(), "verifying", "acceptance_evidence_missing", ["AC-1", "AC-2"]),
                 (contract(results=[evidence("AC-1"), evidence("AC-2", content="sha256:0000")]), "verifying",
                  "acceptance_evidence_missing", ["AC-2"]),
                 (contract(results=[evidence("AC-1"), evidence("AC-2", "failing")]), "addressing",
                  "acceptance_failed", ["AC-2"]),
                 (contract(results=both + [evidence("AC-1", content="")]), None, "acceptance_unreadable", []),
                 (contract(results=both + [evidence("AC-3")]), None, "acceptance_unreadable", [])]
        for acceptance, state, reason, lacking in cases:
            d = go(facts(queue=True, reviews=APPROVED, acceptance=acceptance), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["action"]),
                             (state, reason, lacking, "act", "dequeue"), reason)
        # The other side: every criterion passing on this content, it stays; and so does an item with no contract.
        for acceptance in (contract(results=both), None):
            d = go(facts(queue=True, reviews=APPROVED, acceptance=acceptance), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("queued", "in_merge_queue", "nothing"))

    def test_a_normal_wait_leaves_a_pull_request_in_the_queue(self):  # I-13
        # A wait ends on its own, so it takes nothing out. GitHub reports the merge state as unknown each time the base
        # moves, and the base moves each time the queue merges another item: a dequeue on it would empty the queue. A
        # required check that is pending or not there yet, and a required Lens that has not reported on this content,
        # are waits too. Each is read past, and what lies behind it still decides.
        waits = [({"mergeable": None}, REVIEWED, (None, "mergeable_unreadable")),
                 ({"mergeable": "UNKNOWN"}, REVIEWED, (None, "mergeable_unreadable")),
                 ({"checks": with_check(0, "pending")}, REVIEWED, ("verifying", "awaiting_checks")),
                 ({"checks": with_check(0, "absent")}, REVIEWED, ("verifying", "awaiting_checks")),
                 ({}, (), ("verifying", "awaiting_review")),
                 ({}, [run(conclusion="failure", outcome="environment")], ("verifying", "awaiting_review")),
                 ({"mergeable": None, "checks": with_check(0, "pending")}, (), (None, "mergeable_unreadable"))]
        for over, runs, unqueued in waits:
            d = go(facts(queue=True, reviews=APPROVED, **over), runs)
            self.assertEqual((d["state"], d["reason"], d["outcome"]), ("queued", "in_merge_queue", "nothing"), over)
            self.assertNotIn("action", d)
            # The other side: not queued, the same item waits as it always did.
            d = go(facts(reviews=APPROVED, **over), runs)
            self.assertEqual((d["state"], d["reason"]), unqueued, over)
            self.assertNotEqual(d["outcome"], "act", over)
            # And behind the wait, a definite stop still takes the item out.
            behind = [({"reviews": []}, "approval_lost"), ({"threads": [thread()]}, "gate_open")]
            if "checks" not in over:
                behind.append(({"checks": with_check(1, "failure")}, "check_failed"))
            for more, reason in behind:
                d = go(facts(queue=True, **dict({"reviews": APPROVED}, **over, **more)), runs)
                self.assertEqual((d["reason"], d["outcome"], d.get("action")), (reason, "act", "dequeue"), (over, more))

    def test_a_draft_leaves_the_queue_and_an_unserved_item_is_left_alone(self):
        # A draft is not ready, so it cannot be ready to merge. An item whose base is not protected is not served at
        # all: the Factory makes no change to it, a dequeue among them.
        d = go(facts(queue=True, is_draft=True, reviews=APPROVED), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["action"]), ("draft", "draft", "act", "dequeue"))
        d = go(facts(queue=True, targets_protected=False, reviews=[]), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("not_served", "base_not_protected", "nothing"))
        self.assertNotIn("action", d)
        # Nor is a merged or closed item touched, whatever the queue says.
        for state in ("merged", "closed"):
            d = go(facts(state=state, queue=True, reviews=[]), REVIEWED)
            self.assertEqual((d["state"], d["outcome"]), (state, "nothing"))

    def test_under_a_pause_a_dequeue_defers_for_the_maintainer(self):  # I-7
        # A dequeue defers like every other act. Only the Maintainer can stop the merge now, so each one needs them.
        incomplete = facts()["complete"]
        incomplete["reviews"] = False
        stops = [({"label_events": [labelled("factory:hold")], "reviews": APPROVED}, "held"),
                 ({"reviews": []}, "converged"),
                 ({"reviews": APPROVED, "threads": [thread(kind="human", name="don-petry", severity=None)]}, "addressing"),
                 ({"reviews": APPROVED, "checks": with_check(0, "failure")}, "addressing"),
                 ({"reviews": APPROVED, "complete": incomplete}, None)]
        for over, state in stops:
            for paused, reason in ((True, "paused"), (None, "pause_unreadable")):
                d = go(facts(queue=True, **over), REVIEWED, ctx=context(paused=paused))
                self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                                 (state, reason, "defer", "needs_you"), (over, paused))
                self.assertNotIn("action", d)
            self.assertEqual(go(facts(queue=True, **over), REVIEWED)["action"], "dequeue", over)
        # The other side: an item that may stay is not the Maintainer's to see because of the Pause.
        d = go(facts(queue=True, reviews=APPROVED), REVIEWED, ctx=context(paused=True))
        self.assertEqual((d["reason"], d["outcome"], d["attention"]), ("in_merge_queue", "nothing", "ready"))

    def test_a_dequeue_is_never_refused_at_the_act_ceiling(self):  # I-8
        # An act that stops work is counted and never refused, so neither the count nor its reading stops it.
        stops = [({"label_events": [labelled("factory:hold")], "reviews": APPROVED}, "human_hold"), ({"reviews": []}, "approval_lost"),
                 ({"reviews": APPROVED, "threads": [thread()]}, "gate_open")]
        for over, reason in stops:
            for acts in (LIMITS["max_acts_per_item"], LIMITS["max_acts_per_item"] + 1, None, -1):
                d = go(facts(queue=True, acts_since_writer=acts, **over), REVIEWED)
                self.assertEqual((d["reason"], d["outcome"], d.get("action")), (reason, "act", "dequeue"), (reason, acts))
        # The other side: the same count refuses an enqueue.
        d = go(facts(reviews=APPROVED, acts_since_writer=LIMITS["max_acts_per_item"]), REVIEWED)
        self.assertEqual((d["reason"], d["outcome"]), ("act_ceiling", "hold"))

    def test_a_run_in_progress_does_not_keep_a_pull_request_in_the_queue(self):  # I-2
        # A dequeue is the Controller's act, not a Run, and it stops work: one writer per item does not delay it.
        busy = REVIEWED + [run(role="dev-lead", intent="fix-findings", status="in_progress", at=at(20), name="r2")]
        for over, reason in (({"label_events": [labelled("factory:hold")], "reviews": APPROVED}, "human_hold"),
                             ({"reviews": []}, "approval_lost")):
            d = go(facts(queue=True, **over), busy)
            self.assertEqual((d["reason"], d["outcome"], d.get("action")), (reason, "act", "dequeue"), reason)
        # The other side: a Run in progress still holds an item that is not queued.
        d = go(facts(reviews=[]), busy)
        self.assertEqual((d["outcome"], d["attention"]), ("nothing", "working"))


class Staleness(unittest.TestCase):
    """A wait past its State's limit is the Maintainer's to see, and what happens next does not change (I-1, FR-3)."""

    # The poller has run without a break since long before any of these items last moved.
    PASSING = context(passes_since="2026-10-11T09:00:00Z")
    # Every required check passed at minute 5, but one that has not reported.
    SILENT = [dict(GREEN[0], conclusion="pending", completed_at=None)] + GREEN[1:]

    def waits(self) -> list:
        """(facts, runs, State, its attention, when it last moved): one wait for each State that can go stale."""
        return [(facts(checks=self.SILENT), (), "verifying", "review", at(5)),
                (facts(), REVIEWED, "converged", "ready", at(10)),
                (facts(queue=True, reviews=APPROVED), REVIEWED, "queued", "ready", at(15))]

    def test_a_lens_that_never_reports_is_stale(self):  # I-1
        for f, runs, state, waiting, moved in self.waits():
            limit = CONFIG["lifecycle"]["stale_after_minutes"][state]
            before = go(f, runs, self.PASSING, now=later(moved, limit - 1))
            self.assertEqual((before["state"], before["attention"]), (state, waiting), state)
            # At the limit it is not yet past it.
            self.assertEqual(go(f, runs, self.PASSING, now=later(moved, limit))["attention"], waiting, state)
            past = go(f, runs, self.PASSING, now=later(moved, limit + 1))
            self.assertEqual(past["attention"], "stale", state)
            # Only the attention changes: the State, the reason, the outcome and any act are as they were.
            self.assertEqual(dict(past, attention=waiting), before, state)

    def test_staleness_counts_only_while_passes_run(self):  # I-1, §4.6
        # The check went silent at minute 5, so by 13:00 the wait is 55 minutes against a limit of 30. But a wait
        # counts only while passes ran: an outage of the poller is one health alert, not one for each item.
        f = facts(checks=self.SILENT)
        for since, attention in (("2026-10-11T12:40:00Z", "review"), ("2026-10-11T12:30:00Z", "review"),
                                 ("2026-10-11T12:29:00Z", "stale"), ("2026-10-11T11:00:00Z", "stale")):
            d = go(f, ctx=context(passes_since=since))
            self.assertEqual((d["state"], d["attention"]), ("verifying", attention), since)
        # A start that cannot be read is passed over: that shows more, never less.
        missing = context()
        del missing["passes_since"]
        for ctx in (missing, context(passes_since=None), context(passes_since="2026-10-11 12:40"),
                    context(passes_since="yesterday"), context(passes_since=1760187600)):
            self.assertEqual(go(f, ctx=ctx)["attention"], "stale", ctx.get("passes_since", "missing"))

    def test_only_what_a_writer_a_lens_or_the_factory_does_moves_an_item(self):  # I-1, I-28, decision 0002
        # State is never stored, so the time an item entered it is read from what moved it last.
        f, past = facts(checks=self.SILENT), "2026-10-11T12:36:00Z"
        self.assertEqual(go(f, ctx=self.PASSING, now=past)["attention"], "stale")
        lens = {"kind": "lens", "name": "coderabbit", "can_write": False}
        moves = {"a push": {"last_push_at": at(20)},
                 "a required check that reports": {"checks": self.SILENT[:1] + [dict(GREEN[1], completed_at=at(20))]
                                                   + GREEN[2:]},
                 "a writer's review": {"reviews": [review(state="commented", kind="human", name="a-colleague", at=at(20))]},
                 "a Lens's review": {"reviews": [review(state="commented", **REVIEWER_APP, at=at(20))]},
                 "the machine user's review": {"reviews": [review(state="commented", at=at(20))]},
                 "a Lens's thread": {"threads": [dict(thread(severity=None, at=at(20)), opened_by=lens)]},
                 "a writer's thread, resolved": {"threads": [thread(kind="human", name="don-petry", resolved=True,
                                                                    severity=None, at=at(20))]},
                 "a writer's action": {"last_writer_action_at": at(20)}}
        for what, over in moves.items():
            d = go(facts(**dict({"checks": self.SILENT}, **over)), ctx=self.PASSING, now=past)
            self.assertEqual((d["state"], d["attention"]), ("verifying", "review"), what)
        d = go(f, [run(at=at(20))], ctx=self.PASSING, now=past)
        self.assertEqual((d["state"], d["attention"]), ("verifying", "review"), "a Run")
        # The other side: anyone can comment, so a stranger's review or thread moves nothing, and nor does a check
        # that is not required, or a Run on another item. Otherwise a comment every half hour would hide a stall. Nor
        # does an App that is no Lens's: no configuration names it, and any App installed on the repo could comment.
        stranger = {"a stranger's review": {"reviews": [review(state="commented", kind="human", name="stranger",
                                                               can_write=False, at=at(20))]},
                    "a stranger's thread": {"threads": [thread(kind="human", name="stranger", can_write=False,
                                                               severity=None, at=at(20))]},
                    "an App's review": {"reviews": [review(state="commented", **AUTHOR_APP, at=at(20))]},
                    "an App's thread": {"threads": [dict(thread(severity=None, at=at(20)), opened_by=AUTHOR_APP)]},
                    "a check that is not required": {"checks": self.SILENT + [
                        {"name": "template-drift", "app_id": OTHER_APP, "conclusion": "success",
                         "completed_at": at(20)}]}}
        for what, over in stranger.items():
            d = go(facts(**dict({"checks": self.SILENT}, **over)), ctx=self.PASSING, now=past)
            self.assertEqual((d["state"], d["attention"]), ("verifying", "stale"), what)
        elsewhere = dict(run(at=at(20)), item=dict(f["item"], number=43))
        self.assertEqual(go(f, [elsewhere], ctx=self.PASSING, now=past)["attention"], "stale")

    def test_only_a_check_from_its_lens_app_moves_an_item(self):  # I-1, I-28
        # Any App with checks: write can post a check under a required Lens's name, so only the check the Lens's own App
        # reports is its completion. Read whole, such a check leaves the item unreadable for the Maintainer to see, so
        # what moved it is read here alone.
        f = facts(checks=self.SILENT)
        self.assertEqual(derive.moved_at(f, [], CONFIG, NOW), at(5))
        own = dict(GREEN[1], completed_at=at(20))
        self.assertEqual(derive.moved_at(facts(checks=self.SILENT + [own]), [], CONFIG, NOW), at(20))
        another_lens = next(c["app_id"] for c in GREEN if c["app_id"] != own["app_id"])
        for app in (OTHER_APP, another_lens, None, str(own["app_id"]), float(own["app_id"])):
            impostor = dict(own, app_id=app)
            self.assertEqual(derive.moved_at(facts(checks=self.SILENT + [impostor]), [], CONFIG, NOW), at(5), app)
        missing = dict(own)
        del missing["app_id"]
        self.assertEqual(derive.moved_at(facts(checks=self.SILENT + [missing]), [], CONFIG, NOW), at(5))

    def test_only_a_check_from_its_lens_workflow_moves_an_item(self):  # I-1, I-28
        # GitHub Actions runs any job a pull request adds, under any name, so only the check from a Lens's own workflow
        # file is its completion; a Lens no workflow runs is read only from a check that names none.
        own = dict(GREEN[1], completed_at=at(20))
        self.assertIsInstance(own["workflow"], str)
        self.assertEqual(derive.moved_at(facts(checks=self.SILENT + [own]), [], CONFIG, NOW), at(20))
        for path in (OTHER_WORKFLOW, GREEN[0]["workflow"], None, own["workflow"].upper(), "absent"):
            impostor = dict(own, workflow=path)
            if path == "absent":
                del impostor["workflow"]
            self.assertEqual(derive.moved_at(facts(checks=self.SILENT + [impostor]), [], CONFIG, NOW), at(5), path)
        unrun = next(c for c in GREEN if c["workflow"] is None)
        self.assertEqual(derive.moved_at(facts(checks=self.SILENT + [dict(unrun, completed_at=at(20))]), [], CONFIG,
                                         NOW), at(20))
        for path in (OTHER_WORKFLOW, "absent"):
            impostor = dict(unrun, workflow=path, completed_at=at(20))
            if path == "absent":
                del impostor["workflow"]
            self.assertEqual(derive.moved_at(facts(checks=self.SILENT + [impostor]), [], CONFIG, NOW), at(5), path)

    def test_a_time_that_is_no_moment_or_still_to_come_moves_nothing(self):  # I-1, I-13
        # A time is read only when it is a real moment no later than now. Any other is passed over, so a time in the
        # future, or one with a field no calendar has, never hides a stalled item: that shows more, never less. Each
        # time that is no moment sorts, as text, between the item's last movement and now, where it would hide it.
        lens = {"kind": "lens", "name": "coderabbit", "can_write": False}
        frames = [("2026-10-11T12:05:00Z", "2026-10-11T12:36:00Z",
                   ["2026-10-11T12:37:00Z", "9999-12-31T23:59:59Z", "2026-10-11T12:20:60Z"]),
                  ("2026-10-11T12:05:00Z", "2026-10-11T13:00:00Z", ["2026-10-11T12:60:00Z"]),
                  ("2026-10-11T23:50:00Z", "2026-10-12T00:30:00Z", ["2026-10-11T24:10:00Z"]),
                  ("2026-02-28T23:50:00Z", "2026-03-01T00:30:00Z",
                   ["2026-02-29T00:10:00Z", "2026-02-30T00:10:00Z", "2026-02-31T00:10:00Z"]),
                  ("2026-04-30T23:50:00Z", "2026-05-01T00:30:00Z", ["2026-04-31T00:10:00Z"]),
                  ("2026-10-31T23:50:00Z", "2026-11-01T00:30:00Z", ["2026-10-32T00:10:00Z"]),
                  ("2026-09-30T23:50:00Z", "2026-10-01T00:30:00Z", ["2026-10-00T00:10:00Z"]),
                  ("2026-12-31T23:50:00Z", "2027-01-01T00:30:00Z", ["2026-13-01T00:10:00Z", "2026-99-99T99:99:99Z"]),
                  ("2025-12-31T23:50:00Z", "2026-01-01T00:30:00Z", ["2026-00-01T00:10:00Z"])]
        for moved, now, whens in frames:
            silent = [dict(self.SILENT[0])] + [dict(c, completed_at=moved) for c in GREEN[1:]]
            base = {"checks": silent, "last_push_at": moved, "last_writer_action_at": moved}
            self.assertEqual(go(facts(**base), ctx=self.PASSING, now=now)["attention"], "stale", (moved, now))
            # The other side: a real moment between the two moves the item.
            between = later(now, -10)
            for when in whens + [between]:
                expected = "review" if when == between else "stale"
                over = {"last_push_at": {"last_push_at": when},
                        "completed_at": {"checks": silent[:1] + [dict(silent[1], completed_at=when)] + silent[2:]},
                        "opened_at": {"threads": [dict(thread(severity=None, at=when), opened_by=lens)]},
                        "last_writer_action_at": {"last_writer_action_at": when}}
                if when > now or when == between:
                    # A review whose time is no moment cannot be read at all, and needs a person: a writer's could gate.
                    over["submitted_at"] = {"reviews": [review(state="commented", kind="human", name="a-colleague",
                                                               at=when)]}
                for field, more in over.items():
                    d = go(facts(**dict(base, **more)), ctx=self.PASSING, now=now)
                    self.assertEqual((d["state"], d["attention"]), ("verifying", expected), (field, when))
                d = go(facts(**base), [run(at=when)], ctx=self.PASSING, now=now)
                self.assertEqual(d["attention"], expected, ("started_at", when))
                if when != between:
                    d = go(facts(**base), ctx=context(passes_since=when), now=now)
                    self.assertEqual(d["attention"], "stale", ("passes_since", when))
                    # Nor does it hide a real movement behind it: the newest real moment is the one counted.
                    d = go(facts(**dict(base, last_push_at=when, last_writer_action_at=between)), ctx=self.PASSING,
                           now=now)
                    self.assertEqual(d["attention"], "review", ("behind", when))

    def test_the_kernel_never_raises_on_a_time_the_schema_accepts(self):  # I-13
        # The schema's pattern bounds each field, but not the day to its month. Whatever it lets through, every time
        # the Kernel reads, `now` among them, gives a Decision and never an exception.
        schema = json.loads((ROOT / "schemas" / "facts.schema.json").read_text())
        edges = ["0000-01-01T00:00:00Z", "0001-01-01T00:00:00Z", "1900-02-29T00:00:00Z", "2000-02-29T23:59:59Z",
                 "2026-02-29T12:00:00Z", "2026-02-31T12:00:00Z", "2026-04-31T12:00:00Z", "2026-12-31T23:59:59Z",
                 "2026-10-11T12:59:59Z", "9999-12-31T23:59:59Z", "9999-02-31T23:59:59Z"]
        # And the schema refuses a field no calendar has.
        refused = ["2026-13-01T00:00:00Z", "2026-00-01T00:00:00Z", "9999-99-01T00:00:00Z", "2026-10-32T00:00:00Z",
                   "2026-10-00T00:00:00Z", "2026-10-11T24:00:00Z", "2026-10-11T12:60:00Z", "2026-10-11T12:00:60Z"]
        for when in refused:
            self.assertNotEqual(validate(facts(last_push_at=when), schema), [], when)
        lost = {"queue": True, "reviews": [review(commit="c0", content="sha256:0000")]}
        for when in edges + [w for w in refused if not validate(facts(last_push_at=w), schema)]:
            checks = [dict(c, completed_at=when) for c in GREEN]
            items = [facts(checks=checks, last_push_at=when, last_writer_action_at=when, threads=[thread(at=when)]),
                     facts(checks=checks, last_push_at=when, last_writer_action_at=when, **lost),
                     facts(checks=self.SILENT, last_push_at=when, reviews=[review(state="commented", at=when)])]
            for f in items:
                self.assertEqual(validate(f, schema), [], when)
                for now in (NOW, when):
                    d = go(f, [run(at=when)], ctx=context(passes_since=when), now=now)
                    self.assertIn(d["outcome"], ("nothing", "defer", "hold", "act", "admit"), (when, now))
        # An approval lost while queued is still taken out, whatever time a passing check gives.
        d = go(facts(checks=[dict(GREEN[0], completed_at="2026-02-31T00:00:00Z")] + GREEN[1:], **lost), REVIEWED)
        self.assertEqual((d["reason"], d["outcome"], d["action"]), ("approval_lost", "act", "dequeue"))

    def test_a_deferral_of_the_whole_scope_is_never_stale(self):  # I-1, §4.6
        # A Pause, read or not, the model provider's deferral, capacity that cannot be read and the org's limit on Runs
        # each hold every item at once. Each is one cause, reported once, and the item keeps the attention it had.
        day_on = "2026-10-12T13:00:00Z"
        waiting = dict(self.PASSING)
        deferrals = [({"paused": True}, (), "paused", "ready"),
                     ({"paused": None}, (), "pause_unreadable", "ready"),
                     ({"model_deferred_until": "2026-10-13T00:00:00Z"}, (), "capacity", "review"),
                     ({"model_deferred_until": "unreadable"}, (), "capacity_unreadable", "review"),
                     ({"active_runs": None}, (), "capacity_unreadable", "review"),
                     ({"active_runs": LIMITS["org_max_active_runs"]}, (), "concurrency", "review")]
        for over, _, reason, attention in deferrals:
            runs = REVIEWED if attention == "ready" else ()
            ctx = dict(waiting, **over)
            if over.get("model_deferred_until") == "unreadable":
                del ctx["model_deferred_until"]
            d = go(facts(), runs, ctx, now=day_on)
            self.assertEqual((d["reason"], d["outcome"], d["attention"]), (reason, "defer", attention), reason)
            # The other side: once the deferral ends, a wait that is still silent goes stale as usual.
            d = go(facts(), runs, waiting, now=day_on)
            self.assertEqual((d["outcome"], d["attention"]), ("act" if runs else "admit", "stale"), reason)

    def test_a_wait_for_acceptance_evidence_goes_stale(self):  # I-1, I-31
        # Evidence that never comes is a wait in verifying, counted from when the item last moved: here the review Run
        # at minute 10. Past the limit it is the Maintainer's to see, and nothing else changes.
        f = facts(acceptance=contract(results=[evidence("AC-1")]))
        limit = CONFIG["lifecycle"]["stale_after_minutes"]["verifying"]
        before = go(f, REVIEWED, self.PASSING, now=later(at(10), limit))
        self.assertEqual((before["reason"], before["attention"]), ("acceptance_evidence_missing", "review"))
        past = go(f, REVIEWED, self.PASSING, now=later(at(10), limit + 1))
        self.assertEqual((past["attention"], dict(past, attention="review")), ("stale", before))
        # A contract that cannot be read already needs a person, and is never stale.
        f = facts(acceptance=contract(results=[evidence("AC-9")]))
        self.assertEqual(go(f, REVIEWED, self.PASSING, now="2026-10-12T13:00:00Z")["attention"], "needs_you")

    def test_needs_you_is_never_stale(self):  # I-1
        # A person is already called to an item that needs them, and a Run holds one that is working: neither is stale.
        # Nor is one that failed, which is the author's, or one the Factory leaves alone.
        incomplete = facts()["complete"]
        incomplete["checks"] = False
        busy = [run(role="dev-lead", intent="fix-findings", status="in_progress", at=at(20), name="r2")]
        cases = [(facts(label_events=[labelled("factory:hold")]), (), "needs_you"),
                 (facts(checks=with_check(0, "neutral")), (), "needs_you"),
                 (facts(threads=[thread(kind="human", name="don-petry", severity=None)]), REVIEWED, "needs_you"),
                 (facts(threads=[thread()]), REVIEWED + busy, "working"),
                 (facts(checks=with_check(0, "failure")), (), "failed"),
                 (facts(is_draft=True), (), "none"),
                 (facts(label_events=[labelled("factory:hands-off")]), (), "none"),
                 (facts(complete=incomplete), (), "none")]
        for f, runs, attention in cases:
            self.assertEqual(go(f, runs, self.PASSING, now="2026-10-12T13:00:00Z")["attention"], attention, attention)
        # The other side: a day on, a wait for a Lens is stale.
        self.assertEqual(go(facts(checks=self.SILENT), (), self.PASSING, now="2026-10-12T13:00:00Z")["attention"],
                         "stale")

    def test_the_kernel_counts_time_as_the_calendar_does(self):
        # The Kernel reads no clock and imports nothing, so it counts the seconds between two times itself.
        rng = random.Random(36)
        shape = "%Y-%m-%dT%H:%M:%SZ"
        edges = ["1900-02-28T23:59:59Z", "2000-02-29T00:00:00Z", "2024-12-31T23:59:59Z", "2100-03-01T00:00:00Z",
                 "2026-10-11T12:00:00Z", "2400-02-29T12:00:00Z"]
        start = datetime.datetime(1890, 1, 1)
        span = int((datetime.datetime(2410, 1, 1) - start).total_seconds())
        # random() only, whose sequence is the same on every Python version.
        times = edges + [(start + datetime.timedelta(seconds=int(rng.random() * span))).strftime(shape)
                         for _ in range(400)]
        for a in times:
            for b in (times[0], times[1], times[-1], a):
                want = (datetime.datetime.strptime(b, shape) - datetime.datetime.strptime(a, shape)).total_seconds()
                self.assertEqual(derive.seconds(b) - derive.seconds(a), want, (a, b))
        # The limit accepts any Lifecycle, the issue's among them.
        issue = json.loads((ROOT / "lifecycle" / "issue.json").read_text())
        limit = issue["stale_after_minutes"]["in_review"]
        self.assertFalse(derive.stale(issue, "in_review", at(0), None, later(at(0), limit)))
        self.assertTrue(derive.stale(issue, "in_review", at(0), None, later(at(0), limit + 1)))

class TheFactorysOwnRules(unittest.TestCase):
    """A change to a protected path or to a Lens's input converges only once every model Lens has reviewed its head,
    whatever its class, and the machine user then approves it as it does every item (decision 0020, I-45)."""

    def waits_for_review(self, paths, pattern=None, cls=DEPENDENCY, content="sha256:bbbb"):
        """A pull request of `cls` that changes `paths`, reviewed only on the head before, waits for the review of this one,
        naming `pattern`."""
        d = go(changing(**cls, changed_paths=list(paths), content_id=content), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["evidence"][0]),
                         ("verifying", "awaiting_review", "admit", "pr-review"), paths)
        self.assertEqual(d["admit"], dict(REVIEW_IT, content_id=content), paths)
        if pattern is not None:
            self.assertIn(pattern, d["evidence"], paths)
        return d

    def converges(self, paths, cls=DEPENDENCY):
        """A pull request of `cls` that changes `paths`, with no review at all, is due its approval."""
        d = go(changing(**cls, changed_paths=list(paths)))
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["action"]),
                         ("converged", "approval_due", "act", "issue_approval"), paths)

    def test_a_change_to_a_protected_path_needs_the_model_review(self):  # I-45
        # A dependency update is judged by the deterministic Lenses alone while it changes nothing on the list.
        self.converges(["docs/notes.md"])
        for entry in HOOKS["protected"]:
            path = example(entry["path"])
            self.waits_for_review(["docs/notes.md", path], entry["path"])
            # Reviewed on this head, it converges, and the machine user approves it as usual.
            d = go(changing(**DEPENDENCY, changed_paths=["docs/notes.md", path]), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["action"]), ("converged", "approval_due", "issue_approval"),
                             path)
        # Every other class needs the review anyway; the list names what it touched.
        d = go(changing(changed_paths=["lifecycle/pull_request.json"]))
        self.assertEqual((d["reason"], d["evidence"], d["admit"]), ("awaiting_review", ["pr-review", "lifecycle/"],
                                                                    REVIEW_IT))

    def test_a_lens_input_counts_like_a_protected_path(self):  # I-45, decision 0018
        for entry in HOOKS["lens_inputs"]:
            self.waits_for_review([example(entry["path"])], entry["path"])
        # Deep below a directory, and the directory's own name; never a name that only starts with it, nor the same
        # name further down.
        for path in ("tests/a/b/test_x.py", "tests", "sim/world.py", "Makefile", "makefile", "GNUmakefile", "json.py",
                     "kernel/gate.py", ".gitleaks.toml", ".gitleaksignore"):
            self.waits_for_review([path])
        for path in ("testsuite/x.py", "docs/tests/x.py", "docs/Makefile", "docs/json.py", "x/.gitleaks.toml",
                     "kernelx/a.py", "tests.d/x.md"):
            self.converges([path])

    def test_a_package_at_the_top_of_the_repo_counts_as_a_lens_input(self):  # I-45
        # `python3 -m tools.verify` puts the top of the repo first on the path, so a package there, `unittest/` with an
        # `__init__`, is imported before the standard library's, and changes what verify does.
        f = changing(**DEPENDENCY, changed_paths=["unittest/__init__.py", "unittest/AGENTS.md"])
        d = go(f)
        self.assertEqual((d["state"], d["reason"], d["evidence"], d["admit"]),
                         ("verifying", "awaiting_review", ["pr-review", "*/__init__.*"], REVIEW_IT))
        for path in ("ast/__init__.pyc", "json.cpython-39-darwin.so", "json.pyd", "__pycache__/json.cpython-39.pyc"):
            self.waits_for_review([path])
        # The other side: a directory with no __init__ is a namespace package, which shadows no module; nor does a
        # package below the top.
        for path in ("unittest/AGENTS.md", "docs/unittest/__init__.py", "docs/a/__pycache__/x.pyc"):
            self.converges([path])

    def test_anything_at_the_top_of_the_repo_counts_as_a_lens_input(self):  # I-45
        # verify may import any file or link at the top of the repo before the standard library, whatever its name: a
        # link `json` to a package elsewhere among them, which no suffix names.
        f = changing(**DEPENDENCY, changed_paths=["json", "docs/payload/__init__.py"])
        d = go(f)
        self.assertEqual((d["state"], d["reason"], d["evidence"], d["admit"]),
                         ("verifying", "awaiting_review", ["pr-review", "*"], REVIEW_IT))
        for path in ("README.md", "LICENSE", ".gitignore", "json.py", "x.so"):
            self.waits_for_review([path])
        # The other side: below the top, outside every package and every other entry, a file is not on the list.
        self.converges(["docs/payload/__init__.py"])

    def test_a_module_of_a_package_at_the_top_of_the_repo_counts_as_a_lens_input(self):  # I-45
        # A package verify imports changes what it does through any of its modules, or the bytecode cached beside them,
        # without its __init__: every package at the top of the repo is listed whole.
        for path in ("sim/whatever.py", "sim/__pycache__/world.cpython-39.pyc", "kernel/__pycache__/x.pyc",
                     "newpkg/__pycache__/__init__.cpython-39.pyc"):
            self.waits_for_review([path])
        d = go(changing(**DEPENDENCY, changed_paths=["sim/whatever.py"]))
        self.assertEqual((d["reason"], d["evidence"], d["admit"]), ("awaiting_review", ["pr-review", "sim/"],
                                                                    dict(REVIEW_IT, content_id="sha256:aaaa")))

    def test_a_pattern_matches_one_name_per_star_in_any_case(self):  # I-45
        # `*` stands for any part of one name, none included, and never for a `/`.
        for path in ("config/rubric-pr-review.json", "config/rubric-.json", ".claude/settings.local.json"):
            self.waits_for_review([path])
        for path in ("config/rubric-a/b.json", ".claude/settings/x.json", "config/rubrics.json",
                     "config/rubric-pr-review.jsonx"):
            self.converges([path])
        # Case is not compared, so the list holds more, never less.
        for path, pattern in (("LIFECYCLE/pull_request.json", "lifecycle/"), (".GitHub/Workflows/Verify.yml", ".github/"),
                              ("config/Rubric-PR-Review.JSON", "config/rubric-*.json"), ("makefile", "Makefile"),
                              (".GITLEAKS.toml", ".gitleaks.toml")):
            self.waits_for_review([path], pattern)
        self.assertTrue(derive.matches("Makefile", "MAKEFILE"))
        self.assertFalse(derive.matches("config/rubric-*.json", "config/rubric-a/b.json"))

    def test_a_pattern_of_several_stars_matches_each_piece_in_order_once(self):  # I-45
        # Each piece between the stars is found in its order, no two overlap, and a star stands for nothing across a
        # `/`, between pieces as at the ends.
        cfg = config(protected_paths=["a*b*c", "x*x"])
        for path in ("abc", "axbyc", "abbc", "xx", "xyx", "XAX"):
            d = go(changing(**DEPENDENCY, changed_paths=[path]), cfg=cfg)
            self.assertEqual(d["reason"], "awaiting_review", path)
        for path in ("axc", "acb", "a/xbc", "ab/c", "x", "xa", "a"):
            d = go(changing(**DEPENDENCY, changed_paths=[path]), cfg=cfg)
            self.assertEqual(d["reason"], "approval_due", path)
        self.assertFalse(derive.matches("a*a", "a"))
        self.assertTrue(derive.matches("a*a", "aa"))

    def test_either_name_of_a_rename_counts(self):  # I-45
        # A rename or a copy gives both of its names: a file moved onto the list, or off it, changes the list.
        for paths in ([(PIN, "docs/pin.yml")], [("docs/pin.yml", PIN)], [("docs/a.md", None), ("docs/pin.yml", PIN)]):
            d = self.waits_for_review(paths)
            self.assertEqual(d["evidence"], ["pr-review", ".github/"], paths)
        self.converges([("docs/new.md", "docs/old.md")])

    def test_a_dependency_update_to_a_workflow_pin_needs_the_model_review(self):  # I-45, decision 0018
        # The dependency bot edits the pin of an Action in the file the verify Lens is read from: the Lens it edits
        # would otherwise be its only judge.
        f = changing(**DEPENDENCY, changed_paths=[PIN])
        d = go(f)
        self.assertEqual((d["state"], d["reason"], d["evidence"], d["admit"]),
                         ("verifying", "awaiting_review", ["pr-review", ".github/"], REVIEW_IT))
        d = go(f, REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"], d["action"]),
                         ("converged", "approval_due", "act", "issue_approval"))
        d = go(dict(f, reviews=APPROVED), REVIEWED)
        self.assertEqual((d["reason"], d["action"]), ("approved", "enqueue"))
        # What the review raised gates it, and a review of another head is none of this one.
        self.assertEqual(go(dict(f, threads=[thread()]), REVIEWED)["reason"], "findings_open")
        self.waits_for_review([PIN], ".github/")
        # The other side: the same update to a path on neither list needs no model review.
        self.converges(["docs/standards/workflows.md"])

    def test_a_queued_change_to_the_list_whose_head_moves_leaves_the_queue(self):  # I-45, I-9
        f = changing(**DEPENDENCY, changed_paths=[PIN], queue=True)
        d = go(dict(f, reviews=APPROVED), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("queued", "in_merge_queue", "nothing"))
        # Its head moved: the review is of the head before, and it leaves the queue whatever approval it holds, one
        # given before the path was on the list among them. Then it waits for the review of this head.
        for reviews in (APPROVED, [review(content="sha256:bbbb", commit="c2")]):
            moved = dict(f, content_id="sha256:bbbb", reviews=reviews)
            d = go(moved, REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["action"]),
                             ("verifying", "awaiting_review", ["pr-review", ".github/"], "act", "dequeue"), reviews)
            d = go(dict(moved, queue=False), REVIEWED)
            self.assertEqual((d["reason"], d["admit"]), ("awaiting_review", dict(REVIEW_IT, content_id="sha256:bbbb")))
        # The other side: an item off the list, approved on this head, is read past a review not yet listed, as before.
        d = go(dict(f, **{"class": "maintainer", "author": "don-petry", "last_pusher": "don-petry"},
                    changed_paths=[changed("docs/notes.md")], content_id="sha256:bbbb",
                    reviews=[review(content="sha256:bbbb", commit="c2")]), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("queued", "in_merge_queue", "nothing"))

    def test_changed_paths_read_short_defer(self):  # I-13, I-20
        # A list read short could leave out the one path on the list.
        for value in ("missing", False, None, "true", 1):
            f = changing(**DEPENDENCY, changed_paths=["docs/notes.md"])
            if value == "missing":
                del f["complete"]["changed_paths"]
            else:
                f["complete"]["changed_paths"] = value
            d = go(f)
            self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"]),
                             (None, "facts_incomplete", ["changed_paths"], "defer"), value)
            d = go(dict(f, queue=True, reviews=APPROVED))
            self.assertEqual((d["reason"], d["outcome"], d["action"]), ("facts_incomplete", "act", "dequeue"), value)
        # The other side: read in full, it converges.
        self.converges(["docs/notes.md"])

    def test_an_unreadable_changed_path_defers_for_the_maintainer(self):  # I-13
        # A path that cannot be read could be a protected one, read as another: no name of it is empty, `.` or `..`.
        unreadable = ("", "/lifecycle/a.json", "lifecycle/", "lifecycle//a.json", "./lifecycle/a.json",
                      "docs/../lifecycle/a.json", "..", ".", "docs/..", 5, None, ["lifecycle/a.json"])
        for path in unreadable:
            for cls in (DEPENDENCY, AGENT):
                d = go(changing(**cls, changed_paths=["docs/notes.md", path]), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"], d["attention"]),
                                 (None, "paths_unreadable", [], "defer", "needs_you"), (path, cls["class"]))
        # So is a list that is no list, or none, and a record that is not one file's: its path and its previous path,
        # null or a path, each given.
        for value in ("missing", None, "docs/notes.md", {"docs/notes.md": True}, 5, ["docs/notes.md"], [{"path": "docs/notes.md"}],
                      [changed("docs/notes.md", "")], [changed("docs/notes.md", "../x")], [changed("docs/notes.md", 5)],
                      [changed("docs/notes.md", "/x")]):
            f = changing(**DEPENDENCY, changed_paths=["docs/a.md"])
            if value == "missing":
                del f["changed_paths"]
            else:
                f["changed_paths"] = value
            d = go(f, REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                             (None, "paths_unreadable", "defer", "needs_you"), value)
            # Queued, it leaves the queue.
            d = go(dict(f, queue=True, reviews=APPROVED), REVIEWED)
            self.assertEqual((d["reason"], d["outcome"], d["action"]), ("paths_unreadable", "act", "dequeue"), value)
        # The other side: a name that only starts or ends with dots is a name.
        for path in ("docs/..lifecycle", "docs/...", "docs/a..b", "docs/.github.md", ("docs/b.md", "docs/..a")):
            self.converges([path])
        # It is read where an unreadable review is: after what needs no paths, a draft or a Hold.
        self.assertEqual(go(changing(changed_paths=None, is_draft=True))["reason"], "draft")
        d = go(changing(changed_paths=[""], label_events=[labelled("factory:hold")]))
        self.assertEqual((d["state"], d["reason"]), ("held", "human_hold"))

    def test_a_list_of_paths_with_a_record_for_each_file_and_no_other(self):  # I-13
        # One record for each file of the diff, each by its own path once. A list of another length, though said to be
        # whole, left a file out or misread one, which could be on the list: a short read that gives a rename's two
        # names as two files, and leaves out the protected file beside it, among them.
        two = {"files": 2, "lines": 40, "truncated": False}
        for paths in ([], [changed("docs/notes.md")], [changed("docs/notes.md"), changed("docs/notes.md")],
                      [changed("docs/new.md", "docs/old.md")],
                      [changed("a.md"), changed("b.md"), changed("c.md")]):
            f = facts(**DEPENDENCY, changed_paths=paths, diff=two)
            d = go(f)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                             (None, "paths_unreadable", "defer", "needs_you"), paths)
            d = go(dict(f, queue=True, reviews=APPROVED))
            self.assertEqual((d["reason"], d["outcome"], d["action"]), ("paths_unreadable", "act", "dequeue"), paths)
        # The other side: a record for each file, a rename's with the name it had before, is whole.
        for paths, files in (([changed("docs/notes.md"), changed("docs/a.md")], 2),
                             ([changed("docs/new.md", "docs/old.md")], 1),
                             ([changed("docs/new.md", "docs/old.md"), changed("docs/old.md")], 2)):
            d = go(facts(**DEPENDENCY, changed_paths=paths, diff=dict(two, files=files)))
            self.assertEqual((d["state"], d["reason"]), ("converged", "approval_due"), paths)

    def test_an_unreadable_list_of_protected_paths_defers_for_the_maintainer(self):  # I-13
        # The list is the Kernel's configuration, built from the base branch's config/hooks.json. Empty or not read,
        # it would let a change to the rules pass as any other.
        f = changing(**DEPENDENCY, changed_paths=[PIN])
        # A pattern that matches nothing is unreadable too: an empty, `.` or `..` name, or a leading separator.
        for rules in ("missing", [], None, ".github/", [""], [5], ["/"], ["./.github/"], [".github//"], ["../.github/"],
                      ["foo//bar"], ["/foo"], ["foo/../bar"],
                      ["/.github/"], [".github/", "lifecycle/../x"]):
            cfg = config()
            if rules == "missing":
                del cfg["protected_paths"]
            else:
                cfg["protected_paths"] = rules
            d = go(f, cfg=cfg)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["attention"]),
                             (None, "protected_paths_unreadable", "defer", "needs_you"), rules)
            d = go(dict(f, queue=True, reviews=APPROVED), REVIEWED, cfg=cfg)
            self.assertEqual((d["reason"], d["action"]), ("protected_paths_unreadable", "dequeue"), rules)
        # The other side: one pattern is a list, and one named twice is named once.
        for rules in ([".github/"], [".github/", ".github/"]):
            d = go(f, cfg=config(protected_paths=rules))
            self.assertEqual((d["reason"], d["evidence"]), ("awaiting_review", ["pr-review", ".github/"]), rules)

    def test_a_decision_names_the_pattern_never_the_path(self):  # I-45
        # A path is text from outside. The Decision names each pattern of the configuration that matched, once, in the
        # configuration's order.
        paths = [PIN, ".github/dependabot.yml", "tests/test_decide.py", "docs/notes.md"]
        d = go(changing(**DEPENDENCY, changed_paths=paths))
        self.assertEqual(d["evidence"], ["pr-review", ".github/", "tests/"])
        spelt = ".GitHub/workflows/a\u202eb.yml"
        d = go(changing(**DEPENDENCY, changed_paths=[spelt]))
        self.assertEqual(d["evidence"], ["pr-review", ".github/"])
        self.assertNotIn(spelt, d["evidence"])


class NotYetHeld(unittest.TestCase):
    """Rules that are decided and that the Kernel does not hold yet. See `pending` in tests/support.py."""


if __name__ == "__main__":
    unittest.main()
