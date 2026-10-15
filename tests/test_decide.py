"""The boundary cases of the design, one test each. Add the case here before the code."""
from __future__ import annotations

import json
import unittest

from kernel.decide import decide
from tests.support import CONFIG, GREEN, NOW, ROOT, config, context, facts, review, run, thread
from tools.jsonschema_lite import validate

DECISION_SCHEMA = json.loads((ROOT / "schemas" / "decision.schema.json").read_text())
REVIEWED = [run()]
# A dependency bot's pull request, whose head that bot pushed itself.
DEPENDENCY = {"class": "dependency", "author": "dependabot[bot]", "last_pusher": "dependabot[bot]"}
APPROVED = [review()]
LIMITS = CONFIG["limits"]
# An agent's pull request, which the Maintainer reviews as they would a colleague's (UJ-4).
AGENT = {"class": "agent", "author": "combsmith-sf-dev-lead[bot]", "last_pusher": "combsmith-sf-dev-lead[bot]"}
MAINTAINER = {"kind": "human", "name": "don-petry", "can_write": True}
COLLEAGUE = {"kind": "human", "name": "a-colleague", "can_write": True}
STRANGER = {"kind": "human", "name": "stranger", "can_write": False}
# The reviewer's App: GitHub cannot grant it less than pull_requests: write, so it can dismiss a review.
REVIEWER_APP = {"kind": "lens", "name": "pr-review", "can_write": True}
ADVISORY = {"kind": "lens", "name": "coderabbit", "can_write": False}
# The author's App, whose push dismisses a stale approval. The facts have no kind for an App that is not a Lens yet.
AUTHOR_APP = {"kind": "lens", "name": "dev-lead", "can_write": True}
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


def go(f, runs=(), ctx=None, cfg=None):
    d = decide(f, list(runs), context() if ctx is None else ctx, CONFIG if cfg is None else cfg, NOW)
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
                 ({"labels": ["factory:hold"]}, "held", "human_hold"), ({"is_draft": True}, "draft", "draft")]
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
        go(facts(labels=["factory:hold"]))
        self.assertEqual(go(f, runs), first)
        self.assertEqual(json.dumps([f, runs], sort_keys=True), before)

    def test_admission_is_given_facts_and_never_an_event(self):
        code = decide.__code__
        self.assertEqual(code.co_varnames[:code.co_argcount], ("facts", "runs", "context", "config", "now"))


class HumanControl(unittest.TestCase):
    def test_hold_label_binds(self):  # I-6
        d = go(facts(labels=["factory:hold"]))
        self.assertEqual((d["outcome"], d["reason"], d["attention"]), ("hold", "human_hold", "needs_you"))

    def test_hands_off_is_left_alone(self):
        d = go(facts(labels=["factory:hands-off"]))
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
        self.assertEqual((d["reason"], d["evidence"]), ("check_failed", [GREEN[0]["lens"]]))
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
        # Whatever kind the facts give them, the approver and the bot that opened an agent's or a dependency
        # update's pull request are not people: their dismissal or approval ends no request.
        asked = review(state="changes_requested", **MAINTAINER)
        machine = dict(MAINTAINER, name="donpetry-bot")
        bot = dict(MAINTAINER, name="combsmith-sf-dev-lead[bot]")
        for cls, who in (("agent", machine), ("agent", bot), ("dependency", bot), ("maintainer", machine)):
            f = dict(AGENT, **{"class": cls})
            d = go(facts(**f, reviews=[dismissed(asked, who)]), ANSWERED)
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("addressing", "awaiting_human", ["don-petry"]),
                             (cls, who))
            # Nor does their approval end a request made under their own name, standing or dismissed.
            own = review(state="changes_requested", **who, at=at(12))
            approval = review(**who, at=at(14))
            for later in (approval, dismissed(approval, AUTHOR_APP, "approved")):
                d = go(facts(**f, reviews=[own, later]), ANSWERED)
                self.assertEqual((d["state"], d["reason"], d["evidence"]),
                                 ("addressing", "awaiting_human", [who["name"]]), (cls, who, later["state"]))
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
                 "base_not_protected"), ({"is_draft": True}, "draft"), ({"labels": ["factory:hold"]}, "human_hold"),
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


