"""The boundary cases of the design, one test each. Add the case here before the code."""
from __future__ import annotations

import datetime
import json
import random
import unittest

from kernel import derive
from kernel.decide import decide
from tests.support import (CONFIG, GREEN, LENS_OF, MAINTAINER, NOW, OTHER_APP, ROOT, config, context, facts, labelled,
                           review, run, thread, unlabelled)
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
PARTS = ("reviews", "threads", "checks", "diff", "runs", "timeline")


def at(minute: int) -> str:
    return "2026-10-11T12:%02d:00Z" % minute


def approvals(count, conclusion="failure", outcome="item", start=20):
    """Approval Runs. An approval is a Run with no Engine: only its `apply` holds the machine user's token."""
    return [run(intent="issue-approval", conclusion=conclusion, outcome=outcome, at=at(start + i), name="a%d" % i)
            for i in range(count)]


def dismissed(rv: dict, by, was: str = "changes_requested") -> dict:
    """`rv` once `by` has dismissed it. GitHub holds its state as dismissed; the timeline says what it was."""
    return dict(rv, state="dismissed", dismissed_by=dict(by) if isinstance(by, dict) else by, dismissed_from=was)


def with_check(i: int, conclusion: str) -> list:
    """Every required check passing but the i-th, which concludes as GitHub says, or is not there ("absent")."""
    if conclusion == "absent":
        return GREEN[:i] + GREEN[i + 1:]
    return GREEN[:i] + [dict(GREEN[i], conclusion=conclusion)] + GREEN[i + 1:]


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
        # The timeline gives each event its time, and they are read by it, however they are listed.
        added, removed = labelled("factory:hold", at=at(3)), unlabelled("factory:hold", at=at(4))
        for events in ([added, removed], [removed, added]):
            self.assertEqual(go(facts(label_events=events), REVIEWED)["action"], "issue_approval")
        added, removed = labelled("factory:hold", at=at(4)), unlabelled("factory:hold", at=at(3))
        for events in ([added, removed], [removed, added]):
            self.assertEqual(go(facts(label_events=events), REVIEWED)["reason"], "human_hold")

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


class NotYetHeld(unittest.TestCase):
    """Rules that are decided and that the Kernel does not hold yet. See `pending` in tests/support.py."""


if __name__ == "__main__":
    unittest.main()
