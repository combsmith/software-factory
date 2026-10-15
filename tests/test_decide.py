"""The boundary cases of the design, one test each. Add the case here before the code."""
from __future__ import annotations

import json
import unittest

from kernel.decide import decide
from tests.support import CONFIG, GREEN, NOW, ROOT, config, context, facts, pending, run, thread
from tools.jsonschema_lite import validate

DECISION_SCHEMA = json.loads((ROOT / "schemas" / "decision.schema.json").read_text())
REVIEWED = [run()]


def go(f, runs=(), ctx=None, cfg=None):
    d = decide(f, list(runs), context() if ctx is None else ctx, CONFIG if cfg is None else cfg, NOW)
    errors = validate(d, DECISION_SCHEMA)
    assert not errors, errors  # every Decision the Kernel emits is a valid one
    return d


class Readability(unittest.TestCase):
    def test_incomplete_facts_never_converge_or_admit(self):  # I-20
        for part in ("reviews", "threads", "checks", "diff"):
            f = facts()
            f["complete"][part] = False
            d = go(f, REVIEWED)
            self.assertEqual((d["outcome"], d["reason"], d["state"]), ("defer", "facts_incomplete", None))

    def test_unreadable_pause_defers(self):  # I-13
        d = go(facts(), ctx={"active_runs": 0, "model_deferred_until": None})
        self.assertEqual((d["outcome"], d["reason"]), ("defer", "pause_unreadable"))

    def test_an_unreadable_pause_stops_approvals_and_merges(self):  # I-7, I-13
        approved = [{"actor": "donpetry-bot", "state": "approved", "commit": "c1", "content_id": "sha256:aaaa"}]
        for reviews in ([], approved):
            unread = {"active_runs": 0, "model_deferred_until": None}
            for ctx in (unread, dict(unread, paused=None)):
                d = go(facts(reviews=reviews), REVIEWED, ctx=ctx)
                self.assertEqual((d["outcome"], d["reason"]), ("defer", "pause_unreadable"), ctx)

    def test_an_unknown_mergeable_never_converges(self):  # I-13, I-20
        approved = [{"actor": "donpetry-bot", "state": "approved", "commit": "c1", "content_id": "sha256:aaaa"}]
        for reviews in ([], approved):
            d = go(facts(mergeable=None, reviews=reviews), REVIEWED)
            self.assertEqual((d["outcome"], d["reason"], d["state"]), ("defer", "mergeable_unreadable", None))
            self.assertEqual(go(facts(reviews=reviews), REVIEWED)["outcome"], "act")

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
        approved = [{"actor": "donpetry-bot", "state": "approved", "commit": "c1", "content_id": "sha256:aaaa"}]
        for reviews in ([], approved):
            d = go(facts(reviews=reviews), REVIEWED, ctx=context(paused=True))
            self.assertEqual((d["outcome"], d["reason"]), ("defer", "paused"))
            self.assertEqual(go(facts(reviews=reviews), REVIEWED)["outcome"], "act")

    def test_draft_is_watched_only(self):
        self.assertEqual(go(facts(is_draft=True))["outcome"], "nothing")

    def test_a_writer_thread_gates_whatever_its_severity(self):
        f = facts(threads=[thread(kind="human", name="don-petry", severity=None)])
        self.assertEqual(go(f, REVIEWED)["reason"], "human_finding")

    def test_a_strangers_thread_does_not_gate(self):
        f = facts(threads=[thread(kind="human", name="stranger", can_write=False, severity=None)])
        self.assertEqual(go(f, REVIEWED)["state"], "converged")


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
        rv = [{"actor": "donpetry-bot", "state": "approved", "commit": "c1", "content_id": "sha256:aaaa"}]
        self.assertEqual(go(facts(reviews=rv), REVIEWED)["action"], "enqueue")

    def test_an_approval_of_other_content_does_not_stand(self):
        rv = [{"actor": "donpetry-bot", "state": "approved", "commit": "c0", "content_id": "sha256:0000"}]
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


class NotYetHeld(unittest.TestCase):
    """Rules that are decided and that the Kernel does not hold yet. See `pending` in tests/support.py."""

    @pending
    def test_a_queued_pull_request_with_no_approval_leaves_the_queue(self):
        self.assertEqual(go(facts(queue=True), REVIEWED)["outcome"], "act")

    @pending
    def test_a_writers_request_for_changes_does_not_converge(self):
        # The facts do not yet say whether a review's author can write; this one is the Maintainer's.
        asked = [{"actor": "don-petry", "state": "changes_requested", "commit": "c1", "content_id": "sha256:aaaa"}]
        self.assertNotEqual(go(facts(reviews=asked), REVIEWED)["state"], "converged")

    @pending
    def test_a_dependency_update_needs_no_model_review(self):
        self.assertEqual(go(facts(**{"class": "dependency"}))["state"], "converged")


if __name__ == "__main__":
    unittest.main()