class Classes(unittest.TestCase):
    def test_outside_item_gets_no_run_until_admitted(self):  # I-25
        d = go(facts(**{"class": "outside"}))
        self.assertEqual((d["outcome"], d["reason"]), ("hold", "outside_not_admitted"))

    def test_admission_lapses_on_the_next_push(self):  # I-36
        f = facts(**{"class": "outside"}, labels=["factory:admit"],
                  admitted_at="2026-10-11T11:00:00Z", last_push_at="2026-10-11T12:00:00Z")
        self.assertEqual(go(f)["reason"], "outside_not_admitted")
        f["admitted_at"] = "2026-10-11T12:30:00Z"
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
        admitted = {"labels": ["factory:admit"], "admitted_at": "2026-10-11T12:30:00Z"}
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
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("addressing", "check_failed", [check["lens"]]))
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
            self.assertNotEqual(d["state"], "converged", check["lens"])
            self.assertNotEqual(d["outcome"], "act", check["lens"])

    def test_a_dependency_update_skips_the_model_review_and_nothing_else(self):
        approved = [review()]
        cases = [({"labels": ["factory:hold"]}, None, ("held", "human_hold", "hold")),
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
        pending = facts(checks=[{"lens": "verify", "conclusion": "pending"}])
        d = go(pending)
        self.assertEqual((d["outcome"], d["reason"]), ("nothing", "awaiting_checks"))
        d = go(facts())
        self.assertEqual(d["admit"], {"role": "pr-review", "intent": "review-change", "content_id": "sha256:aaaa"})

    def test_a_failed_required_check_goes_back_to_the_author(self):
        f = facts(checks=[{"lens": "verify", "conclusion": "failure"}] + GREEN[1:])
        d = go(f, REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["evidence"]), ("addressing", "check_failed", ["verify"]))
        self.assertEqual(d["admit"]["intent"], "fix-findings")

    def test_a_timed_out_required_check_goes_back_to_the_author(self):  # L-39
        # A hung test usually belongs to the content, and attempts bound the fixes.
        for i, check in enumerate(GREEN):
            d = go(facts(checks=with_check(i, "timed_out")), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["evidence"]), ("addressing", "check_failed", [check["lens"]]))
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
                                     ("verifying", "check_unreadable", [check["lens"]], "defer", "needs_you"),
                                     (value, check["lens"]))
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
                                 ("verifying", "awaiting_checks", [check["lens"]], "nothing"), (value, check["lens"]))

    def test_a_failed_check_is_read_before_an_unreadable_or_waiting_one(self):  # I-13
        # A failure is readable and decisive: whatever the check with no verdict would say, the content
        # goes back to the author. Read the other way, an ordinary failure would wait for a person.
        failed, neutral, waiting = (dict(c, conclusion=v) for c, v in zip(GREEN, ("failure", "neutral", "queued")))
        d = go(facts(checks=[failed, neutral, waiting]), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"]),
                         ("addressing", "check_failed", [failed["lens"]], "admit"))
        self.assertEqual(d["admit"]["intent"], "fix-findings")
        d = go(facts(checks=[neutral, waiting]), REVIEWED)
        self.assertEqual((d["reason"], d["evidence"], d["outcome"]), ("check_unreadable", [neutral["lens"]], "defer"))
        d = go(facts(checks=[waiting]), REVIEWED)
        self.assertEqual((d["reason"], d["outcome"]), ("awaiting_checks", "nothing"))

    def test_a_failure_with_cancelled_or_skipped_siblings_goes_back_to_the_author(self):  # I-13
        # GitHub's fail-fast cancels the jobs beside a failure, and a job that needs the failed one is skipped.
        for sibling in ("cancelled", "skipped"):
            for i, check in enumerate(GREEN):
                checks = [dict(c, conclusion="failure" if j == i else sibling) for j, c in enumerate(GREEN)]
                d = go(facts(checks=checks), REVIEWED)
                self.assertEqual((d["state"], d["reason"], d["evidence"], d["outcome"]),
                                 ("addressing", "check_failed", [check["lens"]], "admit"), (sibling, check["lens"]))
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
        f = facts(checks=GREEN + [{"lens": "template-drift", "conclusion": "failure"}])
        self.assertEqual(go(f, REVIEWED)["state"], "converged")

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
            d = go(facts(queue=True, labels=["factory:hold"], reviews=reviews), REVIEWED)
            self.assertEqual((d["state"], d["reason"], d["outcome"], d["action"], d["attention"]),
                             ("held", "human_hold", "act", "dequeue", "needs_you"), reviews)
        # Hands-off means the Factory never acts: the item stays where the Maintainer left it, whatever else holds.
        incomplete = facts()["complete"]
        incomplete["threads"] = False
        for over in ({}, {"labels": ["factory:hold"]}, {"is_draft": True}, {"reviews": []}, {"complete": incomplete},
                     {"checks": with_check(0, "failure")}):
            f = facts(queue=True, **dict({"reviews": APPROVED}, **over))
            f["labels"] = f["labels"] + ["factory:hands-off"]
            d = go(f, REVIEWED)
            self.assertNotEqual(d["outcome"], "act", over)
            self.assertNotIn("action", d)
        d = go(facts(queue=True, labels=["factory:hands-off"], reviews=[]), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "hands_off", "hold"))
        # A held item that is not queued is only held.
        d = go(facts(labels=["factory:hold"], reviews=APPROVED), REVIEWED)
        self.assertEqual((d["state"], d["reason"], d["outcome"]), ("held", "human_hold", "hold"))
        self.assertNotIn("action", d)

    def test_every_hold_takes_a_queued_pull_request_out(self):  # FR-23
        # A Hold the facts establish stops every Effect as a person's does: an outside item whose admission was taken
        # away, a diff too large or read short, an empty one.
        outside = {"class": "outside", "author": "stranger", "last_pusher": "stranger"}
        holds = [(outside, "outside_not_admitted"),
                 (dict(outside, labels=["factory:admit"], admitted_at=at(5), last_push_at=at(10)), "outside_not_admitted"),
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
        d = go(facts(queue=True, reviews=APPROVED, **dict(outside, labels=["factory:admit"], admitted_at=at(5)),
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
        # The other side: not queued, the same read defers and acts on nothing.
        d = go(facts(**AGENT, reviews=[review(), rv]), ANSWERED)
        self.assertEqual((d["reason"], d["outcome"]), ("review_unreadable", "defer"))
        self.assertNotIn("action", d)

    def test_a_check_that_no_longer_passes_takes_it_out_of_the_queue(self):  # I-9, I-27
        # Convergence must still hold on the content: a required check that now fails or gives no verdict, or a
        # conflict with the base. Each is a definite answer, and none ends on its own.
        lens = GREEN[0]["lens"]
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
        stops = [({"labels": ["factory:hold"], "reviews": APPROVED}, "held"),
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
        stops = [({"labels": ["factory:hold"], "reviews": APPROVED}, "human_hold"), ({"reviews": []}, "approval_lost"),
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
        for over, reason in (({"labels": ["factory:hold"], "reviews": APPROVED}, "human_hold"),
                             ({"reviews": []}, "approval_lost")):
            d = go(facts(queue=True, **over), busy)
            self.assertEqual((d["reason"], d["outcome"], d.get("action")), (reason, "act", "dequeue"), reason)
        # The other side: a Run in progress still holds an item that is not queued.
        d = go(facts(reviews=[]), busy)
        self.assertEqual((d["outcome"], d["attention"]), ("nothing", "working"))


class NotYetHeld(unittest.TestCase):
    """Rules that are decided and that the Kernel does not hold yet. See `pending` in tests/support.py."""


if __name__ == "__main__":
    unittest.main()
