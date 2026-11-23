"""Can the tests fail? Break the Kernel on purpose, one rule at a time, and see.

Each mutant removes or inverts one rule. A mutant that the tests do not catch
is a rule nothing is checking. Run with `python3 -m tools.mutants`. The Kernel's
mutants are here; those of every other file are in tools/mutants_of/, one file
to a target, and run after ISSUE.
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import importlib
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile
import unittest

from tools import walk
from tools.mutants_of import common
from tools.verify import SLOW

ROOT = pathlib.Path(__file__).resolve().parent.parent


def moved_after(rel: str, block: str, anchor: str) -> tuple:
    """(old, new) for a mutant that moves `block` down to just after the `anchor` that follows it in `rel`.

    The text between them is read from the file, so it is not written out twice here. If either is not
    found, `old` is text that is not in the file, and the mutant reports itself STALE.
    """
    text = (ROOT / rel).read_text()
    start = text.find(block)
    end = text.find(anchor, start + len(block)) if start >= 0 else -1
    if end < 0:
        return block + anchor, anchor + block
    middle = text[start + len(block):end + len(anchor)]
    return block + middle, middle + block


REVIEW_GUARD = ("    if unreadable_reviews(facts, config):\n"
                '        return {"state": None, "reason": "review_unreadable", "evidence": []}\n')
LABEL_GUARD = ("    if unreadable_labels(facts, config):\n"
               '        return {"state": None, "reason": "label_unreadable", "evidence": []}\n')
STOPS = "for name in (t.LABEL_HOLD, t.LABEL_HANDS_OFF) if name in labels]"
THREAD_GUARD = ("    unread = unreadable_threads(facts, config)\n    if unread:\n"
                '        return {"state": None, "reason": "thread_unreadable", "evidence": unread}\n')
REVIEW_WAIT = '            return {"state": t.VERIFYING, "reason": "awaiting_review", "evidence": [lens] + rules}\n'
PATHS_GUARD = ('    if not readable_paths(facts.get("changed_paths"), facts["diff"]["files"]):\n'
               '        return {"state": None, "reason": "paths_unreadable", "evidence": []}\n')
STAYS = '    if d["reason"] == "approved":\n'
LEFT_ALONE = '    if d["state"] in t.ADMITS_NOTHING or not facts["queue"] or hands_off(facts, config):\n'
DEQUEUE_IF = '    if d.get("dequeue"):\n'
CONTRACT_GUARD = "    stop = contract_reading(facts, config)\n    if stop is not None:\n        return stop\n"
DEQUEUE = ('        return _decision(facts, state, reason, evidence, t.ACT, action="dequeue",'
           ' content_id=facts["content_id"])\n')

# Decision 0232's tests: a pull request stands with its issue, and how the issue stands.
STOOD = ('tests.test_decide.OnlyAPersonEnds.test_a_pull_request_whose_issue_a_person_held_or_closed_is_held_and_leaves_the_queue',)
STANDS_READ = ('tests.test_issue.Stands.test_an_issue_stands_open_held_or_closed_from_its_state_and_its_own_labels',)
STANDS_UNREAD = ('tests.test_issue.Stands.test_what_cannot_be_read_gives_none',)
F849_KERNEL = ("tests.test_issue.Unreadable.test_a_timeline_past_the_ports_bound_defers_on_its_own_code_and_calls_a_person",)
STALE = "tests.test_decide.Staleness."

# Where the boundary cases of decision 0029 are.
REPORTED = "tests.test_decide.AReviewThatReported."
# Where those of decision 0036 are, and the brakes on a pull request's Run, which are asked before them.
UNIDENTIFIED = "tests.test_decide.UnidentifiedRuns."
PUSHER_TESTS = ("tests.test_decide.Convergence.test_an_unreadable_last_pusher_lets_nothing_through",)
RUN_BRAKES = ("    brake = brakes.on_run(_decision, facts, state, evidence, context, intent, since_writer(mine, facts),"
              " limits)\n    if brake:\n        return brake\n")
ACT_BRAKES = ('    brake = brakes.on_act(_decision, facts, state, evidence, context, action, since, config["limits"],\n'
              "                          acted_since_writer(mine, facts))\n    if brake:\n        return brake\n")
# The deferral for an unidentified Run in decide.py's _act, the first after the brakes it follows; and the call that
# reads every deferral of a Run, the first after the brakes in decide.py's _decide and in issue.py's decide.
UNIDENTIFIED_DEFERS = '        return _decision(facts, state, "run_unidentified", evidence, t.DEFER)\n'
DEFERRAL_CALL = ("    stop = run_deferral(_decision, facts, state, evidence, context, now, limits)\n"
                 "    if stop:\n        return stop\n")
COVERAGE = "tests.test_coverage.Coverage."

# An issue's State (kernel/issue.py, decision 0028), in a list of its own so that the pull request's work, which adds
# to MUTANTS below, never touches the same lines. Each is run against tests.test_issue first.
ISSUE_PY, ISSUE_TESTS = "kernel/issue.py", ("tests.test_issue",)
MERGE_UNDER_STOP_TESTS = ("tests.test_issue.Done.test_a_merge_read_while_a_person_closed_or_held_the_issue_is_never_done",)
PLATFORM_CLOSE_TESTS = ("tests.test_issue.Done.test_a_platform_close_keeps_the_state_a_person_set",)
CLOSE_TIME_TESTS = ("tests.test_issue.Done.test_a_close_or_a_reopening_without_its_time_cannot_be_read",)
# Issue 218: the guard on a count of active Runs, the same on both sides.
COUNT_GUARD = "    if type(active) is not int or active < 0:\n"
COUNT_TESTS = ("tests.test_decide.Ceilings.test_an_active_runs_that_is_no_count_defers_and_raises_nothing",)
ISSUE_COUNT_TESTS = ("tests.test_issue.Investigation.test_an_active_runs_that_is_no_count_defers_and_raises_nothing",)
# What an issue's Run in flight counts, and the ceilings asked of the Run its State wants; and the exploration of an
# issue's changes of State, which a mutant may name as a second killer.
ISSUE_DONE = '            done = [r for r in since_writer(mine, facts) if r["status"] == "completed"]\n'
ISSUE_CEILINGS = "            held = brakes.run_ceilings(_decision, facts, evidence, wanted[1], done, limits)\n"
ISSUE_EXPLORED = "tests.test_transitions.AnyLifecycle.test_an_issue_explored_is_held_to_the_issue_lifecycle"
ISSUE = [
    # What is read short or cannot be read, before row 1.
    ("an issue's lists read short are trusted", ISSUE_PY,
     "    gaps = [name for name in ISSUE_READ_IN_FULL if name in unread_lists(facts) or (name == \"timeline\" and bounded is not False)]\n",
     "    gaps = []\n", ISSUE_TESTS),
    ("an issue's flag that is not exactly true counts as whole", ISSUE_PY,
     "if flags.get(name) is not True]", "if not flags.get(name, True)]", ISSUE_TESTS),
    ("an issue's unreadable state is trusted", ISSUE_PY,
     '    if facts.get("state") not in ISSUE_STATES or not readable_close(facts):\n', "    if False:\n", ISSUE_TESTS),
    ("an issue's unreadable author is trusted", ISSUE_PY,
     '    if not whole_actor(facts.get("author"), config):\n', "    if False:\n", ISSUE_TESTS),
    ("an issue's unreadable label event is trusted", ISSUE_PY,
     '    if not readable_events(facts.get("label_events"), config):\n', "    if False:\n", ISSUE_TESTS),
    ("an issue's control labels are not read from terms.py", ISSUE_PY,
     "    return tuple(t.CONTROL_LABELS) + (LABEL_TRIAGE, LABEL_READY)\n", "    return (LABEL_TRIAGE, LABEL_READY)\n",
     ISSUE_TESTS),
    ("an issue's unreadable label names are trusted", ISSUE_PY,
     '    if not readable_names(facts.get("label_names")):\n', "    if False:\n", ISSUE_TESTS),
    ("an issue's unreadable linked pull request is trusted", ISSUE_PY,
     ' and all(readable_link(p, config) for p in facts["linked"])):\n', "):\n", ISSUE_TESTS),
    ("a linked pull request numbered 1 cannot be read", ISSUE_PY,
     'entry["number"] >= 1', 'entry["number"] > 1', ISSUE_TESTS),
    ("a linked pull request's closing time is not read", ISSUE_PY,
     'for when in ("merged_at", "closed_at")', 'for when in ("merged_at",)', ISSUE_TESTS),
    ("an issue's unreadable life is trusted", ISSUE_PY,
     '    if not (is_time(facts.get("life_started_at")) and facts.get("reopened_last_by") in REOPENED_BY\n'
     "            and readable_reopening(facts)):\n", "    if False:\n", ISSUE_TESTS),
    ("a content id of too few digits is read", ISSUE_PY,
     "len(CONTENT_FEWEST) <= len(digits) <= len(CONTENT_MOST)", "len(digits) <= len(CONTENT_MOST)", ISSUE_TESTS),
    ("a content id of too many digits is read", ISSUE_PY,
     "len(CONTENT_FEWEST) <= len(digits) <= len(CONTENT_MOST)", "len(CONTENT_FEWEST) <= len(digits)", ISSUE_TESTS),
    ("an issue's unreadable content is trusted", ISSUE_PY,
     "    if not readable_content(facts):\n", "    if False:\n", ISSUE_TESTS),
    ("an issue's unreadable type is trusted", ISSUE_PY,
     "    if not readable_type(facts):\n", "    if False:\n", ISSUE_TESTS),
    ("an issue's missing type is read as none", ISSUE_PY,
     '    if not ("type" in facts and (', "    if not ((", ISSUE_TESTS),
    ("an issues block that cannot be read is trusted", ISSUE_PY,
     "    if not readable_issues(config):\n", "    if False:\n", ISSUE_TESTS),
    ("an issues block's date is not read", ISSUE_PY,
     ' or is_time(issues.get("served_from")))', " or True)", ISSUE_TESTS),
    ("an issues block's labels left out are not read", ISSUE_PY,
     '            and readable_names(issues.get("left_out_labels")) and', "            and", ISSUE_TESTS),
    ("an issues block's types left out are not read", ISSUE_PY,
     ' and readable_names(issues.get("left_out_types"))):', "):", ISSUE_TESTS),
    ("an issues block's Apps are not read", ISSUE_PY,
     "    return isinstance(apps, dict) and all(", "    return True or all(", ISSUE_TESTS),
    ("an issues block's App may be any value", ISSUE_PY,
     '        name in apps and (apps[name] is None or (isinstance(apps[name], str) and apps[name] != ""))',
     "        name in apps", ISSUE_TESTS),
    # Row 1: done. Issue 227, the Maintainer's ruling: a merge read while a person closed or held the issue is never
    # done, and the reason names the contradiction.
    ("a linked merge is not done", ISSUE_PY, "    if merged:\n", "    if False:\n", ISSUE_TESTS),
    ("a merge after a person's close is done", ISSUE_PY,
     '        if facts["closed_first_at"] is not None and facts["closed_first_at"] < first:\n', "        if False:\n",
     MERGE_UNDER_STOP_TESTS),
    ("a close in the merge's second is a person's", ISSUE_PY,
     'facts["closed_first_at"] < first:', 'facts["closed_first_at"] <= first:', MERGE_UNDER_STOP_TESTS),
    ("a first close before its life is read", ISSUE_PY,
     "    return is_time(when) and (not is_time(began) or began <= when)\n", "    return is_time(when)\n",
     CLOSE_TIME_TESTS),
    ("a close after the reopening that undid it is read", ISSUE_PY,
     "    return undone <= when\n", "    return True\n", CLOSE_TIME_TESTS),
    ("an open issue nobody but a writer reopened may carry a close of this life", ISSUE_PY,
     '    if facts["state"] == "open" and facts.get("reopened_last_by") != "other":\n        return when is None\n', "",
     CLOSE_TIME_TESTS),
    ("an open issue an outsider reopened may carry no close", ISSUE_PY,
     '    if facts["state"] == "open" and facts.get("reopened_last_by") != "other":\n',
     '    if facts["state"] == "open":\n', CLOSE_TIME_TESTS),
    ("a merge after an outsider's reopening is done", ISSUE_PY,
     '        if facts["reopened_last_by"] == "other" and facts["reopened_last_at"] <= first:\n', "        if False:\n",
     MERGE_UNDER_STOP_TESTS),
    ("an outsider's reopening after the merge is read as before it", ISSUE_PY,
     '"other" and facts["reopened_last_at"] <= first:', '"other":', MERGE_UNDER_STOP_TESTS),
    ('a merge while a Hold stands is done', ISSUE_PY, '        if stopped_before(facts, first) and not placed_by_a_person(standing_labels(past), past):\n', '        if False:\n', MERGE_UNDER_STOP_TESTS),
    ("a merge under a person's hands-off is a Hold", ISSUE_PY, '        if stopped_before(facts, first) and not placed_by_a_person(standing_labels(past), past):\n', '        if stopped_before(facts, first):\n', MERGE_UNDER_STOP_TESTS),
    ("a person's hands-off placed after the merge excuses the Hold that stood", ISSUE_PY, 'stopped_before(facts, first) and not placed_by_a_person(standing_labels(past), past):', 'stopped_before(facts, first) and not a_persons_hands_off(labels, facts, drafts):', MERGE_UNDER_STOP_TESTS),
    ("a person's hands-off lifted since the merge excuses nothing", ISSUE_PY, '        past = as_of(facts, first)\n        if hands_off_stood', '        past = facts\n        if hands_off_stood', MERGE_UNDER_STOP_TESTS),
    ("a person's hands-off placed in the merge's second did not stand at it", ISSUE_PY,
     '                                    if ev["label"] in t.CONTROL_LABELS and ev["at"] <= when])\n',
     '                                    if ev["label"] in t.CONTROL_LABELS and ev["at"] < when])\n',
     MERGE_UNDER_STOP_TESTS),
    ("a label the Kernel does not read is read for its time", ISSUE_PY,
     'if ev["label"] in t.CONTROL_LABELS and ev["at"] <= when', 'if ev["at"] <= when', MERGE_UNDER_STOP_TESTS),
    ("a person's removal in the merge's second released the Hold that stood", ISSUE_PY,
     'ev["at"] > when and is_person(ev["by"])\n', 'ev["at"] >= when and is_person(ev["by"])\n', MERGE_UNDER_STOP_TESTS),
    ("a Hold an App took off after the merge was released", ISSUE_PY,
     'ev["at"] > when and is_person(ev["by"])\n', 'ev["at"] > when\n', MERGE_UNDER_STOP_TESTS),
    ("the last merge in the life is read instead of the first", ISSUE_PY,
     '        first = min(p["merged_at"] for p in merged)\n', '        first = max(p["merged_at"] for p in merged)\n',
     MERGE_UNDER_STOP_TESTS),
    ('a Hold placed after the merge holds it', ISSUE_PY, '    past = as_of(facts, when)\n    return [name', '    past = facts\n    return [name', MERGE_UNDER_STOP_TESTS),
    ('a Hold a person released since the merge holds it', ISSUE_PY, ' and not released_since(facts, name, when)]\n', ']\n', MERGE_UNDER_STOP_TESTS),
    ("an issue's close time is not read", ISSUE_PY,
     '    if facts.get("state") not in ISSUE_STATES or not readable_close(facts):\n',
     '    if facts.get("state") not in ISSUE_STATES:\n', CLOSE_TIME_TESTS),
    ("an issue's reopening time is not read", ISSUE_PY,
     "            and readable_reopening(facts)):\n", "            ):\n", CLOSE_TIME_TESTS),
    ("a writer's reopening at another time than its life's start is read", ISSUE_PY,
     '        return when == facts["life_started_at"]\n', '        return when >= facts["life_started_at"]\n',
     CLOSE_TIME_TESTS),
    ("an issue's merged_while_held calls nobody", ISSUE_PY, '    "merged_while_held",\n', "", MERGE_UNDER_STOP_TESTS),
    ("an issue's merged_while_declined calls nobody", ISSUE_PY, '    "merged_while_declined",\n', "",
     MERGE_UNDER_STOP_TESTS),
    # Issue 542: a linked draft is read as it stood at the merge that closed its issue (decision 0141).
    ("a draft's hands-off at the merge is passed", ISSUE_PY, '    return placed_by_a_person(standing_labels(past), past) and not released_since(facts, t.LABEL_HANDS_OFF, when)\n', '    return any(placed_by_a_person(standing_labels(as_of(q, when)), as_of(q, when)) for q in [facts] + facts["linked"])\n', ('tests.test_issue.Done.test_a_linked_drafts_labels_leave_a_done_issue_done',)),
    # Issue 970: row 1 reads no linked pull request's draft flag at the merge, as it stood or as it stands.
    ("row 1 holds an issue under a Hold on a pull request that was a draft at the merge", ISSUE_PY,
     '        if stopped_before(facts, first) and not placed_by_a_person(standing_labels(past), past):\n',
     '        if (stopped_before(facts, first) or any(t.LABEL_HOLD in standing_labels(as_of(p, first))\n'
     '                                                and ([e["action"] == "ready_for_review" for e in p["draft_events"] if e["at"] > first]\n'
     '                                                     + [p["draft"]])[0] for p in facts["linked"])) \\\n'
     '                and not placed_by_a_person(standing_labels(past), past):\n',
     ('tests.test_issue.Done.test_a_linked_drafts_labels_leave_a_done_issue_done',)),
    ("a flag that disagrees with its last event is read", ISSUE_PY,
     '    return not events or (events[-1]["action"] == DRAFTED) == entry["draft"]\n',
     '    return True\n', ("tests.test_issue.Done.test_a_linked_drafts_labels_leave_a_done_issue_done", "tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers")),
    ("a person's hands-off on a linked draft at the merge excuses the issue's Hold", ISSUE_PY,
     '        if stopped_before(facts, first) and not placed_by_a_person(standing_labels(past), past):\n',
     '        if stopped_before(facts, first) and not any(placed_by_a_person(standing_labels(as_of(q, first)), as_of(q, first))\n'
     '                                                   for q in [facts] + [p for p in links if p["opened_at"] <= first]):\n',
     ("tests.test_issue.Done.test_a_merge_read_while_a_person_closed_or_held_the_issue_is_never_done",)),
    # Issue 551: a link by hand and a type change, each read whole with its time, and two links by hand before the
    # first merge's second leave the issue held (decision 0132's same second aside).
    ("a pull request's link events are not read", ISSUE_PY,
     'readable_draft_events(entry) and readable_link_events(entry) and', 'readable_draft_events(entry) and',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('link events that are no list are read', ISSUE_PY,
     '    events = entry.get("link_events")\n    if not isinstance(events, list):\n        return False\n', '    events = entry.get("link_events") or []\n',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a link event may be anything', ISSUE_PY,
     'isinstance(ev, dict) and ev.get("action") in LINK_ACTIONS and is_time(ev.get("at"))', 'isinstance(ev, dict) and "at" in ev',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('the first link event may be an unlinking', ISSUE_PY,
     'events[0]["action"] != CONNECTED or ', '',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a link may be made before the pull request opened', ISSUE_PY,
     ' or entry["opened_at"] > events[0]["at"])', ')',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a link in the opening second is refused', ISSUE_PY,
     'entry["opened_at"] > events[0]["at"]', 'entry["opened_at"] >= events[0]["at"]',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('link events may be out of order', ISSUE_PY,
     'return not any(later["at"] < ev["at"] or later["action"] == ev["action"] for', 'return not any(later["action"] == ev["action"] for',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a link event may repeat the last', ISSUE_PY,
     'return not any(later["at"] < ev["at"] or later["action"] == ev["action"] for', 'return not any(later["at"] < ev["at"] for',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ("an issue's type events are not read", ISSUE_PY,
     '    return readable_type_events(facts)\n', '    return True\n',
     ('tests.test_issue.Unreadable.test_an_issues_type_changes_are_read_whole_or_defer',)),
    ('type events that are no list are read', ISSUE_PY,
     '    events = facts.get("type_events")\n    if not isinstance(events, list):\n        return False\n', '    events = facts.get("type_events") or []\n',
     ('tests.test_issue.Unreadable.test_an_issues_type_changes_are_read_whole_or_defer',)),
    ("a type event's time may be anything", ISSUE_PY,
     'isinstance(ev, dict) and is_time(ev.get("at")) and all(', 'isinstance(ev, dict) and all(',
     ('tests.test_issue.Unreadable.test_an_issues_type_changes_are_read_whole_or_defer',)),
    ("a type event's names may be anything", ISSUE_PY,
     'name in ev and (ev[name] is None or (isinstance(ev[name], str) and ev[name] != "")) for name in names)', 'name in ev for name in names)',
     ('tests.test_issue.Unreadable.test_an_issues_type_changes_are_read_whole_or_defer',)),
    ('type events may be out of order', ISSUE_PY,
     'if any(later["at"] < ev["at"] or later["from"] != ev["to"]', 'if any(later["from"] != ev["to"]',
     ('tests.test_issue.Unreadable.test_an_issues_type_changes_are_read_whole_or_defer',)),
    ('a type event may not follow the last', ISSUE_PY,
     'if any(later["at"] < ev["at"] or later["from"] != ev["to"]', 'if any(later["at"] < ev["at"]',
     ('tests.test_issue.Unreadable.test_an_issues_type_changes_are_read_whole_or_defer',)),
    ('the last type event may leave another type', ISSUE_PY,
     '    return not events or events[-1]["to"] == facts["type"]\n', '    return True\n',
     ('tests.test_issue.Unreadable.test_an_issues_type_changes_are_read_whole_or_defer',)),
    ('two links by hand at the merge are not read', ISSUE_PY,
     '        if len(stood) > 1 and not placed_by_a_person(standing_labels(past), past):\n            return out(t.HELD, "merged_while_held", stood)\n', '',
     ('tests.test_issue.Done.test_two_links_by_hand_before_the_merge_leave_the_issue_held',)),
    ('two links by hand at the merge are read as before, in the exploration', ISSUE_PY,
     '        if len(stood) > 1 and not placed_by_a_person(standing_labels(past), past):\n            return out(t.HELD, "merged_while_held", stood)\n',
     '        if False:\n            return out(t.HELD, "merged_while_held", stood)\n',
     ('tests.test_transitions.AnyLifecycle.test_the_queues_merge_from_held_or_not_served_keeps_the_state',)),
    ('one link by hand is two at the merge', ISSUE_PY,
     '        if len(stood) > 1 and', '        if len(stood) > 0 and',
     ('tests.test_issue.Done.test_two_links_by_hand_before_the_merge_leave_the_issue_held',)),
    ("a link in the merge's second stands before it", ISSUE_PY,
     'before = [ev for ev in entry["link_events"] if ev["at"] < when]', 'before = [ev for ev in entry["link_events"] if ev["at"] <= when]',
     ('tests.test_issue.Done.test_two_links_by_hand_before_the_merge_leave_the_issue_held',)),
    ('an unlinking before the merge leaves the link', ISSUE_PY,
     'return bool(before) and before[-1]["action"] == CONNECTED', 'return bool(before)',
     ('tests.test_issue.Done.test_two_links_by_hand_before_the_merge_leave_the_issue_held',)),
    ('a link with no time stands before the merge', ISSUE_PY,
     'return bool(before) and before[-1]["action"] == CONNECTED', 'return not before or before[-1]["action"] == CONNECTED',
     ('tests.test_issue.Done.test_two_links_by_hand_before_the_merge_leave_the_issue_held',)),
    ('a pull request closed before the merge is a link at it', ISSUE_PY,
     '                 and not closed_before(p, first)]', '                 ]',
     ('tests.test_issue.Done.test_two_links_by_hand_before_the_merge_leave_the_issue_held',)),
    ("a pull request closed in the merge's second is no link at it", ISSUE_PY,
     '    before = [ev for ev in entry["close_events"] if ev["at"] < when]', '    before = [ev for ev in entry["close_events"] if ev["at"] <= when]',
     ('tests.test_issue.Done.test_two_links_by_hand_before_the_merge_leave_the_issue_held',)),
    # Issue 672: a linked pull request's closes and reopenings, read whole, and a rival read as it stood at the merge.
    ("a pull request's close events are not read", ISSUE_PY,
     'and readable_close_events(entry, config) and readable_events(', 'and readable_events(', ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a pull request with no close events has none', ISSUE_PY,
     '    events = entry.get("close_events")\n', '    events = entry.get("close_events", [])\n',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('close events that are no list are read', ISSUE_PY,
     '    events = entry.get("close_events")\n    if not isinstance(events, list):\n        return False\n',
     '    events = entry.get("close_events") or []\n', ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a close event may be anything', ISSUE_PY,
     'isinstance(ev, dict) and ev.get("action") in CLOSE_ACTIONS and is_time(ev.get("at"))', 'isinstance(ev, dict)', ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ("a close event's actor may be anything", ISSUE_PY,
     '\n               and whole_actor(ev.get("by"), config) for ev in events):', ' for ev in events):',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('the first close event may be a reopening', ISSUE_PY,
     'events[0]["action"] != CLOSED or not entry["opened_at"] <= events[0]["at"]', 'not entry["opened_at"] <= events[0]["at"]', ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a close may come before the pull request opened', ISSUE_PY,
     'events[0]["action"] != CLOSED or not entry["opened_at"] <= events[0]["at"]', 'events[0]["action"] != CLOSED', ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a close in the opening second is refused', ISSUE_PY,
     'not entry["opened_at"] <= events[0]["at"]', 'not entry["opened_at"] < events[0]["at"]',
     ('tests.test_issue.Stale.test_a_link_whose_opening_merge_and_close_are_out_of_order_defers',)),
    ('close events may be out of order or repeat the last', ISSUE_PY,
     '    if any(b["at"] < a["at"] or b["action"] == a["action"] for a, b in zip(events, events[1:])):\n        return False\n',
     '', ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('an open pull request may end on a close', ISSUE_PY,
     '        return last is None or last["action"] != CLOSED\n', '        return True\n', ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a closed pull request need not end on its close', ISSUE_PY,
     '    return (last is not None and last["action"] == CLOSED\n', '    return (last is not None\n',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a close long after closed_at is read', ISSUE_PY,
     '0 <= seconds(last["at"]) - seconds(entry["closed_at"]) < bound)', '0 <= seconds(last["at"]) - seconds(entry["closed_at"]))',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('an unreadable limit lets a close trail closed_at', ISSUE_PY,
     '    bound = lag if type(lag) is int and 1 <= lag else 1\n', '    bound = lag if type(lag) is int else 600\n',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a close at the limit after closed_at is read', ISSUE_PY,
     '0 <= seconds(last["at"]) - seconds(entry["closed_at"]) < bound)', '0 <= seconds(last["at"]) - seconds(entry["closed_at"]) <= bound)',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a merged pull request may be reopened and closed after its merge', ISSUE_PY,
     '    if merged is not None and len([ev for ev in events if ev["at"] >= merged]) != 1:\n', '    if False:\n',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a close before closed_at is read', ISSUE_PY,
     '0 <= seconds(last["at"]) - seconds(entry["closed_at"]) < bound)', 'seconds(last["at"]) - seconds(entry["closed_at"]) < bound)',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a close a second after closed_at is refused', ISSUE_PY,
     '0 <= seconds(last["at"]) - seconds(entry["closed_at"]) < bound)', '0 == seconds(last["at"]) - seconds(entry["closed_at"]))',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ("a rival's close is read as it stands now", ISSUE_PY,
     '                 and not closed_before(p, first)]', '                 and (p["closed_at"] is None or p["closed_at"] >= first)]',
     ('tests.test_issue.Done.test_two_links_by_hand_before_the_merge_leave_the_issue_held',)),
    ('a reopening before the merge leaves the rival closed', ISSUE_PY,
     '    return bool(before) and before[-1]["action"] == CLOSED\n', '    return any(ev["action"] == CLOSED for ev in before)\n',
     ('tests.test_issue.Done.test_two_links_by_hand_before_the_merge_leave_the_issue_held',)),
    ('an admission after the merge counts toward two links', ISSUE_PY,
     'if is_linked(as_of(p, first))', 'if is_linked(p)',
     ('tests.test_issue.Done.test_two_links_by_hand_before_the_merge_leave_the_issue_held',)),
    ('a link unlinked since the merge still holds', ISSUE_PY,
     '                 and not any(ev["action"] != CONNECTED and ev["at"] >= first for ev in p["link_events"])\n', '                 and True\n',
     ('tests.test_issue.Done.test_two_links_by_hand_before_the_merge_leave_the_issue_held',)),
    ('an unlinking in the merge\'s second leaves the link', ISSUE_PY,
     'ev["action"] != CONNECTED and ev["at"] >= first for ev in p["link_events"])', 'ev["action"] != CONNECTED and ev["at"] > first for ev in p["link_events"])',
     ('tests.test_issue.Done.test_two_links_by_hand_before_the_merge_leave_the_issue_held',)),
    ('a link made again after an unlinking since the merge holds again', ISSUE_PY,
     'and not any(ev["action"] != CONNECTED and ev["at"] >= first for ev in p["link_events"])', 'and p["link_events"][-1]["action"] == CONNECTED',
     ('tests.test_issue.Done.test_two_links_by_hand_before_the_merge_leave_the_issue_held',)),
    ('a pull request listed twice is read', ISSUE_PY,
     '    if len({p["number"] for p in facts["linked"]}) != len(facts["linked"]):\n        return out(None, "linked_unreadable", [])\n', '',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a type change that changes nothing is read', ISSUE_PY,
     '    if any(ev["from"] == ev["to"] for ev in events):     # each changes the type, as a link event changes the link\n        return False\n', '',
     ('tests.test_issue.Unreadable.test_an_issues_type_changes_are_read_whole_or_defer',)),
    ('a person\'s hands-off beside two links does not excuse them', ISSUE_PY,
     ' and not placed_by_a_person(standing_labels(past), past):\n            return out(t.HELD, "merged_while_held", stood)', ':\n            return out(t.HELD, "merged_while_held", stood)',
     ('tests.test_issue.Done.test_two_links_by_hand_before_the_merge_leave_the_issue_held',)),
    # Issue 552: a closing keyword's link stood at the merge where a span of it, as the passes saw it, covered the
    # merge's second; rows 4 to 7 read the links as they stand.
    ("a pull request's keyword is not read", ISSUE_PY,
     ' and readable_keyword(entry)\n',
     '\n',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a keyword of any kind is read', ISSUE_PY,
     'type(entry.get("keyword")) is bool and isinstance(spans, list)',
     'isinstance(spans, list)',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('keyword spans that are no list are read', ISSUE_PY,
     ' and isinstance(spans, list)):',
     '):',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ("a span's seen time may be anything", ISSUE_PY,
     'is_time(span.get("seen_at")) and "gone_at" in span',
     '"gone_at" in span',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a span without its end is read', ISSUE_PY,
     ' and "gone_at" in span\n',
     '\n',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ("a span's end may be anything", ISSUE_PY,
     '(span["gone_at"] is None or is_time(span["gone_at"]) and span["gone_at"] >= span["seen_at"])',
     'True',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a span may end before it began', ISSUE_PY,
     ' and span["gone_at"] >= span["seen_at"]) for span in spans)',
     ') for span in spans)',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a keyword may be seen before the pull request opened', ISSUE_PY,
     'if spans and entry["opened_at"] > spans[0]["seen_at"]:',
     'if False:',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a keyword seen in the opening second is refused', ISSUE_PY,
     'entry["opened_at"] > spans[0]["seen_at"]',
     'entry["opened_at"] >= spans[0]["seen_at"]',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a span left open before another is read', ISSUE_PY,
     'if any(span["gone_at"] is None or later["seen_at"] <= span["gone_at"]',
     'if any(later["seen_at"] <= span["gone_at"] if span["gone_at"] is not None else False',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('overlapping spans are read', ISSUE_PY,
     ' or later["seen_at"] <= span["gone_at"] for span, later',
     ' for span, later',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a span begun in the second the last ended is read', ISSUE_PY,
     'later["seen_at"] <= span["gone_at"]',
     'later["seen_at"] < span["gone_at"]',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a span ended in the second it began is refused', ISSUE_PY,
     ' and span["gone_at"] >= span["seen_at"]) for span in spans)',
     ' and span["gone_at"] > span["seen_at"]) for span in spans)',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a pull request listed for nothing is read', ISSUE_PY,
     '    return entry["keyword"] or bool(spans) or bool(entry["link_events"]) or entry["closed_issue_at"] is not None\n',
     '    return True\n',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a keyword once seen is listed for nothing', ISSUE_PY,
     ' or bool(spans) or',
     ' or',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a pull request linked by hand alone is refused', ISSUE_PY,
     ' or bool(entry["link_events"]) or entry["closed_issue_at"]',
     ' or entry["closed_issue_at"]',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a closer whose keyword was taken out is refused', ISSUE_PY,
     ' or entry["closed_issue_at"] is not None\n',
     '\n',
     ('tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers',)),
    ('a keyword link is not read at the merge', ISSUE_PY,
     ' or keyword_stood(p, first))\n',
     ')\n',
     ('tests.test_issue.Done.test_a_keyword_link_a_pass_saw_before_the_merge_is_a_link_at_it',)),
    ("a keyword first seen in the merge's second stands before it", ISSUE_PY,
     'span["seen_at"] < when and',
     'span["seen_at"] <= when and',
     ('tests.test_issue.Done.test_a_keyword_link_a_pass_saw_before_the_merge_is_a_link_at_it',)),
    ('a keyword seen gone before the merge still stands', ISSUE_PY,
     '(span["gone_at"] is None or span["gone_at"] >= when)',
     'True',
     ('tests.test_issue.Done.test_a_keyword_link_a_pass_saw_before_the_merge_is_a_link_at_it',)),
    ("a keyword seen gone in the merge's second is no link at it", ISSUE_PY,
     'span["gone_at"] >= when)',
     'span["gone_at"] > when)',
     ('tests.test_issue.Done.test_a_keyword_link_a_pass_saw_before_the_merge_is_a_link_at_it',)),
    ('only the first span of a keyword is read', ISSUE_PY,
     'for span in entry["keyword_spans"])',
     'for span in entry["keyword_spans"][:1])',
     ('tests.test_issue.Done.test_a_keyword_link_a_pass_saw_before_the_merge_is_a_link_at_it',)),
    ('only the last span of a keyword is read', ISSUE_PY,
     'for span in entry["keyword_spans"])',
     'for span in entry["keyword_spans"][-1:])',
     ('tests.test_issue.Done.test_a_keyword_link_a_pass_saw_before_the_merge_is_a_link_at_it',)),
    ('an edited-out keyword still opens a link in rows 4 to 7', ISSUE_PY,
     'if p["open"] and linked_now(p)]',
     'if p["open"]]',
     ('tests.test_issue.Done.test_a_keyword_link_a_pass_saw_before_the_merge_is_a_link_at_it',)),
    ('a link by hand undone is still linked now', ISSUE_PY,
     'entry["keyword"] or bool(entry["link_events"]) and entry["link_events"][-1]["action"] == CONNECTED',
     'entry["keyword"] or bool(entry["link_events"])',
     ('tests.test_issue.Done.test_a_keyword_link_a_pass_saw_before_the_merge_is_a_link_at_it',)),
    ('a link by hand alone is no link now', ISSUE_PY,
     '    return entry["keyword"] or bool(entry["link_events"]) and entry["link_events"][-1]["action"] == CONNECTED\n',
     '    return entry["keyword"]\n',
     ('tests.test_issue.Done.test_a_keyword_link_a_pass_saw_before_the_merge_is_a_link_at_it',)),
    ('an unlinking since the merge releases a keyword link too', ISSUE_PY,
     '                 and (linked_by_hand_before(p, first)\n                      and not any(ev["action"] != CONNECTED and ev["at"] >= first for ev in p["link_events"])\n                      or keyword_stood(p, first))\n',
     '                 and (linked_by_hand_before(p, first) or keyword_stood(p, first))\n                 and not any(ev["action"] != CONNECTED and ev["at"] >= first for ev in p["link_events"])\n',
     ('tests.test_issue.Done.test_a_keyword_link_a_pass_saw_before_the_merge_is_a_link_at_it',)),
    # Issue 552, ruling (2) (a): a person's close of a rival, its event the lag after the merge's second, releases the
    # hold, for good.
    ("a person's close of the rival after the merge releases nothing", ISSUE_PY,
     '\n                 and not closed_by_a_person_after(p, first, config)', '',
     ('tests.test_issue.Done.test_a_persons_close_of_the_rival_after_the_merge_releases_the_hold',)),
    ("anyone's close of the rival after the merge releases the hold", ISSUE_PY,
     'CLOSED and is_person(ev["by"]) and', 'CLOSED and',
     ('tests.test_issue.Done.test_a_persons_close_of_the_rival_after_the_merge_releases_the_hold',)),
    ("an App's or a Lens's close of the rival after the merge releases the hold", ISSUE_PY,
     'CLOSED and is_person(ev["by"]) and', 'CLOSED and (is_person(ev["by"]) or ev["by"]["kind"] in APP_KINDS) and',
     ('tests.test_issue.Done.test_a_persons_close_of_the_rival_after_the_merge_releases_the_hold',)),
    ("a reopening after the merge releases the hold", ISSUE_PY,
     'return any(ev["action"] == CLOSED and is_person', 'return any(is_person',
     ('tests.test_issue.Done.test_a_persons_close_of_the_rival_after_the_merge_releases_the_hold',)),
    ("a merge's own close releases the hold", ISSUE_PY,
     ' and (merged is None or ev["at"] < merged)\n               and seconds', '\n               and seconds',
     ('tests.test_issue.Done.test_a_persons_close_of_the_rival_after_the_merge_releases_the_hold',)),
    ("a close in the merge's own second releases the hold", ISSUE_PY,
     '(merged is None or ev["at"] < merged)', '(merged is None or ev["at"] <= merged)',
     ('tests.test_issue.Done.test_a_persons_close_of_the_rival_after_the_merge_releases_the_hold',)),
    ("a merged pull request's earlier close by a person releases nothing", ISSUE_PY,
     '(merged is None or ev["at"] < merged)', 'merged is None',
     ('tests.test_issue.Done.test_a_persons_close_of_the_rival_after_the_merge_releases_the_hold',)),
    ("only a pull request's first close is read for a release", ISSUE_PY,
     'seconds(when) >= lag for ev in entry["close_events"])', 'seconds(when) >= lag for ev in entry["close_events"][:1])',
     ('tests.test_issue.Done.test_a_persons_close_of_the_rival_after_the_merge_releases_the_hold',)),
    ("a person's close after the merge is read once its pull request is reopened", ISSUE_PY,
     '    return any(ev["action"] == CLOSED and is_person',
     '    return entry["closed_at"] is not None and any(ev["action"] == CLOSED and is_person',
     ('tests.test_issue.Done.test_a_persons_close_of_the_rival_after_the_merge_releases_the_hold',)),
    ("a reopening by anyone but a person undoes a release", ISSUE_PY,
     '    return any(ev["action"] == CLOSED and is_person',
     '    return (entry["close_events"][-1]["action"] == CLOSED or is_person(entry["close_events"][-1]["by"])) and any(ev["action"] == CLOSED and is_person',
     ('tests.test_issue.Done.test_a_persons_close_of_the_rival_after_the_merge_releases_the_hold',)),
    ("a close's event is read as its time", ISSUE_PY,
     'seconds(ev["at"]) - seconds(when) >= lag for ev', 'ev["at"] > when for ev',
     ('tests.test_issue.Done.test_a_persons_close_of_the_rival_after_the_merge_releases_the_hold',)),
    ("a close at the lag after the merge releases nothing", ISSUE_PY,
     'seconds(ev["at"]) - seconds(when) >= lag for ev', 'seconds(ev["at"]) - seconds(when) > lag for ev',
     ('tests.test_issue.Done.test_a_persons_close_of_the_rival_after_the_merge_releases_the_hold',)),
    ("an unreadable limit lets a close a second after the merge release the hold", ISSUE_PY,
     '    if not (type(lag) is int and 1 <= lag):\n        return False\n    merged = entry["merged_at"]\n',
     '    lag = lag if type(lag) is int and 1 <= lag else 1\n    merged = entry["merged_at"]\n',
     ('tests.test_issue.Done.test_a_persons_close_of_the_rival_after_the_merge_releases_the_hold',)),
    # Issue 681: a stopped run's checks give no verdict where another run of the Lens on the head did not stop; every
    # run stopped, the Lens is unreadable; a failing check in a suite not concluded is a wait; a check without both
    # fields reads as before.
    ("a stopped run is never passed over", 'kernel/derive.py',
     ' if not (r is not None and r[1] in t.STOPPED_SUITES and going)]', ']', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a stopped run is passed over for another stopped run", 'kernel/derive.py',
     'going = {r[0] for r in runs if r is not None and r[1] not in t.STOPPED_SUITES}', 'going = {r[0] for r in runs if r is not None}', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("every run stopped reads as before", 'kernel/derive.py',
     '    if all(r is not None and r[1] in t.STOPPED_SUITES for r in runs):\n        return "unreadable"\n', '', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a check without a run counts toward every run stopped", 'kernel/derive.py',
     'if all(r is not None and r[1] in t.STOPPED_SUITES for r in runs)', 'if all(r is None or r[1] in t.STOPPED_SUITES for r in runs)', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a run stopped at its timeout is no stop", 'kernel/terms.py', 'STOPPED_SUITES = ("cancelled", "timed_out")', 'STOPPED_SUITES = ("cancelled",)', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a failing check in a suite not concluded fails", 'kernel/derive.py',
     '"concluding" if r is not None and r[1] is None and check_reading(c, config) == "failing"\n                else ', '', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a failing check in a concluded suite is a wait", 'kernel/derive.py',
     'if r is not None and r[1] is None and check_reading', 'if r is not None and check_reading', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a check no workflow ran is read as a run", 'kernel/derive.py',
     ' or check["run_id"] is None:\n        return None', ':\n        return None', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a check lacking its suite is read as a run", 'kernel/derive.py',
     'if "run_id" not in check or "suite_conclusion" not in check or', 'if "run_id" not in check or', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a run in another form is read as none", 'kernel/derive.py',
     'and check["run_id"] >= 1):\n        return False', 'and check["run_id"] >= 1):\n        return None', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a run in another form under another name is read", 'kernel/derive.py',
     'if any(run_of(c) is False for c in checks if', 'if any(run_of(c) is False for c in mine if', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a suite in another form is read as none", 'kernel/derive.py',
     'in t.SUITE_CONCLUSIONS):\n        return False', 'in t.SUITE_CONCLUSIONS):\n        return None', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a run given two suite conclusions is read", 'kernel/derive.py',
     '    if any(r is not None and len({s for s in shared if s[0] == r[0]}) != 1 for r in runs):\n        return "unreadable"\n', '', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a run's two suite conclusions are read only within one Lens", 'kernel/derive.py',
     'shared = {r for r in (run_of(c) for c in checks) if r}', 'shared = {r for r in runs if r}', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("every run stopped passes when every check passed", 'kernel/derive.py',
     '    if all(r is not None and r[1] in t.STOPPED_SUITES for r in runs):\n        return "unreadable"\n',
     '    if all(r is not None and r[1] in t.STOPPED_SUITES for r in runs):\n        return "passing" if all(check_reading(c, config) == "passing" for c in mine) else "unreadable"\n', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a suite neutral is no conclusion GitHub gives", 'kernel/terms.py', '("success", "failure", "neutral", "cancelled"', '("success", "failure", "cancelled"', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a check that gave no verdict waits for its suite", 'kernel/derive.py',
     'r[1] is None and check_reading(c, config) == "failing"', 'r[1] is None and check_reading(c, config) != "passing"', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a run of 0 is read", 'kernel/derive.py', 'type(check["run_id"]) is int and check["run_id"] >= 1', 'type(check["run_id"]) is int and check["run_id"] >= 0', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a run of any type is read", 'kernel/derive.py', 'type(check["run_id"]) is int and check["run_id"] >= 1', 'isinstance(check["run_id"], int) and check["run_id"] >= 1', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a suite word GitHub does not give is read", 'kernel/derive.py', 'check["suite_conclusion"] in t.SUITE_CONCLUSIONS', 'isinstance(check["suite_conclusion"], str)', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a queued item reads past a failure whose suite has not concluded", 'kernel/derive.py',
     '(failed if "awaiting_checks" in past else waiting).append', 'waiting.append', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a failure whose suite has not concluded fails an item not queued", 'kernel/derive.py',
     '(failed if "awaiting_checks" in past else waiting).append', 'failed.append', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    ("a failure whose suite has not concluded is passed over beside another run", 'kernel/derive.py',
     'r[1] in t.STOPPED_SUITES and going)]', '(r[1] in t.STOPPED_SUITES or r[1] is None) and going)]', ('tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head',)),
    # Issue 554: a draft event before its pull request opened is no chronology.
    ("a draft event before the pull request opened is read", ISSUE_PY,
     '    if events and events[0]["at"] < entry["opened_at"]:\n        return False\n', '',
     ("tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers",)),
    ("a draft event in the opening second is refused", ISSUE_PY, 'events[0]["at"] < entry["opened_at"]', 'events[0]["at"] <= entry["opened_at"]',
     ("tests.test_issue.Unreadable.test_draft_events_in_the_opening_second_and_after_the_close_are_read",)),
    ("a draft event that is no object is read", ISSUE_PY, 'isinstance(ev, dict) and ev.get("action") in DRAFT_ACTIONS',
     '(isinstance(ev, dict) or isinstance(ev, str)) and (ev.get("action") if isinstance(ev, dict) else ev) in DRAFT_ACTIONS', ("tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers",)),
    ("a draft event's time is read in any form", ISSUE_PY, 'in DRAFT_ACTIONS and is_time(ev.get("at")) for ev in events)',
     'in DRAFT_ACTIONS and bool(ev.get("at")) for ev in events)', ("tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers",)),
    ("a draft event after the pull request closed is refused", ISSUE_PY,
     '    if events and events[0]["at"] < entry["opened_at"]:\n',
     '    if events and (events[0]["at"] < entry["opened_at"] or (entry["closed_at"] is not None and events[-1]["at"] > entry["closed_at"])):\n',
     ("tests.test_issue.Unreadable.test_draft_events_in_the_opening_second_and_after_the_close_are_read",)),
    ("two draft events of one kind in a row are read", ISSUE_PY,
     ' or later["action"] == ev["action"] for ev, later in zip(events, events[1:])):\n        return False\n    return not events or (events[-1]', ' for ev, later in zip(events, events[1:])):\n        return False\n    return not events or (events[-1]', ("tests.test_issue.Done.test_a_linked_drafts_labels_leave_a_done_issue_done",)),
    ("draft events out of order are read", ISSUE_PY,
     '    if any(later["at"] < ev["at"] or later["action"]', '    if any(later["action"]', ("tests.test_issue.Done.test_a_linked_drafts_labels_leave_a_done_issue_done",)),
    ("the last draft event is the latest by time", ISSUE_PY,
     '    return not events or (events[-1]["action"] == DRAFTED) == entry["draft"]\n',
     '    return not events or (max(events, key=lambda ev: ev["at"])["action"] == DRAFTED) == entry["draft"]\n', ("tests.test_issue.Done.test_a_linked_drafts_labels_leave_a_done_issue_done",)),
    ("a draft event in words is read", ISSUE_PY, ' and ev.get("action") in DRAFT_ACTIONS and is_time(ev.get("at"))',
     ' and is_time(ev.get("at"))', ("tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers",)),
    ("a draft event with no time is read", ISSUE_PY, ' and ev.get("action") in DRAFT_ACTIONS and is_time(ev.get("at"))',
     ' and ev.get("action") in DRAFT_ACTIONS', ("tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers",)),
    ("a linked pull request's draft events are not read", ISSUE_PY,
     '    return (readable_draft_events(entry) and readable_link_events(entry) and readable_keyword(entry)\n',
     '    return (readable_link_events(entry) and readable_keyword(entry)\n', ("tests.test_issue.Unreadable.test_an_unreadable_linked_pull_request_defers",)),
    # Issue 522: a platform close keeps the State a person set, not served or held, where the facts place it at the
    # merge; what carries no time leaves no terminal State.
    ("a person's hands-off at the merge is passed", ISSUE_PY,
     "        if hands_off_stood(facts, first):\n", "        if False:\n", PLATFORM_CLOSE_TESTS),
    ("a person's removal of hands-off since the merge ends nothing", ISSUE_PY, ' and not released_since(facts, t.LABEL_HANDS_OFF, when)\n', '\n', PLATFORM_CLOSE_TESTS),
    ("a person's hands-off placed after the merge keeps it", ISSUE_PY, '    past = as_of(facts, when)\n    return placed_by_a_person', '    past = facts\n    return placed_by_a_person', PLATFORM_CLOSE_TESTS),
    ("an issue's merged_while_hands_off calls nobody", ISSUE_PY, '    "merged_while_hands_off",\n', "",
     PLATFORM_CLOSE_TESTS),
    ('a Hold on a ready linked pull request stood at the merge', ISSUE_PY, '            if name in standing_labels(past) and not released_since(facts, name, when)]\n', '            if (name in standing_labels(past) or any(name in standing_labels(as_of(q, when)) for q in facts["linked"]))\n               and not released_since(facts, name, when)]\n', PLATFORM_CLOSE_TESTS),
    ("the Consumer entry is read at the merge as it stands now", ISSUE_PY,
     "        if hands_off_stood(facts, first):\n",
     "        if not served(facts, config):\n            return out(t.NOT_SERVED, \"left_out\", [])\n"
     "        if hands_off_stood(facts, first):\n",
     ("tests.test_issue.Done.test_a_done_issue_stays_done_whatever_changes_after_the_merge_that_carries_no_time",)),
    ("an issue left out under a person's hands-off at the merge is quiet", ISSUE_PY,
     '            return out(t.NOT_SERVED, "merged_while_hands_off", merges)\n',
     '            if not served(facts, config):\n                return out(t.NOT_SERVED, "left_out", [])\n'
     '            return out(t.NOT_SERVED, "merged_while_hands_off", merges)\n', PLATFORM_CLOSE_TESTS),
    ("an issue left out under a Hold at the merge is quiet", ISSUE_PY,
     '            return out(t.HELD, "merged_while_held", merges)\n',
     '            if not served(facts, config):\n                return out(t.NOT_SERVED, "left_out", [])\n'
     '            return out(t.HELD, "merged_while_held", merges)\n', PLATFORM_CLOSE_TESTS),
    ("issues turned off, or the entry's date moved, is read at the merge", ISSUE_PY,
     "        if hands_off_stood(facts, first):\n",
     "        start = config[\"issues\"][\"served_from\"]\n"
     "        if not is_time(start) or facts[\"life_started_at\"] < start:\n"
     "            return out(t.NOT_SERVED, \"left_out\", [])\n"
     "        if hands_off_stood(facts, first):\n",
     ("tests.test_issue.Done.test_a_done_issue_stays_done_whatever_changes_after_the_merge_that_carries_no_time",)),
    ("a left-out label or type is read at the merge as it stands now", ISSUE_PY,
     "        if hands_off_stood(facts, first):\n",
     "        if facts[\"type\"] in config[\"issues\"][\"left_out_types\"] or any(\n"
     "                n in config[\"issues\"][\"left_out_labels\"] for n in facts[\"label_names\"]):\n"
     "            return out(t.NOT_SERVED, \"left_out\", [])\n"
     "        if hands_off_stood(facts, first):\n",
     ("tests.test_issue.Done.test_a_done_issue_stays_done_whatever_changes_after_the_merge_that_carries_no_time",)),
    ("two links at the merge are read from the links as they stand now", ISSUE_PY,
     "            return out(t.HELD, \"merged_while_held\", stood)\n        # Done only where",
     "            return out(t.HELD, \"merged_while_held\", stood)\n"
     "        if any(p[\"opened_at\"] <= first and p[\"merged_at\"] != first for p in links):\n"
     "            return out(t.HELD, \"merged_while_held\", merges)\n        # Done only where",
     ("tests.test_issue.Done.test_a_done_issue_stays_done_whatever_changes_after_the_merge_that_carries_no_time",)),
    ("an empty merge is done", ISSUE_PY,
     'if p["merged_at"] is not None and not p["empty"] and', 'if p["merged_at"] is not None and', ISSUE_TESTS),
    ("a merge in an earlier life is done", ISSUE_PY,
     ' and p["merged_at"] >= facts["life_started_at"]]', "]", ISSUE_TESTS),
    ("a merge at the start of a life is not done", ISSUE_PY,
     'p["merged_at"] >= facts["life_started_at"]', 'p["merged_at"] > facts["life_started_at"]', ISSUE_TESTS),
    # Row 2: declined.
    ("a closed issue is not declined", ISSUE_PY,
     '    if facts["state"] != "open":\n', "    if False:\n", ISSUE_TESTS),
    ("a reopening by anyone begins a life", ISSUE_PY,
     '    if facts["reopened_last_by"] == "other":\n', "    if False:\n", ISSUE_TESTS),
    # Row 3: not served.
    ("an issue the Consumer entry leaves out is served", ISSUE_PY,
     "    # Row 3.\n    if not served(facts, config):\n", "    # Row 3.\n    if False:\n", ISSUE_TESTS),
    ("an issue whose life began before the date served is served", ISSUE_PY,
     'if not is_time(start) or facts["life_started_at"] < start:', "if not is_time(start):", ISSUE_TESTS),
    ("an issue of a type left out is served", ISSUE_PY,
     '    if facts["type"] in issues["left_out_types"]:\n', "    if False:\n", ISSUE_TESTS),
    ("an issue with a label left out is served", ISSUE_PY,
     'not any(label in issues["left_out_labels"] for label in facts["label_names"])', "True", ISSUE_TESTS),
    ("a person's hands-off on an issue is not read", ISSUE_PY, 'for each, item in [(labels, facts)] + [(standing_labels(p), p) for p in drafts])', 'for each, item in [(standing_labels(p), p) for p in drafts])', ISSUE_TESTS),
    ("a person's hands-off on the linked draft is not read", ISSUE_PY, 'for each, item in [(labels, facts)] + [(standing_labels(p), p) for p in drafts])', 'for each, item in [(labels, facts)])', ISSUE_TESTS),
    ("hands-off anyone placed on an issue is a person's", ISSUE_PY,
     '    if placed is None or not is_person(placed["by"]):\n', "    if placed is None:\n", ISSUE_TESTS),
    ("hands-off a person removed in the second it was placed stands", ISSUE_PY,
     '    return not any(ev["label"] == t.LABEL_HANDS_OFF', '    return True or not any(ev["label"] == t.LABEL_HANDS_OFF',
     ISSUE_TESTS),
    ("a person's removal of hands-off at another second ties", ISSUE_PY,
     ' and ev["at"] == placed["at"]\n', "\n", ISSUE_TESTS),
    ("a person's removal of another label ties with hands-off", ISSUE_PY,
     'ev["label"] == t.LABEL_HANDS_OFF and ev["action"] == "unlabeled"', 'ev["action"] == "unlabeled"', ISSUE_TESTS),
    # Row 4: held.
    ("a Hold does not hold an issue", ISSUE_PY, "    if stops:\n", "    if False:\n", ISSUE_TESTS),
    ("a Hold on the linked draft does not hold the issue", ISSUE_PY,
     "if name in labels or any(name in d for d in on_drafts)]", "if name in labels]", ISSUE_TESTS),
    ("two linked pull requests open do not hold the issue", ISSUE_PY,
     "    if len(open_links) > 1:\n", "    if False:\n", ISSUE_TESTS),
    # Row 5, and accepted.
    ("an issue that is not accepted moves on", ISSUE_PY,
     "    if not accepted(facts, runs, config):\n", "    if False:\n", ISSUE_TESTS),
    ("acceptance that lapsed after work began is not told apart", ISSUE_PY,
     '"acceptance_lapsed" if work_began(facts, links, config) else "not_accepted"', '"not_accepted"', ISSUE_TESTS),
    ("acceptance lapses on an issue never admitted", ISSUE_PY,
     "    if not admitted_once(facts):\n        return False\n", "", ISSUE_TESTS),
    ("a linked pull request is no work begun", ISSUE_PY,
     "    return bool(here) or any(added_in_this_life(", "    return any(added_in_this_life(", ISSUE_TESTS),
    ("a link closed in an earlier life is work begun", ISSUE_PY,
     ' or p["closed_at"] >= facts["life_started_at"]]', " or True]", ISSUE_TESTS),
    ("a link closed at the start of a life is no work begun in it", ISSUE_PY,
     'p["closed_at"] >= facts["life_started_at"]', 'p["closed_at"] > facts["life_started_at"]', ISSUE_TESTS),
    ("factory:ready is no work begun", ISSUE_PY,
     "config, name) for name in (LABEL_TRIAGE, LABEL_READY))\n", "config, name) for name in (LABEL_TRIAGE,))\n",
     ISSUE_TESTS),
    ("a label from an earlier life is work begun", ISSUE_PY,
     ' and placed[0]["at"] > facts["life_started_at"]', "", ISSUE_TESTS),
    ("a label anyone added is work begun", ISSUE_PY,
     '            and all(is_person(ev["by"]) or declared(ev["by"], name, config) for ev in placed))',
     "            )", ISSUE_TESTS),
    ("a person's issue is not accepted", ISSUE_PY,
     '    return is_person(facts["author"]) or ', "    return ", ISSUE_TESTS),
    ("an issue opened by any actor with write access is accepted", ISSUE_PY,
     'is_person(facts["author"]) or ', 'facts["author"]["can_write"] is True or ', ISSUE_TESTS),
    ("an admission does not accept an outsider's issue", ISSUE_PY,
     " or counts(facts, runs, config, t.LABEL_ADMIT)", "", ISSUE_TESTS),
    # Linked.
    ("the Factory's pull request is not linked", ISSUE_PY,
     '    if entry["class"] == "agent":\n        return True\n', "", ISSUE_TESTS),
    ("a writer's pull request is not linked", ISSUE_PY,
     '    if entry["class"] == "maintainer":\n        return True\n', "", ISSUE_TESTS),
    ("an outsider's pull request nobody admitted is linked", ISSUE_PY,
     'return entry["class"] == "outside" and admitted_once(entry)', 'return entry["class"] == "outside"', ISSUE_TESTS),
    ("a dependency update is linked", ISSUE_PY,
     'return entry["class"] == "outside" and admitted_once(entry)',
     'return entry["class"] == "dependency" or (entry["class"] == "outside" and admitted_once(entry))', ISSUE_TESTS),
    ("an admission anyone placed links an outsider's pull request", ISSUE_PY,
     'and ev["action"] == "labeled" and is_person(ev["by"])\n', 'and ev["action"] == "labeled"\n', ISSUE_TESTS),
    # Counts.
    ("a label anyone added counts", ISSUE_PY,
     '    if not all(is_person(ev["by"]) or declared(ev["by"], name, config) for ev in placed):\n',
     "    if False:\n", ISSUE_TESTS),
    ("of adds in one second, the first listed is read", ISSUE_PY,
     '    if not all(is_person(ev["by"]) or declared(ev["by"], name, config) for ev in placed):\n',
     '    if not (is_person(placed[0]["by"]) or declared(placed[0]["by"], name, config)):\n', ISSUE_TESTS),
    ("any App counts as the declared one", ISSUE_PY,
     'by["kind"] in APP_KINDS and by["name"] == app', 'by["kind"] in APP_KINDS', ISSUE_TESTS),
    ("anyone named as the declared App counts", ISSUE_PY,
     'by["kind"] in APP_KINDS and by["name"] == app', 'by["name"] == app', ISSUE_TESTS),
    ("an App declared for one label counts for the other", ISSUE_PY,
     'app = config["issues"]["label_apps"].get(name)', 'app = config["issues"]["label_apps"].get(LABEL_READY)',
     ISSUE_TESTS),
    ("triage and ready count from an earlier life", ISSUE_PY,
     'if name != t.LABEL_ADMIT and at <= facts["life_started_at"]:', "if False:", ISSUE_TESTS),
    ("a label added at a reopening counts", ISSUE_PY,
     'at <= facts["life_started_at"]', 'at < facts["life_started_at"]', ISSUE_TESTS),
    ("an admission lasts one life", ISSUE_PY,
     'if name != t.LABEL_ADMIT and at <= facts["life_started_at"]', 'if at <= facts["life_started_at"]', ISSUE_TESTS),
    ("ready and an admission count from before the last edit", ISSUE_PY,
     'if name != LABEL_TRIAGE and at <= facts["content_changed_at"]:', "if False:", ISSUE_TESTS),
    ("a label added at an edit counts", ISSUE_PY,
     'at <= facts["content_changed_at"]', 'at < facts["content_changed_at"]', ISSUE_TESTS),
    ("an edit ends triage", ISSUE_PY,
     'if name != LABEL_TRIAGE and at <= facts["content_changed_at"]', 'if at <= facts["content_changed_at"]',
     ISSUE_TESTS),
    ("a Factory ready counts for content its readiness Run did not judge", ISSUE_PY,
     '    if name == LABEL_READY and not all(is_person(ev["by"]) for ev in placed) and not judged_here(at, facts, runs):\n',
     "    if False:\n", ISSUE_TESTS),
    ("a person's ready is held to a readiness Run's content", ISSUE_PY,
     ' and not all(is_person(ev["by"]) for ev in placed) and not judged_here(', " and not judged_here(", ISSUE_TESTS),
    ("a person's add in the second of the App's excuses the App's", ISSUE_PY,
     ' and not all(is_person(ev["by"]) for ev in placed) and not judged_here(',
     ' and not any(is_person(ev["by"]) for ev in placed) and not judged_here(', ISSUE_TESTS),
    ("a Factory ready whose readiness Run record expired counts on its time", ISSUE_PY,
     "    if not mine:\n        return False\n", "    if not mine:\n        return True\n", ISSUE_TESTS),
    ("a Run of any Intent judges readiness", ISSUE_PY,
     'if r["intent"] == JUDGE_READINESS and r["started_at"] <= at]', 'if r["started_at"] <= at]', ISSUE_TESTS),
    ("a readiness Run that started after the label is the one read", ISSUE_PY,
     ' and r["started_at"] <= at]', "]", ISSUE_TESTS),
    ("a readiness Run in the same second as the label is not read", ISSUE_PY,
     'r["started_at"] <= at]', 'r["started_at"] < at]', ISSUE_TESTS),
    ("a readiness Run still running has judged", ISSUE_PY,
     '    return all(r["status"] == "completed" and r["content_id"]', '    return all(r["content_id"]', ISSUE_TESTS),
    ("one readiness Run of that second agreeing is enough", ISSUE_PY,
     '    return all(r["status"] == "completed" and r["content_id"]',
     '    return any(r["status"] == "completed" and r["content_id"]', ISSUE_TESTS),
    ("another issue's Run judges this one's label", ISSUE_PY,
     "    mine = [r for r in runs_on(runs, facts) if", "    mine = [r for r in runs if", ISSUE_TESTS),
    ("a removal does not end ready or triage", ISSUE_PY,
     '    if any(ev["label"] == name and ev["action"] == "unlabeled"',
     '    if False and any(ev["label"] == name and ev["action"] == "unlabeled"', ISSUE_TESTS),
    ("a removal in the second of the latest add does not end it", ISSUE_PY,
     'ev["at"] >= last for ev in events', 'ev["at"] > last for ev in events', ISSUE_TESTS),
    ("the first add of ready or triage is read, not the latest", ISSUE_PY,
     'last = max(ev["at"] for ev in adds)', 'last = min(ev["at"] for ev in adds)', ISSUE_TESTS),
    # Rows 6 to 10.
    ("a linked pull request ready for review is not in review", ISSUE_PY,
     '    if open_links and not open_links[0]["draft"]:\n', "    if False:\n", ISSUE_TESTS),
    ("a linked draft is not in progress", ISSUE_PY, "    if open_links:\n", "    if False:\n", ISSUE_TESTS),
    ("an opening Run does not hold the issue", ISSUE_PY,
     "    if any(r[\"intent\"] == OPENING for r in in_progress(runs_on(runs, facts))):\n", "    if False:\n",
     ISSUE_TESTS),
    ("any Run in progress holds the issue as an opening Run would", ISSUE_PY,
     'r["intent"] == OPENING for r in', "True for r in", ISSUE_TESTS),
    ("an opening Run that ended still holds the issue", ISSUE_PY,
     "for r in in_progress(runs_on(runs, facts))", "for r in runs_on(runs, facts)", ISSUE_TESTS),
    ("factory:ready does not make an issue ready", ISSUE_PY,
     "    if counts(facts, runs, config, LABEL_READY):\n", "    if False:\n", ISSUE_TESTS),
    ("factory:triage does not put an issue in triage", ISSUE_PY,
     "    if counts(facts, runs, config, LABEL_TRIAGE):\n", "    if False:\n", ISSUE_TESTS),
    ("an accepted issue with no label is not new", ISSUE_PY,
     '    return out(NEW, "acceptance_due", [])', '    return out(TRIAGE, "acceptance_due", [])', ISSUE_TESTS),
    # What is admitted on an issue (decision 0031). Its outcomes, and who is called.
    ("an issue that cannot be read admits nothing but does not defer", ISSUE_PY,
     "        return _decision(facts, None, reason, evidence, t.DEFER)\n",
     "        return _decision(facts, None, reason, evidence, t.NOTHING)\n", ISSUE_TESTS),
    ("an issue at an end is acted on", ISSUE_PY,
     "    if state in ADMITS_NOTHING:\n        return _decision(facts, state, reason, evidence, t.NOTHING)\n", "",
     ISSUE_TESTS),
    ("a held issue is not held", ISSUE_PY, "    if state == t.HELD:\n", "    if False:\n", ISSUE_TESTS),
    ("an issue's reason that needs a person calls nobody", ISSUE_PY,
     "    if reason in NEEDS_YOU_REASONS:\n        return t.NEEDS_YOU\n", "", ISSUE_TESTS),
    ("an issue's Run in flight is not told apart", ISSUE_PY, "    if working:\n        return t.WORKING\n", "",
     ISSUE_TESTS),
    ("an issue nobody accepted calls attention", ISSUE_PY,
     "    if state in QUIET_STATES or reason in QUIET_REASONS:\n", "    if state in QUIET_STATES:\n", ISSUE_TESTS),
    ("an issue at an end calls attention", ISSUE_PY,
     "    if state in QUIET_STATES or reason in QUIET_REASONS:\n", "    if reason in QUIET_REASONS:\n", ISSUE_TESTS),
    ("an issue's unreadable configuration calls nobody", ISSUE_PY,
     "    if state is None and reason not in NEEDS_YOU_REASONS:\n", "    if state is None:\n", ISSUE_TESTS),
    # Unmerged closes past their bound place a Hold (I-43).
    ("unmerged closes past their bound place no Hold", ISSUE_PY,
     '    if len(closes) > config["limits"]["max_unmerged_closes"]:\n', "    if False:\n", ISSUE_TESTS),
    ("unmerged closes at their bound place a Hold", ISSUE_PY,
     'len(closes) > config["limits"]', 'len(closes) >= config["limits"]', ISSUE_TESTS),
    ("a Hold deferred by the Pause calls nobody", ISSUE_PY,
     '        return dict(_stop(facts, state, "unmerged_closes", closes, context, PLACE_HOLD), attention=t.NEEDS_YOU)\n',
     '        return _stop(facts, state, "unmerged_closes", closes, context, PLACE_HOLD)\n', ISSUE_TESTS),
    ("a close in an earlier life is counted", ISSUE_PY,
     '    since = max([facts["life_started_at"]] + released)\n', '    since = max([""] + released)\n', ISSUE_TESTS),
    ("a close at the start of a life or a release is not counted", ISSUE_PY,
     'p["closed_at"] >= since]', 'p["closed_at"] > since]', ISSUE_TESTS),
    ("a person's release of the Hold resets no count", ISSUE_PY,
     '[facts["life_started_at"]] + released)', '[facts["life_started_at"]])', ISSUE_TESTS),
    ("anyone's removal of the Hold resets the count", ISSUE_PY,
     'if ev["label"] == t.LABEL_HOLD and ev["action"] == "unlabeled" and is_person(ev["by"])]',
     'if ev["label"] == t.LABEL_HOLD and ev["action"] == "unlabeled"]', ISSUE_TESTS),
    ("a pull request that is not linked counts as a close", ISSUE_PY,
     '            if is_linked(p) and not p["open"]', '            if not p["open"]', ISSUE_TESTS),
    ("an open pull request counts as a close", ISSUE_PY,
     'if is_linked(p) and not p["open"] and p["closed_at"]', 'if is_linked(p) and p["closed_at"]', ISSUE_TESTS),
    # A label that stands and does not count is removed (I-17).
    ("a label that does not count is kept", ISSUE_PY,
     "    if label is not None and not in_progress(mine):\n", "    if False:\n", ISSUE_TESTS),
    ("a label is removed under a Run in flight", ISSUE_PY,
     "    if label is not None and not in_progress(mine):\n", "    if label is not None:\n", ISSUE_TESTS),
    ("a label is removed once work is linked", ISSUE_PY,
     '    if state not in KEPT or reason == "acceptance_lapsed":\n', '    if reason == "acceptance_lapsed":\n',
     ISSUE_TESTS),
    ("a label is removed while acceptance has lapsed", ISSUE_PY,
     '    if state not in KEPT or reason == "acceptance_lapsed":\n', "    if state not in KEPT:\n", ISSUE_TESTS),
    ("a person's label is removed", ISSUE_PY,
     ' and not any(is_person(ev["by"]) for ev in adds)', "", ISSUE_TESTS),
    ("a person's label tied in its second with another's is removed", ISSUE_PY,
     'not any(is_person(ev["by"]) for ev in adds)', 'not all(is_person(ev["by"]) for ev in adds)', ISSUE_TESTS),
    ("a label that counts is removed", ISSUE_PY,
     " and not counts(facts, runs, config, name):", ":", ISSUE_TESTS),
    ("a label already gone is removed", ISSUE_PY,
     "        if adds and not any(", "        if not any(", ISSUE_TESTS),
    ("factory:ready is never removed", ISSUE_PY,
     "    for name in (LABEL_READY, LABEL_TRIAGE):\n        adds = latest_adds",
     "    for name in (LABEL_TRIAGE,):\n        adds = latest_adds", ISSUE_TESTS),
    ("factory:triage is never removed", ISSUE_PY,
     "    for name in (LABEL_READY, LABEL_TRIAGE):\n        adds = latest_adds",
     "    for name in (LABEL_READY,):\n        adds = latest_adds", ISSUE_TESTS),
    ("the label to remove is not named", ISSUE_PY, "REMOVE_LABEL, label=label)", "REMOVE_LABEL)", ISSUE_TESTS),
    ("an act that stops work is not stopped by the Pause", ISSUE_PY,
     "    pause = brakes.paused(_decision, facts, state, evidence, context)\n    if pause:\n        return pause\n", "",
     ISSUE_TESTS),
    ("an act that stops work names no content", ISSUE_PY,
     'action=action, content_id=facts["content_id"], **extra)', "action=action, **extra)", ISSUE_TESTS),
    # What steers admission, read whole.
    ("an issue's role comments that cannot be read are trusted", ISSUE_PY,
     '    if not readable_comments(facts.get("role_comments")):\n', "    if False:\n", ISSUE_TESTS),
    ("a role comment's time is not read", ISSUE_PY,
     'c["by"] != "" and is_time(c.get("at"))', 'c["by"] != ""', ISSUE_TESTS),
    ("a role comment's App is not read", ISSUE_PY,
     'isinstance(c.get("by"), str) and c["by"] != "" and ', "", ISSUE_TESTS),
    ("a writer's times that cannot be read are trusted", ISSUE_PY,
     "    if not readable_writer(facts):\n", "    if False:\n", ISSUE_TESTS),
    ("a writer's time left out is read as none", ISSUE_PY,
     'facts.get(name, "") is None', "facts.get(name) is None", ISSUE_TESTS),
    # Acceptance, at row 10.
    ("a new issue is not accepted", ISSUE_PY,
     "    if state == NEW:\n        return _accept(", "    if False:\n        return _accept(", ISSUE_TESTS),
    ("an issue past row 10 is accepted", ISSUE_PY, '    if reason != "acceptance_due":\n', "    if False:\n",
     ISSUE_TESTS),
    ("an issue is accepted with no App declared for factory:triage", ISSUE_PY,
     '    if config["issues"]["label_apps"][LABEL_TRIAGE] is None:\n', "    if False:\n", ISSUE_TESTS),
    ("a person's removal of factory:triage is overruled", ISSUE_PY,
     "    if removed_by_a_person(facts, LABEL_TRIAGE):\n", "    if False:\n", ISSUE_TESTS),
    ("acceptance is not braked", ISSUE_PY,
     "    if brake:\n        return brake\n    return _decision(facts, state, reason, evidence, t.ACT, action=ACCEPT",
     "    return _decision(facts, state, reason, evidence, t.ACT, action=ACCEPT", ISSUE_TESTS),
    ("acceptance names no content", ISSUE_PY,
     'action=ACCEPT, content_id=facts["content_id"])', "action=ACCEPT)", ISSUE_TESTS),
    ("anyone's removal of a label overrules the Factory", ISSUE_PY,
     ' and is_person(ev["by"])\n               and ev["at"] >= facts["content_changed_at"]',
     '\n               and ev["at"] >= facts["content_changed_at"]', ISSUE_TESTS),
    ("a removal before the content changed overrules the Factory", ISSUE_PY,
     'and ev["at"] >= facts["content_changed_at"] for ev in', "for ev in", ISSUE_TESTS),
    ("a removal at the edit does not overrule the Factory", ISSUE_PY,
     'ev["at"] >= facts["content_changed_at"] for ev in', 'ev["at"] > facts["content_changed_at"] for ev in',
     ISSUE_TESTS),
    # The Intents, read whole.
    ("an issue in review reads the Intents", ISSUE_PY,
     '    if state == IN_REVIEW:\n        return _decision(facts, state, reason, evidence, t.NOTHING)\n    if reason',
     '    if False:\n        return _decision(facts, state, reason, evidence, t.NOTHING)\n    if reason',
     ("tests.test_issue.Outcomes.test_in_review_and_with_a_linked_draft_nothing_is_admitted_whatever_the_intents",)),
    ("an issue with a linked draft reads the Intents", ISSUE_PY,
     '    if reason == "linked_draft":\n        return _implementing(', '    if False:\n        return _implementing(',
     ("tests.test_issue.Outcomes.test_in_review_and_with_a_linked_draft_nothing_is_admitted_whatever_the_intents",)),
    # The implementing Run while the draft the Factory opened fails its checks (slice 2's S9, issue 825, decision 0217).
    ("a draft is implemented with no author Role named", ISSUE_PY,
     'config["author_role"] is None or draft', 'False or draft',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("anyone's draft is implemented", ISSUE_PY, 'or draft["class"] != "agent":', 'or False:',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("a draft's unreadable checks are read as passing", ISSUE_PY,
     '    if draft.get("checks") not in CHECKS:\n', '    if False:\n',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("a draft is implemented whatever its checks", ISSUE_PY,
     '    if draft["checks"] != "failing":\n', '    if False:\n',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("a draft's pending checks admit an implementing Run", ISSUE_PY,
     '    if draft["checks"] != "failing":\n', '    if draft["checks"] == "passing":\n',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("the implementing rounds are unbounded", "kernel/brakes.py",
     'if len(rounds) >= limits["max_attempts"]:', 'if False:',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("max_attempts rounds admit one more", "kernel/brakes.py",
     'if len(rounds) >= limits["max_attempts"]:', 'if len(rounds) > limits["max_attempts"]:',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("every Run counts as an implementing round", "kernel/brakes.py", 'r["intent"] == t.IMPLEMENT and ', '',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("a writer's action does not renew the rounds", ISSUE_PY,
     'brakes.implementing_rounds(_decision, facts, since_writer(mine, facts), config["limits"])',
     'brakes.implementing_rounds(_decision, facts, mine, config["limits"])',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("the implementing Run is not told its draft", ISSUE_PY, '{"pull_request": draft["number"]}', '{}',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("the first pull request linked is read as the draft", ISSUE_PY, 'if str(p["number"]) == evidence[0]]', 'if True]',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("the implementing rounds hold only at the bound", "kernel/brakes.py",
     'if len(rounds) >= limits["max_attempts"]:', 'if len(rounds) == limits["max_attempts"]:',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("an implementing Run in flight counts as a round", "kernel/brakes.py",
     'r["intent"] == t.IMPLEMENT and r["status"] == "completed"]', 'r["intent"] == t.IMPLEMENT]',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("the implementing rounds' Hold leaves the State", "kernel/brakes.py",
     'return _decision(facts, t.HELD, "attempts_exhausted", [r["run"] for r in rounds], t.HOLD)',
     'return _decision(facts, "in_progress", "attempts_exhausted", [r["run"] for r in rounds], t.HOLD)',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("the implementing rounds' Hold names no Run", "kernel/brakes.py",
     '"attempts_exhausted", [r["run"] for r in rounds], t.HOLD)', '"attempts_exhausted", [], t.HOLD)',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("a draft's checks are read before whose draft it is", ISSUE_PY,
     '    if config["author_role"] is None or draft["class"] != "agent":\n        return _decision(facts, state, reason, evidence, t.NOTHING)\n    if draft.get("checks") not in CHECKS:\n        return _decision(facts, state, "draft_checks_unreadable", evidence, t.DEFER)\n',
     '    if draft.get("checks") not in CHECKS:\n        return _decision(facts, state, "draft_checks_unreadable", evidence, t.DEFER)\n    if config["author_role"] is None or draft["class"] != "agent":\n        return _decision(facts, state, reason, evidence, t.NOTHING)\n',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("the implementing rounds' Hold is dropped while a Run is in flight", ISSUE_PY,
     '        elif isinstance(wanted, dict) and wanted["outcome"] == t.HOLD:\n            held = wanted\n', '',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    # Carbon's read of #827: the other sides of the implementing rule, and its dormancy.
    ("whatever the Run wanted says stands while a Run is in flight", ISSUE_PY,
     '        elif isinstance(wanted, dict) and wanted["outcome"] == t.HOLD:\n',
     '        elif isinstance(wanted, dict):\n',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("a draft's passing checks admit an implementing Run", ISSUE_PY,
     '    if draft["checks"] != "failing":\n', '    if draft["checks"] == "pending":\n',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("the implementing rounds are spent whatever the draft's checks", ISSUE_PY,
     '    if draft["checks"] != "failing":\n        return _decision(facts, state, reason, evidence, t.NOTHING)\n'
     '    held = brakes.implementing_rounds(_decision, facts, since_writer(mine, facts), config["limits"])\n'
     '    if held:\n        return held\n',
     '    held = brakes.implementing_rounds(_decision, facts, since_writer(mine, facts), config["limits"])\n'
     '    if held:\n        return held\n'
     '    if draft["checks"] != "failing":\n        return _decision(facts, state, reason, evidence, t.NOTHING)\n',
     ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("the implementing rounds are not asked of the brakes", ISSUE_PY,
     '    if held:\n        return held\n    return (config["author_role"], IMPLEMENT,',
     '    return (config["author_role"], IMPLEMENT,', ("tests.test_issue.Outcomes.test_while_the_factorys_draft_fails_its_checks_another_implementing_run_is_admitted",)),
    ("Intents that cannot be read are trusted", ISSUE_PY,
     "    if not readable_intents(intents):\n", "    if False:\n", ISSUE_TESTS),
    ("an Intent left out of the Intents is read", ISSUE_PY,
     "    if not (isinstance(intents, dict) and all(name in intents for name in INTENTS)):\n",
     "    if not isinstance(intents, dict):\n", ISSUE_TESTS),
    ("an Intent's Role or App may be any value", ISSUE_PY,
     'isinstance(intents[name].get(key), str) and intents[name][key] != ""', "True", ISSUE_TESTS),
    ("an Intent may be mapped to anything", ISSUE_PY,
     "(isinstance(intents[name], dict) and all(", "(all(", ISSUE_TESTS),
    ("two Intents may share a Role", ISSUE_PY, "    if shares_a_role(intents):\n", "    if False:\n", ISSUE_TESTS),
    ("an Intent that is null shares a Role", ISSUE_PY,
     'roles = [intents[name]["role"] for name in INTENTS if intents[name] is not None]',
     'roles = [intents[name]["role"] for name in INTENTS]', ISSUE_TESTS),
    ("two Intents may share an App", ISSUE_PY, "    if shares_an_app(intents):\n", "    if False:\n", ISSUE_TESTS),
    ("an Intent that is null shares an App", ISSUE_PY,
     'apps = [intents[name]["app"] for name in INTENTS if intents[name] is not None]',
     'apps = [intents[name]["app"] for name in INTENTS]', ISSUE_TESTS),
    # In triage: an investigation unless it is current, then a verdict unless one stands.
    ("an investigation with no Role declared is admitted", ISSUE_PY,
     '        if who is None:\n            return _decision(facts, state, "intent_undeclared", [INVESTIGATE], t.NOTHING)\n',
     "", ISSUE_TESTS),
    ("a current investigation is investigated again", ISSUE_PY,
     "        if since is None:\n", "        if True:\n", ISSUE_TESTS),
    ("a person's removal of factory:ready is overruled", ISSUE_PY,
     "        if removed_by_a_person(facts, LABEL_READY):\n", "        if False:\n", ISSUE_TESTS),
    ("a verdict with no Role declared is admitted", ISSUE_PY,
     '        if who is None:\n            return _decision(facts, state, "intent_undeclared", [JUDGE_READINESS], '
     "t.NOTHING)\n", "", ISSUE_TESTS),
    ("a verdict given is judged again", ISSUE_PY,
     "        if judged(facts, mine, who, since):\n", "        if False:\n", ISSUE_TESTS),
    ("another Role's investigation is current", ISSUE_PY,
     '\n    kept = [r for r in mine if r["intent"] == INVESTIGATE and r["role"] == who["role"]]',
     '\n    kept = [r for r in mine if r["intent"] == INVESTIGATE]', ISSUE_TESTS),
    ("another Intent's Run investigates", ISSUE_PY,
     '\n    kept = [r for r in mine if r["intent"] == INVESTIGATE and r["role"] == who["role"]]',
     '\n    kept = [r for r in mine if r["role"] == who["role"]]', ISSUE_TESTS),
    ("a failed investigation is current", ISSUE_PY,
     'r["conclusion"] == "success" and r["content_id"] == facts["content_id"]]',
     'r["content_id"] == facts["content_id"]]', ISSUE_TESTS),
    ("an investigation of other content is current", ISSUE_PY,
     'r["conclusion"] == "success" and r["content_id"] == facts["content_id"]]', 'r["conclusion"] == "success"]',
     ISSUE_TESTS),
    ("an investigating App's comment from before the edit stands in", ISSUE_PY,
     'c["by"] == who["app"] and c["at"] > facts["content_changed_at"]]', 'c["by"] == who["app"]]', ISSUE_TESTS),
    ("an investigating App's comment at the edit stands in", ISSUE_PY,
     'c["at"] > facts["content_changed_at"]]', 'c["at"] >= facts["content_changed_at"]]', ISSUE_TESTS),
    ("another App's comment stands in for the investigation", ISSUE_PY,
     'if c["by"] == who["app"] and c["at"] > facts', "if c[\"at\"] > facts", ISSUE_TESTS),
    ("an investigation before a writer acted is current", ISSUE_PY,
     "    times = [when for when in times if mark is None or when > mark]\n",
     "    times = [when for when in times]\n", ISSUE_TESTS),
    ("an investigation in the second a writer acted is current", ISSUE_PY,
     "if mark is None or when > mark]", "if mark is None or when >= mark]", ISSUE_TESTS),
    ("with no writer's action nothing is current", ISSUE_PY,
     "if mark is None or when > mark]", "if mark is not None and when > mark]", ISSUE_TESTS),
    ("an investigating App's comment stands in while a record of its Runs is kept", ISSUE_PY,
     "    if not kept:\n        times = [c[\"at\"] for c", "    if True:\n        times += [c[\"at\"] for c", ISSUE_TESTS),
    ("the latest sign of the investigation is read, not the first", ISSUE_PY,
     "    return min(times) if times else None\n", "    return max(times) if times else None\n", ISSUE_TESTS),
    ("another Role's verdict stands", ISSUE_PY,
     'r["intent"] == JUDGE_READINESS and r["role"] == who["role"]', 'r["intent"] == JUDGE_READINESS', ISSUE_TESTS),
    ("another Intent's Run is a verdict", ISSUE_PY,
     'r["intent"] == JUDGE_READINESS and r["role"] == who["role"]', 'r["role"] == who["role"]', ISSUE_TESTS),
    ("the readiness App's label or comment stands in while a record of its Runs is kept", ISSUE_PY,
     "    if kept:\n", "    if False:\n", ISSUE_TESTS),
    ("a failed verdict stands", ISSUE_PY,
     'r["conclusion"] == "success" and r["content_id"] == facts["content_id"] and r["started_at"] >= since',
     'r["content_id"] == facts["content_id"] and r["started_at"] >= since', ISSUE_TESTS),
    ("a verdict on other content stands", ISSUE_PY,
     'r["conclusion"] == "success" and r["content_id"] == facts["content_id"] and r["started_at"] >= since',
     'r["conclusion"] == "success" and r["started_at"] >= since', ISSUE_TESTS),
    ("a verdict from before the investigation stands", ISSUE_PY,
     ' and r["started_at"] >= since\n', "\n", ISSUE_TESTS),
    ("a verdict in the second of the investigation does not stand", ISSUE_PY,
     'r["started_at"] >= since', 'r["started_at"] > since', ISSUE_TESTS),
    ("the readiness App's label does not stand in", ISSUE_PY,
     '    if any(ev["label"] == LABEL_READY and ev["action"] == "labeled"',
     '    if False and any(ev["label"] == LABEL_READY and ev["action"] == "labeled"', ISSUE_TESTS),
    ("a removal stands in for a verdict", ISSUE_PY,
     'ev["label"] == LABEL_READY and ev["action"] == "labeled" and ev["by"]["kind"]',
     'ev["label"] == LABEL_READY and ev["by"]["kind"]', ISSUE_TESTS),
    ("a person named as the readiness App gives its verdict", ISSUE_PY,
     ' and ev["by"]["kind"] in APP_KINDS\n           and ev["by"]["name"]', '\n           and ev["by"]["name"]',
     ISSUE_TESTS),
    ("another App's label stands in for a verdict", ISSUE_PY,
     '           and ev["by"]["name"] == who["app"] and ev["at"] >= since', '           and ev["at"] >= since',
     ISSUE_TESTS),
    ("a label from before the investigation stands in", ISSUE_PY,
     'ev["by"]["name"] == who["app"] and ev["at"] >= since for ev', 'ev["by"]["name"] == who["app"] for ev',
     ISSUE_TESTS),
    ("the readiness App's comment does not stand in", ISSUE_PY,
     '    return any(c["by"] == who["app"] and c["at"] >= since for c in facts["role_comments"])\n',
     "    return False\n", ISSUE_TESTS),
    ("a comment from before the investigation stands in", ISSUE_PY,
     'c["by"] == who["app"] and c["at"] >= since for c', 'c["by"] == who["app"] for c', ISSUE_TESTS),
    ("the readiness App's comment in the second of the investigation does not stand in", ISSUE_PY,
     'c["by"] == who["app"] and c["at"] >= since for c', 'c["by"] == who["app"] and c["at"] > since for c',
     ISSUE_TESTS),
    ("another App's comment stands in for a verdict", ISSUE_PY,
     'any(c["by"] == who["app"] and c["at"] >= since for c', 'any(c["at"] >= since for c', ISSUE_TESTS),
    # In ready: the opening Run, from a statement on an outsider's issue, for its branch head.
    ("an opening with no Role declared is admitted", ISSUE_PY,
     '    if who is None:\n        return _decision(facts, state, "intent_undeclared", [OPENING], t.NOTHING)\n', "",
     ISSUE_TESTS),
    ("an outsider's issue opens with no statement", ISSUE_PY,
     "    if not stated(facts, intents, mine):\n", "    if False:\n", ISSUE_TESTS),
    ("a person's own issue needs a statement", ISSUE_PY,
     '    if is_person(facts["author"]):\n        return True\n', "", ISSUE_TESTS),
    ("an investigating App's comment from before the edit is a statement", ISSUE_PY,
     'c["by"] == who["app"] and c["at"] > changed for c', 'c["by"] == who["app"] for c', ISSUE_TESTS),
    ("another App's comment is a statement", ISSUE_PY,
     'any(c["by"] == who["app"] and c["at"] > changed', 'any(c["at"] > changed', ISSUE_TESTS),
    ("an App's comment is a statement with no investigating Role declared", ISSUE_PY,
     "    if who is not None and any(", "    if any(", ISSUE_TESTS),
    ("a writer's comment is no statement", ISSUE_PY,
     "    return said is not None and said > changed\n", "    return False\n", ISSUE_TESTS),
    ("a writer's comment at the edit is a statement", ISSUE_PY,
     "said is not None and said > changed", "said is not None and said >= changed", ISSUE_TESTS),
    ("an unreadable branch head is admitted", ISSUE_PY,
     "    if not readable_head(facts):\n", "    if False:\n", ISSUE_TESTS),
    ("an empty branch head is read", ISSUE_PY,
     '(isinstance(facts["branch_head"], str) and facts["branch_head"] != "")',
     'isinstance(facts["branch_head"], str)', ISSUE_TESTS),
    ("the opening Run is admitted for no branch head", ISSUE_PY,
     '{"branch_head": facts["branch_head"]}', "{}", ISSUE_TESTS),
    # Issue 838: where the branch does not exist, the opening Run is admitted for the commit it lands on.
    ("an unreadable base is admitted", ISSUE_PY,
     "    if not readable_base(facts):\n", "    if False:\n",
     ("tests.test_issue.Opening.test_the_opening_run_of_a_branch_that_does_not_exist_is_admitted_for_the_commit_it_lands_on",)),
    ("a base that is not as long as a commit's name is read", ISSUE_PY,
     "isinstance(base, str) and len(base) == len(COMMIT_SHAPE) and all(", "isinstance(base, str) and all(",
     ("tests.test_issue.Opening.test_the_opening_run_of_a_branch_that_does_not_exist_is_admitted_for_the_commit_it_lands_on",)),
    ("a base that is no text is read", ISSUE_PY,
     "isinstance(base, str) and len(base) == len(COMMIT_SHAPE)", "len(base) == len(COMMIT_SHAPE)",
     ("tests.test_issue.Opening.test_the_opening_run_of_a_branch_that_does_not_exist_is_admitted_for_the_commit_it_lands_on",)),
    ("a base of other characters than a commit's name is read", ISSUE_PY,
     " and all(c in t.HEX_DIGITS for c in base)\n", "\n",
     ("tests.test_issue.Opening.test_the_opening_run_of_a_branch_that_does_not_exist_is_admitted_for_the_commit_it_lands_on",)),
    ("an unread base is said before what a person must act on", ISSUE_PY,
     "    who = intents[OPENING]\n    if who is None:\n",
     '    if facts.get("branch_head") is None and not readable_base(facts):\n'
     '        return _decision(facts, state, "base_unreadable", evidence, t.DEFER)\n'
     "    who = intents[OPENING]\n    if who is None:\n",
     ("tests.test_issue.Opening.test_the_opening_run_of_a_branch_that_does_not_exist_is_admitted_for_the_commit_it_lands_on",)),
    ("the opening Run is admitted for no base", ISSUE_PY,
     '{"branch_head": None, "base_head": facts["base_head"]}', '{"branch_head": None}',
     ("tests.test_issue.Opening.test_the_opening_run_of_a_branch_that_does_not_exist_is_admitted_for_the_commit_it_lands_on",)),
    ("a base is asked for where the branch stands", ISSUE_PY,
     '    if facts["branch_head"] is not None:\n', "    if False:\n",
     ("tests.test_issue.Opening.test_the_opening_run_of_a_branch_that_does_not_exist_is_admitted_for_the_commit_it_lands_on",)),
    ("a base is carried where the branch stands", ISSUE_PY,
     '        return (who["role"], OPENING, {"branch_head": facts["branch_head"]})\n',
     '        return (who["role"], OPENING, {"branch_head": facts["branch_head"], "base_head": facts.get("base_head")})\n',
     ("tests.test_issue.Opening.test_the_opening_run_of_a_branch_that_does_not_exist_is_admitted_for_the_commit_it_lands_on",)),
    ("an unread base stops the accepting of an issue", ISSUE_PY,
     "    if state == NEW:\n        return _accept(",
     '    if state == NEW:\n        if not readable_base(facts):\n            return _decision(facts, state, "base_unreadable", evidence, t.DEFER)\n        return _accept(',
     ("tests.test_issue.Opening.test_the_opening_run_of_a_branch_that_does_not_exist_is_admitted_for_the_commit_it_lands_on",)),
    ("an unread base is said before an unread branch head", ISSUE_PY,
     '    if not readable_head(facts):\n        return _decision(facts, state, "branch_unreadable", evidence, t.DEFER)\n'
     '    if facts["branch_head"] is not None:\n',
     '    if not readable_base(facts):\n        return _decision(facts, state, "base_unreadable", evidence, t.DEFER)\n'
     '    if not readable_head(facts):\n        return _decision(facts, state, "branch_unreadable", evidence, t.DEFER)\n'
     '    if facts["branch_head"] is not None:\n',
     ("tests.test_issue.Opening.test_the_opening_run_of_a_branch_that_does_not_exist_is_admitted_for_the_commit_it_lands_on",)),
    ("an unread base at the second asking is still admitted", ISSUE_PY,
     '    was, now = admitted.get("admit"), again.get("admit")\n',
     '    if again.get("reason") == "base_unreadable":\n        return True\n    was, now = admitted.get("admit"), again.get("admit")\n',
     ("tests.test_issue.Apply.test_the_default_branch_moving_does_not_stop_the_opening_run_and_a_branch_made_does",)),
    ("the default branch moving stops the opening Run", ISSUE_PY,
     "    return _but_base(now) == _but_base(was)\n", "    return now == was\n",
     ("tests.test_issue.Apply.test_the_default_branch_moving_does_not_stop_the_opening_run_and_a_branch_made_does",)),
    ("the branch head is left out with the base", ISSUE_PY,
     'for part in admit if part != "base_head"}', 'for part in admit if part not in ("base_head", "branch_head")}',
     ("tests.test_issue.Apply.test_the_default_branch_moving_does_not_stop_the_opening_run_and_a_branch_made_does",)),
    ("an admission of no base is still admitted where the second asking has one", ISSUE_PY,
     '    if "base_head" in now and not (readable_base(was) and readable_base(now)):\n        return False\n', "",
     ("tests.test_issue.Apply.test_the_default_branch_moving_does_not_stop_the_opening_run_and_a_branch_made_does",)),
    ("an admission's base need name no commit", ISSUE_PY,
     'if "base_head" in now and not (readable_base(was) and readable_base(now)):', 'if "base_head" in now and not readable_base(now):',
     ("tests.test_issue.Apply.test_the_default_branch_moving_does_not_stop_the_opening_run_and_a_branch_made_does",)),
    ("the second asking's base need name no commit", ISSUE_PY,
     'if "base_head" in now and not (readable_base(was) and readable_base(now)):', 'if "base_head" in now and not readable_base(was):',
     ("tests.test_issue.Apply.test_the_default_branch_moving_does_not_stop_the_opening_run_and_a_branch_made_does",)),
    ("a base on one admission alone is left out", ISSUE_PY,
     '    if ("base_head" in now) != ("base_head" in was):\n        return False\n', "",
     ("tests.test_issue.Apply.test_the_default_branch_moving_does_not_stop_the_opening_run_and_a_branch_made_does",)),
    ("an admission that was no mapping is asked of its parts", ISSUE_PY,
     "    if not isinstance(was, dict) or not isinstance(now, dict):\n", "    if not isinstance(now, dict):\n",
     ("tests.test_issue.Apply.test_the_default_branch_moving_does_not_stop_the_opening_run_and_a_branch_made_does",)),
    ("an admission that is no mapping now is asked of its parts", ISSUE_PY,
     "    if not isinstance(was, dict) or not isinstance(now, dict):\n", "    if not isinstance(was, dict):\n",
     ("tests.test_issue.Apply.test_the_default_branch_moving_does_not_stop_the_opening_run_and_a_branch_made_does",)),
    # The brakes, a Run in flight, and capacity.
    ("an issue's Run is not braked", ISSUE_PY,
     "    brake = brakes.on_run(_decision, facts, state, evidence, context, intent, since_writer(mine, facts), limits)\n"
     "    if brake:\n        return brake\n", "", ISSUE_TESTS),
    # Issue 171: while a Run is in flight, the ceilings are asked about the Run the State wants (decision 0003).
    ("an issue's ceilings are asked about the Run in flight", ISSUE_PY,
     "        if isinstance(wanted, tuple):\n" + ISSUE_DONE + ISSUE_CEILINGS,
     "        if True:\n" + ISSUE_DONE + ISSUE_CEILINGS.replace("wanted[1]", 'flight[0]["intent"]'),
     ISSUE_TESTS + (ISSUE_EXPLORED,)),
    ("the Run ceiling holds an issue that wants no Run while a Run waits", ISSUE_PY,
     "        if isinstance(wanted, tuple):\n" + ISSUE_DONE + ISSUE_CEILINGS,
     "        if True:\n" + ISSUE_DONE
     + ISSUE_CEILINGS.replace("wanted[1]", '(wanted[1] if isinstance(wanted, tuple) else "")'), ISSUE_TESTS),
    ("an issue's ceilings are asked of another Intent", ISSUE_PY,
     "wanted[1], done, limits)", "INVESTIGATE, done, limits)", ISSUE_TESTS),
    ("a Run in flight is counted against itself", ISSUE_PY, ISSUE_DONE,
     "            done = since_writer(mine, facts)\n", ISSUE_TESTS),
    ("a Pause is read for a Run in flight", ISSUE_PY, ISSUE_CEILINGS,
     "            held = brakes.on_run(_decision, facts, state, evidence, context, wanted[1], done, limits)\n",
     ISSUE_TESTS),
    ("a Run in flight hides the brakes' Hold", ISSUE_PY, "        if held:\n            return held\n", "",
     ISSUE_TESTS),
    ("a Run in flight on an issue does not stop another", ISSUE_PY,
     "    if flight:\n        held = None\n", "    if False:\n        held = None\n", ISSUE_TESTS),
    ("an issue in new wants a Run while a Run waits", ISSUE_PY,
     'wanted = None if bare["state"] == NEW else _run_wanted(', "wanted = _run_wanted(", ISSUE_TESTS),
    ("an issue's ceilings are asked of the Intent in flight", ISSUE_PY,
     "wanted[1], done, limits)", 'flight[0]["intent"], done, limits)', ISSUE_TESTS),
    ("the Run wanted is found from the State an opening Run in flight shows", ISSUE_PY,
     '    bare = d if reason != "opening_run" else derive(facts, without_opening(runs), config)\n',
     "    bare = d\n", ISSUE_TESTS),
    ("every Run in flight is left out to find the Run wanted", ISSUE_PY,
     'r["status"] == "completed" or r["intent"] != OPENING]', 'r["status"] == "completed"]', ISSUE_TESTS),
    # Decision 0036: a Run listed before its run-name defers every admission, after the brakes.
    ("an unidentified Run hides an issue's Hold", ISSUE_PY,
     *moved_after(ISSUE_PY, RUN_BRAKES, DEFERRAL_CALL),
     ("tests.test_issue.UnidentifiedRuns.test_an_unidentified_run_defers_an_issues_run",)),
    ("an issue's admission names no content", ISSUE_PY,
     '{"role": role, "intent": intent, "content_id": facts["content_id"]}', '{"role": role, "intent": intent}',
     ISSUE_TESTS),
    # Who each reason and State calls: one mutant to an entry.
    ("an issue's human_hold calls nobody", ISSUE_PY, '    "human_hold",\n', "", ISSUE_TESTS),
    ("an issue's linked_twice calls nobody", ISSUE_PY, '    "linked_twice",\n', "", ISSUE_TESTS),
    ("an issue's acceptance_lapsed calls nobody", ISSUE_PY, '    "acceptance_lapsed",\n', "", ISSUE_TESTS),
    ("an issue's attempts_exhausted calls nobody", ISSUE_PY, '    "attempts_exhausted",\n', "", ISSUE_TESTS),
    ("an issue's run_ceiling calls nobody", ISSUE_PY, '    "run_ceiling",\n', "", ISSUE_TESTS),
    ("an issue's environment_ceiling calls nobody", ISSUE_PY, '    "environment_ceiling",\n', "",
     ("tests.test_issue.Attention.test_each_reason_and_state_calls_whom_it_should",)),
    ("an issue's act_ceiling calls nobody", ISSUE_PY, '    "act_ceiling",\n', "", ISSUE_TESTS),
    ("an issue's triage_stands calls nobody", ISSUE_PY, '    "triage_stands",\n', "", ISSUE_TESTS),
    ("an issue's judged calls nobody", ISSUE_PY, '    "judged",\n', "", ISSUE_TESTS),
    ("an issue's ready_removed calls nobody", ISSUE_PY, '    "ready_removed",\n', "", ISSUE_TESTS),
    ("an issue's no_statement calls nobody", ISSUE_PY, '    "no_statement",\n', "", ISSUE_TESTS),
    ("an issue's intent_undeclared calls nobody", ISSUE_PY, '    "intent_undeclared",\n', "", ISSUE_TESTS),
    ("an issue's label_unreadable calls nobody", ISSUE_PY, '    "label_unreadable",\n', "", ISSUE_TESTS),
    ("an issue's issues_unreadable calls nobody", ISSUE_PY, '    "issues_unreadable",\n', "", ISSUE_TESTS),
    ("an issue's intents_unreadable calls nobody", ISSUE_PY, '    "intents_unreadable",\n', "", ISSUE_TESTS),
    ("an issue's intents_share_a_role calls nobody", ISSUE_PY, '    "intents_share_a_role",\n', "", ISSUE_TESTS),
    ("an issue's intents_share_an_app calls nobody", ISSUE_PY, '    "intents_share_an_app",\n', "", ISSUE_TESTS),
    ("an issue in DONE calls attention", ISSUE_PY, "    DONE,\n", "", ISSUE_TESTS),
    ("an issue in DECLINED calls attention", ISSUE_PY, "    DECLINED,\n", "", ISSUE_TESTS),
    ("an issue in t.NOT_SERVED calls attention", ISSUE_PY, "    t.NOT_SERVED,\n", "", ISSUE_TESTS),
    ("an issue in IN_REVIEW calls attention", ISSUE_PY, "    IN_REVIEW,\n", "", ISSUE_TESTS),
    ("an issue's not_accepted calls attention", ISSUE_PY, '    "not_accepted",\n', "", ISSUE_TESTS),
    ("an issue's triage_removed calls attention", ISSUE_PY, '    "triage_removed",\n', "", ISSUE_TESTS),
    # No act whose label stands; and a failed investigation's comment is no statement.
    ("an issue is accepted while factory:triage stands", ISSUE_PY,
     '    if latest_adds(facts["label_events"], LABEL_TRIAGE):\n', "    if False:\n", ISSUE_TESTS),
    ("a failed investigation's comment is a statement", ISSUE_PY,
     '        if not kept or any(r["conclusion"] == "success" and r["content_id"] == facts["content_id"] for r in kept):\n',
     "        if True:\n", ISSUE_TESTS),
    ("an investigation of other content makes its comment a statement", ISSUE_PY,
     ' and r["content_id"] == facts["content_id"] for r in kept):', " for r in kept):", ISSUE_TESTS),
    # What apply re-asks (I-21, I-38).
    ("apply writes whatever Run the Kernel admits now", ISSUE_PY,
     '    return _but_base(now) == _but_base(was)\n', '    return True\n', ISSUE_TESTS),
    ("apply writes when nothing is admitted", ISSUE_PY,
     '    if not isinstance(was, dict) or not isinstance(now, dict):\n        return False\n',
     '    if not isinstance(was, dict) or not isinstance(now, dict):\n        return now == was\n', ISSUE_TESTS),
    # An issue's wait past its State's limit (design §4.1, decision 0034).
    ("an issue never goes stale", ISSUE_PY,
     '    if (d["attention"] in t.MAY_GO_STALE and d["reason"] not in t.SCOPE_DEFERRALS\n', "    if (False\n",
     ISSUE_TESTS),
    ("an issue deferred for the whole scope goes stale", ISSUE_PY,
     ' and d["reason"] not in t.SCOPE_DEFERRALS\n', "\n", ISSUE_TESTS),
    ("an issue needing a person goes stale", ISSUE_PY, 'd["attention"] in t.MAY_GO_STALE and ', "",
     ("tests.test_issue.Stale.test_a_person_a_run_nobody_or_a_deferral_of_the_whole_scope_is_never_stale",)),
    ("every issue is held to triage's limit", ISSUE_PY,
     'overdue(config.get("lifecycle"), d["state"],', 'overdue(config.get("lifecycle"), TRIAGE,', ISSUE_TESTS),
    ("every issue is held to ready's limit", ISSUE_PY,
     'overdue(config.get("lifecycle"), d["state"],', 'overdue(config.get("lifecycle"), READY,', ISSUE_TESTS),
    ("an issue's limits are read from any Lifecycle", ISSUE_PY,
     ' and lifecycle.get("work_item") == WORK_ITEM)', ")", ISSUE_TESTS),
    ("an issue's new life does not move it", ISSUE_PY,
     '    times = [facts["life_started_at"]]\n', "    times = []\n", ISSUE_TESTS),
    ("an edit does not move an issue", ISSUE_PY, '    times += [facts["content_changed_at"]]\n', "", ISSUE_TESTS),
    ("a writer's action does not move an issue", ISSUE_PY,
     '    times += [facts.get("last_writer_action_at")]\n', "", ISSUE_TESTS),
    ("a writer's comment does not move an issue", ISSUE_PY,
     '    times += [facts.get("last_writer_comment_at")]\n', "", ISSUE_TESTS),
    ("a control label does not move an issue", ISSUE_PY,
     '    times += [ev["at"] for ev in facts["label_events"]\n', '    times += [ev["at"] for ev in []\n', ISSUE_TESTS),
    ("a Run's start does not move an issue", ISSUE_PY,
     '    times += [r["started_at"] for r in runs_on(runs, facts)]\n', "", ISSUE_TESTS),
    ("a linked pull request's opening does not move an issue", ISSUE_PY,
     '    times += [p["opened_at"] for p in linked]\n', "", ISSUE_TESTS),
    ("a linked pull request's close does not move an issue", ISSUE_PY,
     '    times += [p["closed_at"] for p in linked]\n', "", ISSUE_TESTS),
    ("any App's label moves an issue", ISSUE_PY,
     ' and (is_person(ev["by"]) or named(ev["by"], config))]', "]", ISSUE_TESTS),
    ("an App moves an issue only by the label it is named for", ISSUE_PY,
     'named(ev["by"], config))]', 'declared(ev["by"], ev["label"], config))]', ISSUE_TESTS),
    ("a label the Kernel does not read moves an issue", ISSUE_PY,
     'if ev["label"] in issue_labels() and (is_person(ev["by"])', 'if (is_person(ev["by"])', ISSUE_TESTS),
    ("a pull request of any class moves an issue", ISSUE_PY,
     '    linked = [p for p in facts["linked"] if p["class"] in MOVING_CLASSES]\n', '    linked = facts["linked"]\n',
     ISSUE_TESTS),
    ("an admitted outsider's pull request moves an issue", ISSUE_PY,
     'if p["class"] in MOVING_CLASSES]', "if is_linked(p)]", ISSUE_TESTS),
    ("a writer's pull request moves nothing", ISSUE_PY,
     'MOVING_CLASSES = ("agent", "maintainer")', 'MOVING_CLASSES = ("agent",)', ISSUE_TESTS),
    ("a time after now moves an issue", ISSUE_PY,
     "readable = [x for x in times if is_time(x) and x <= now]", "readable = [x for x in times if is_time(x)]",
     ISSUE_TESTS),
    ("a now that is no moment raises", ISSUE_PY, "    if not is_time(now):\n        return None\n", "", ISSUE_TESTS),
    ("a link with no opening time is read", ISSUE_PY,
     '    if not is_time(entry.get("opened_at")):\n', "    if False:\n", ISSUE_TESTS),
    ("an issue's limit that cannot be read is trusted", ISSUE_PY,
     "    if not (type(cap) in (int, float) and abs(cap) < float(\"inf\")):\n", "    if False:\n", ISSUE_TESTS),
    ("a bool is read as an issue's limit", ISSUE_PY,
     "type(cap) in (int, float)", "isinstance(cap, (int, float))", ISSUE_TESTS),
    ("an issue's limit that is not finite is read", ISSUE_PY, " and abs(cap) < float(\"inf\")):", "):", ISSUE_TESTS),
    ("an issue at its end goes stale", ISSUE_PY,
     "    if isinstance(ends, list) and state in ends:\n", "    if False:\n", ISSUE_TESTS),
    ("the App named for factory:ready moves no issue", ISSUE_PY,
     "any(declared(by, name, config) for name in (LABEL_TRIAGE, LABEL_READY))",
     "any(declared(by, name, config) for name in (LABEL_TRIAGE,))", ISSUE_TESTS),
    ("an issue with no time before now raises", ISSUE_PY,
     "    return max(readable) if readable else None\n", "    return max(readable)\n", ISSUE_TESTS),
    ("a link that closed before it opened is read", ISSUE_PY,
     "    if closed_on is not None and closed_on < opened_on:\n", "    if False:\n", ISSUE_TESTS),
    ("a link that closed in the second it opened cannot be read", ISSUE_PY,
     "closed_on is not None and closed_on < opened_on", "closed_on is not None and closed_on <= opened_on",
     ISSUE_TESTS),
    ("a link that merged before it opened is read", ISSUE_PY,
     "not (opened_on <= merged_on and merged_on <= closed_on)", "not merged_on <= closed_on", ISSUE_TESTS),
    ("a link that merged in the second it opened cannot be read", ISSUE_PY,
     "not (opened_on <= merged_on and merged_on <= closed_on)",
     "not (opened_on < merged_on and merged_on <= closed_on)", ISSUE_TESTS),
    ("a link that merged after it closed is read", ISSUE_PY,
     "not (opened_on <= merged_on and merged_on <= closed_on)", "not opened_on <= merged_on", ISSUE_TESTS),
    ("a link that merged in the second it closed cannot be read", ISSUE_PY,
     "not (opened_on <= merged_on and merged_on <= closed_on)",
     "not (opened_on <= merged_on and merged_on < closed_on)", ISSUE_TESTS),
    ("an issue's context that cannot be read raises", ISSUE_PY,
     "    known = context if isinstance(context, dict) else {}\n", "    known = context\n", ISSUE_TESTS),
    # Issue 267: a merge is read as it stood at the merge, by the close of the issue the timeline names it the closer of.
    ("a merge is read from the references as they stand now", ISSUE_PY,
     '    merged = [p for p in in_life if p["closed_issue_at"] is not None or closed_at(facts, p["merged_at"])]\n',
     '    merged = in_life\n', ISSUE_TESTS),
    ("a merge that closed nothing while the issue stood open counts", ISSUE_PY,
     '    merged = [p for p in in_life if p["closed_issue_at"] is not None or closed_at(facts, p["merged_at"])]\n',
     '    merged = [p for p in in_life if p["closed_issue_at"] is not None or facts["closed_first_at"] is not None]\n',
     ISSUE_TESTS),
    ("an issue an outsider reopened before a merge is read as closed at it", ISSUE_PY,
     '        return facts["state"] == "closed"\n', "        return True\n", ISSUE_TESTS),
    ("an issue an outsider reopened and closed again is read as open at a merge", ISSUE_PY,
     '        return facts["state"] == "closed"\n', "        return False\n", ISSUE_TESTS),
    ("an issue an outsider reopened in a merge's second is read as open at it", ISSUE_PY,
     'facts["reopened_last_at"] < when:', 'facts["reopened_last_at"] <= when:', ISSUE_TESTS),
    ("an issue closed in a merge's second is read as open at it", ISSUE_PY,
     '    if facts["closed_first_at"] is None or not facts["closed_first_at"] <= when:\n',
     '    if facts["closed_first_at"] is None or not facts["closed_first_at"] < when:\n', ISSUE_TESTS),
    ("a first merge that closed nothing is done", ISSUE_PY,
     '        if all(p["closed_issue_at"] is None for p in merged if p["merged_at"] == first):\n', "        if False:\n",
     ISSUE_TESTS),
    ("a close of the issue before the merge is read", ISSUE_PY,
     "(is_time(closer) and merged_on is not None and merged_on <= closer)", "(is_time(closer) and merged_on is not None)",
     ISSUE_TESTS),
    ("a close of the issue by an unmerged link is read", ISSUE_PY,
     "(is_time(closer) and merged_on is not None and merged_on <= closer)",
     "(is_time(closer) and (merged_on is None or merged_on <= closer))", ISSUE_TESTS),
    ("a close of the issue that is no time is read", ISSUE_PY,
     "(is_time(closer) and merged_on is not None and merged_on <= closer)",
     "(isinstance(closer, str) and merged_on is not None and merged_on <= closer)", ISSUE_TESTS),
    ("a link without its close of the issue is read as one that closed nothing", ISSUE_PY,
     '    closer = entry.get("closed_issue_at", "")\n', '    closer = entry.get("closed_issue_at")\n', ISSUE_TESTS),
    ("an open issue in the close's lag is read past", ISSUE_PY,
     "        if closing:\n", "        if False:\n", ISSUE_TESTS),
    ("an open issue read at the lag's limit still waits", ISSUE_PY,
     'seconds(facts["read_at"]) - seconds(p["merged_at"]) < lag]', 'seconds(facts["read_at"]) - seconds(p["merged_at"]) <= lag]',
     ISSUE_TESTS),
    ("a closed issue waits in the close's lag", ISSUE_PY,
     '    if in_life and facts["state"] == "open":\n', "    if in_life:\n", ISSUE_TESTS),
    ("a lag that is no whole number of seconds is read", ISSUE_PY,
     "        if not (type(lag) is int and lag >= 1):\n", "        if not isinstance(lag, (int, float)):\n", ISSUE_TESTS),
    ("a lag of no seconds is read", ISSUE_PY, "type(lag) is int and lag >= 1", "type(lag) is int and lag >= 0",
     ISSUE_TESTS),
    ("a read before the merge is read past", ISSUE_PY,
     'seconds(facts["read_at"]) - seconds(p["merged_at"]) < lag]',
     'abs(seconds(facts["read_at"]) - seconds(p["merged_at"])) < lag]', ISSUE_TESTS),
    ("a first merge beside one that closed the issue is the contradiction", ISSUE_PY,
     '        if all(p["closed_issue_at"] is None for p in merged if p["merged_at"] == first):\n',
     '        if any(p["closed_issue_at"] is None for p in merged if p["merged_at"] == first):\n', ISSUE_TESTS),
    ("an issue's limits_unreadable calls nobody", ISSUE_PY, '    "limits_unreadable",\n', "", ISSUE_TESTS),
    ("a read time that cannot be read is taken", ISSUE_PY,
     '        if not is_time(facts.get("read_at")):\n            return out(None, "linked_unreadable", [])\n', "",
     ISSUE_TESTS),
    # Issue 280: an outsider's merge never makes an issue done.
    ("an admitted outsider's merge makes the issue done", ISSUE_PY,
     '        if any(p["class"] != "outside" for p in closers):\n', '        if closers:\n', ISSUE_TESTS),
    ("an outsider's merge reads as any other close", ISSUE_PY,
     '        return out(DECLINED, "closed_by_outsider_merge", [str(p["number"]) for p in merged if p["class"] == "outside"])\n', '        return out(DECLINED, "closed", [])\n', ISSUE_TESTS),
    ("an issue's closed_by_outsider_merge calls nobody", ISSUE_PY, '    "closed_by_outsider_merge",\n', "", ISSUE_TESTS),
    ("an outsider's merge that closed nothing is named", ISSUE_PY,
     'closers = [p for p in merged if p["merged_at"] == first and p["closed_issue_at"] is not None]', 'closers = [p for p in merged if p["merged_at"] == first]', ISSUE_TESTS),
]

# The files of tools/mutants_of/, each the mutants of files outside kernel/, found by the walk in the order of their
# names, so that a change adding one edits no list here or there (issue 1101). OUTSIDE is their mutants, in that order.
AREA_NAME = re.compile(r"[a-z_][a-z0-9_]*")


def area_names(root: pathlib.Path) -> list:
    """The name of each file of mutants in `root`'s tools/mutants_of/: its Python files but __init__.py and common.py,
    directly in it, as the walk gives them."""
    folder = root / "tools" / "mutants_of"
    return [path.stem for path in walk.files(root, "tools/mutants_of")
            if path.parent == folder and path.suffix == ".py" and path.stem not in ("__init__", "common")]


def areas(root: pathlib.Path, load=importlib.import_module) -> tuple:
    """Each file of mutants in `root`, loaded by `load` in the order of the names. Each name is a module name, by
    AREA_NAME, before it is loaded: nothing but a file of tools/mutants_of/ is imported."""
    return tuple(load("tools.mutants_of." + name) for name in area_names(root) if AREA_NAME.fullmatch(name))


AREAS = areas(ROOT)
OUTSIDE = [mutant for area in AREAS for mutant in area.MUTANTS]
# Shared with tools/mutants_of/, and bound here so that an entry below may name them.
RESULT_PORT = common.RESULT_PORT

F849_BROKEN = ("tests.test_issue.Unreadable.test_a_chain_of_spans_the_records_broke_defers_on_its_own_code_and_calls_a_person",)
F849_SAID = common.F849_SAID
MUTANTS = ISSUE + OUTSIDE + [
    # Issue 346: a Lens review whose applied/1 is past retention on an open pull request is asked for again.
    ("a review past retention is never asked for again", 'kernel/derive.py',
     ' or review_expired(mine, facts, lens))', ')', ('tests.test_decide.OnlyAPersonEnds',)),
    ("a review that started before the expired Run answers it", 'kernel/derive.py',
     ' and r["started_at"] > last\n', '\n', ('tests.test_decide.OnlyAPersonEnds',)),
    ("an adjudication answers an expired review", 'kernel/derive.py',
     'return not any(r["role"] == role and r["intent"] == "review-change" and r["content_id"]',
     'return not any(r["role"] == role and r["content_id"]', ('tests.test_decide.OnlyAPersonEnds',)),
    ("the earliest expired Run is the one a review must follow", 'kernel/derive.py',
     '    last = max(gone)\n', '    last = min(gone)\n', ('tests.test_decide.OnlyAPersonEnds',)),
    ("a review still running answers an expired one", 'kernel/derive.py',
     '                   and r["status"] == "completed" and r["conclusion"] == "success" and r["started_at"] > last',
     '                   and r["conclusion"] in ("success", None) and r["started_at"] > last', ('tests.test_decide.OnlyAPersonEnds',)),
    ("a Run named as past retention that is none of the item's is ignored", 'kernel/derive.py',
     '    if unknown:\n        return {"state": None, "reason": "run_unreadable", "evidence": unknown}\n', '',
     ('tests.test_decide.OnlyAPersonEnds',)),
    ("a Run of another item named as past retention is read", 'kernel/derive.py',
     '{r["run"] for r in runs_on(runs, facts)})', '{r["run"] for r in runs})', ('tests.test_decide.OnlyAPersonEnds',)),
    ("a conflict admits a fix Run past a Run named as past retention that is none of the item's", 'kernel/derive.py',
     '    if unknown:\n', '    if unknown and facts["mergeable"] is not False:\n', ('tests.test_decide.OnlyAPersonEnds',)),
    ("a Lens's failure admits a fix Run past a Run named as past retention that is none of the item's", 'kernel/derive.py',
     '    if unknown:\n', '    if unknown and all(c["conclusion"] != "failure" for c in facts["checks"]):\n', ('tests.test_decide.OnlyAPersonEnds',)),
    ("a review of another item answers an expired one", 'kernel/derive.py',
     'review_expired(mine, facts, lens)', 'review_expired(runs, facts, lens)', ('tests.test_decide.OnlyAPersonEnds',)),
    ("a review that failed answers an expired one", 'kernel/derive.py',
     ' and r["conclusion"] == "success" and r["started_at"] > last\n', ' and r["started_at"] > last\n', ('tests.test_decide.OnlyAPersonEnds',)),
    ("a review of other content answers an expired one", 'kernel/derive.py',
     'return not any(r["role"] == role and r["intent"] == "review-change" and r["content_id"] == facts["content_id"]\n',
     'return not any(r["role"] == role and r["intent"] == "review-change"\n', ('tests.test_decide.OnlyAPersonEnds',)),
    ("another Lens's review answers an expired one", 'kernel/derive.py',
     'return not any(r["role"] == role and r["intent"]', 'return not any(r["intent"]', ('tests.test_decide.OnlyAPersonEnds',)),
    ("another Lens's expired Run asks this Lens's review again", 'kernel/derive.py',
     'gone = [r["started_at"] for r in runs if r["role"] == role and r["run"] in', 'gone = [r["started_at"] for r in runs if r["run"] in',
     ('tests.test_decide.OnlyAPersonEnds',)),
    ("a list of expired Runs that cannot be read is read as none", 'kernel/derive.py',
     '    if not readable_expired(facts):\n        return {"state": None, "reason": "facts_incomplete", "evidence": ["expired_reviews"]}\n',
     '', ('tests.test_decide.OnlyAPersonEnds',)),
    ("a list of expired Runs of anything but run ids is read", 'kernel/derive.py',
     ' and all(isinstance(run, str) for run in found)', '', ('tests.test_decide.OnlyAPersonEnds',)),
    # Issue 519: a description edited after the first approval since a person looked holds the item.
    ('a description edit after the approval holds nothing', 'kernel/derive.py',
     '    if anchor is not None and edited >= anchor:\n',
     '    if False:\n', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ('the edit is measured against the latest machine approval', 'kernel/derive.py',
     '        return min(approval_anchor(rv, mine) for rv in firsts)\n',
     '        return max(approval_anchor(rv, mine) for rv in firsts)\n', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ("a person's look in the edit's second clears it", 'kernel/derive.py',
     'if any(look > edited for look in looks):',
     'if any(look >= edited for look in looks):', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ("a person's look never starts the anchor again", 'kernel/derive.py',
     'firsts = [rv for rv in machine if last is None or rv["submitted_at"] >= last]',
     'firsts = machine', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ('a dismissed machine approval sets no anchor', 'kernel/derive.py',
     'if rv["by"]["kind"] == t.MACHINE_USER and approved[0] in (rv["state"], rv["dismissed_from"])',
     'if rv["by"]["kind"] == t.MACHINE_USER and rv["state"] == "approved"', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ('an edit time that cannot be read is taken', 'kernel/derive.py',
     '    if "description_edited_at" not in facts or (edited is not None and not is_time(edited)):\n        return {"state": None, "reason": "description_unreadable", "evidence": []}\n',
     '    if "description_edited_at" not in facts or (edited is not None and not is_time(edited)):\n        edited = None\n', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ('description_edited_after_approval calls nobody', 'kernel/decide.py',
     '    "description_edited_after_approval", "description_unreadable",\n',
     '    "description_unreadable",\n', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ("an outsider's edit is measured against the machine approval", 'kernel/derive.py',
     '    if facts["class"] == "outside":\n        seen = [look for look in looks if look <= edited]\n        return max(seen) if seen else None\n',
     '', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    # Issue 526: the facts port reads the description's edits, and an absent edit time is unread, never none (0140).
    ("an absent edit time is no edit", 'kernel/derive.py',
     '    if "description_edited_at" not in facts or (edited is not None and not is_time(edited)):\n',
     '    if edited is not None and not is_time(edited):\n',
     ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ("an edit time in words is no edit", 'kernel/derive.py',
     '    if "description_edited_at" not in facts or (edited is not None and not is_time(edited)):\n',
     '    if "description_edited_at" not in facts:\n',
     ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ("an edit in the anchor's second holds nothing", 'kernel/derive.py',
     'if anchor is not None and edited >= anchor:',
     'if anchor is not None and edited > anchor:', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ("an approval in a look's second anchors nothing", 'kernel/derive.py',
     'last is None or rv["submitted_at"] >= last]',
     'last is None or rv["submitted_at"] > last]', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ("an outsider's edit in the admission's second holds nothing", 'kernel/derive.py',
     'seen = [look for look in looks if look <= edited]',
     'seen = [look for look in looks if look < edited]', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ("an edit after a person's look escapes with no approval since", 'kernel/derive.py',
     '    return last if machine else None',
     '    return None', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ('an admission is a look on any pull request', 'kernel/derive.py',
     '    if facts["class"] == "outside":\n        looks += [',
     '    if True:\n        looks += [', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ("an App's admission is a person's look", 'kernel/derive.py',
     'if ev["label"] == t.LABEL_ADMIT and ev["action"] == "labeled" and is_person(ev["by"])]',
     'if ev["label"] == t.LABEL_ADMIT and ev["action"] == "labeled"]', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ('a removed admission is a look', 'kernel/derive.py',
     'if ev["label"] == t.LABEL_ADMIT and ev["action"] == "labeled" and is_person(ev["by"])]',
     'if ev["label"] == t.LABEL_ADMIT and is_person(ev["by"])]', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ("a person's approval dismissed since was no look", 'kernel/derive.py',
     '\n                                         or (rv["dismissed_from"] == "approved" and not is_person(rv["dismissed_by"])))]',
     ')]', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ("a person's dismissal leaves the look", 'kernel/derive.py',
     ' and not is_person(rv["dismissed_by"])))]',
     '))]', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ("a person's look anchors an edit with no approval ever", 'kernel/derive.py',
     '    return last if machine else None',
     '    return last', ('tests.test_decide.Convergence.test_a_description_edited_after_the_approval_holds_until_a_person_approves',)),
    ("a stranger's edit holds with a bound other than a person", 'kernel/derive.py',
     'return {"state": t.HELD, "reason": "description_edited_after_approval", "evidence": [edited]}',
     'return {"state": t.HELD, "reason": "approver_is_author_or_last_pusher", "evidence": [edited]}', ('tests.test_transitions.Transitions.test_a_stranger_only_stops_an_item_into_a_hold_a_person_ends',)),
    ("a reopening's time that cannot be read is read", 'kernel/derive.py',
     '    if "last_reopened_at" not in facts or not (facts["last_reopened_at"] is None or is_time(facts["last_reopened_at"])):\n        return True\n    for rv in facts["reviews"]:',
     '    for rv in facts["reviews"]:', ("tests.test_decide",)),
    ('an approval from before a reopening stands', 'kernel/derive.py',
     '\n            and (facts["last_reopened_at"] is None or rv["submitted_at"] > facts["last_reopened_at"])',
     '', ("tests.test_decide",)),
    ('an approval in the second of a reopening stands', 'kernel/derive.py',
     'rv["submitted_at"] > facts["last_reopened_at"]',
     'rv["submitted_at"] >= facts["last_reopened_at"]', ("tests.test_decide",)),
    ('an approval stands on a timeline not read whole', 'kernel/derive.py',
     '    if facts["complete"]["timeline"] is not True:\n        return None\n    for rv in facts["reviews"]:',
     '    for rv in facts["reviews"]:', ("tests.test_decide",)),
    # Issue 1025: each stage of a pass is timed in the log alone.
    ("the queue App is read as an issue's declared App", 'kernel/issue.py',
     'APP_KINDS = ("app", "lens")', 'APP_KINDS = ("app", "lens", "queue")',
     ('tests.test_issue.Counts.test_only_an_app_is_read_as_the_declared_app',
      'tests.test_issue.Investigation.test_once_its_record_has_expired_the_readiness_apps_label_or_comment_stands_in')),
    ("the queue App's label is the declared App's", 'kernel/issue.py',
     'by["kind"] in APP_KINDS and by["name"] == app', 'by["kind"] in ("app", "lens", "queue") and by["name"] == app',
     ('tests.test_issue.Counts.test_only_an_app_is_read_as_the_declared_app',)),
    ("the queue App's factory:ready stands in for the readiness verdict", 'kernel/issue.py',
     ' and ev["by"]["kind"] in APP_KINDS\n           and ev["by"]["name"] == who["app"]',
     ' and ev["by"]["kind"] in ("app", "lens", "queue")\n           and ev["by"]["name"] == who["app"]',
     ('tests.test_issue.Investigation.test_once_its_record_has_expired_the_readiness_apps_label_or_comment_stands_in',)),
    # Issue 195, ruling 4: an act or a Run asks the Kernel again before it writes (I-38).
    ("an act or a Run is still wanted for another item", "kernel/decide.py",
     ' or again.get("item") != decided.get("item"):\n',
     ':\n', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("an act or a Run is still wanted for an item that cannot be read", "kernel/decide.py",
     ' or not _a_pull_request(decided.get("item")) \\\n', ' \\\n', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("the item asked again is not read", "kernel/decide.py",
     '            or not _a_pull_request(again.get("item")) or', '            or', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("a repo is any truthy value", "kernel/decide.py",
     'isinstance(repo, str) and bool(repo)', 'bool(repo)', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("an issue is read as a pull request", "kernel/decide.py",
     '    if not isinstance(item, dict) or item.get("type") != "pull_request":\n', '    if not isinstance(item, dict):\n', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("a pull request with no repo is whole", "kernel/decide.py",
     '    return isinstance(repo, str) and bool(repo) and isinstance(number, int)', '    return isinstance(number, int)', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("a pull request of any number is whole", "kernel/decide.py",
     ' and isinstance(number, int) and not isinstance(number, bool) and number > 0\n', '\n', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("a Run named in part is still wanted", "kernel/decide.py",
     '        return (whole and decided.get("outcome")', '        return (decided.get("outcome")', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("a Run of an empty part is still wanted", "kernel/decide.py",
     'isinstance(admit.get(part), str) and admit.get(part)\n', 'admit.get(part) is not None\n', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("a Run is still wanted whatever the Kernel decides again", "kernel/decide.py",
     ' and again.get("outcome") == t.ADMIT\n', '\n', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("a Decision that admits nothing is still wanted as a Run", "kernel/decide.py",
     '        return (whole and decided.get("outcome") == t.ADMIT and', '        return (whole and', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("a Run is still wanted whatever is admitted again", "kernel/decide.py",
     '                and again.get("admit") == admit)\n',
     '                )\n', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("anything decided is still wanted", "kernel/decide.py",
     '            or not content:\n        return False\n',
     '            or not content:\n        return True\n', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("a Decision that is no act is still wanted as an approval", "kernel/decide.py",
     '    if decided.get("outcome") != t.ACT or decided.get("action")',
     '    if decided.get("action")', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("an enqueue is still wanted as an approval", "kernel/decide.py",
     ' or decided.get("action") != "issue_approval" or not isinstance',
     ' or not isinstance', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("an approval of no content is still wanted", "kernel/decide.py",
     ' or not isinstance(content, str) \\\n            or not content:\n',
     ':\n', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("an approval is still wanted whatever the Kernel decides again", "kernel/decide.py",
     '    return (again.get("outcome") == t.ACT and again.get("action") == "issue_approval"\n            and again.get("content_id") == decided.get("content_id"))\n',
     '    return True\n', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("an approval is still wanted for other content", "kernel/decide.py",
     ' == "issue_approval"\n            and again.get("content_id") == decided.get("content_id"))\n',
     ' == "issue_approval")\n', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("an approval is still wanted as another act", "kernel/decide.py",
     '    return (again.get("outcome") == t.ACT and again.get("action") == "issue_approval"\n',
     '    return (again.get("outcome") == t.ACT\n', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    ("an approval is still wanted whatever the outcome", "kernel/decide.py",
     '    return (again.get("outcome") == t.ACT and again.get("action") == "issue_approval"\n',
     '    return (again.get("action") == "issue_approval"\n', ("tests.test_decide.StillWanted", "tests.test_decide.TheFactorysOwnRules")),
    # Decision 0037: a person-only State is left by a person, or by a stranger's change left to a person.
    ("incomplete facts are trusted", "kernel/derive.py",
     "    gaps = incomplete(facts)\n", "    gaps = []\n", ("tests.test_decide.Readability",)),
    ("a list of Runs read short is trusted", "kernel/derive.py",
     "[name for name in t.READ_IN_FULL if flags.get(name) is not True]",
     '[name for name in t.READ_IN_FULL if name != "runs" and flags.get(name) is not True]',
     ("tests.test_decide.Readability",)),
    ("a timeline read short is trusted", "kernel/derive.py",
     "[name for name in t.READ_IN_FULL if flags.get(name) is not True]",
     '[name for name in t.READ_IN_FULL if name != "timeline" and flags.get(name) is not True]',
     ("tests.test_decide.Readability",)),
    ("a flag that is not exactly true counts as whole", "kernel/derive.py",
     "if flags.get(name) is not True]", "if not flags.get(name, True)]", ("tests.test_decide.Readability",)),
    ("incomplete facts are read before a merged or closed item", "kernel/derive.py",
     '    if facts["state"] == "merged":\n',
     "    if incomplete(facts):\n"
     '        return {"state": None, "reason": "facts_incomplete", "evidence": incomplete(facts)}\n'
     '    if facts["state"] == "merged":\n', ("tests.test_decide.Readability",)),
    ("model review before the checks pass", "kernel/derive.py",
     '    if waiting and "awaiting_checks" not in past:\n', "    if False:\n", ("tests.test_decide.Classes",)),
    ("a failed check is ignored", "kernel/derive.py",
     "    if failed:\n", "    if False:\n", ("tests.test_decide.HumanControl",)),
    ("a stranger's thread gates", "kernel/gate.py",
     "        if is_person(by):\n", '        if by["kind"] == "human":\n', ("tests.test_decide.HumanControl",)),
    ("a stranger is a person", "kernel/gate.py",
     'actor.get("kind") == "human" and actor.get("can_write") is True', 'actor.get("kind") == "human"',
     ("tests.test_decide.HumanControl",)),
    ("an App with write access is a person", "kernel/gate.py",
     'actor.get("kind") == "human" and actor.get("can_write") is True', 'actor.get("can_write") is True',
     ("tests.test_decide.HumanControl",)),
    ("a thread is closed by whoever resolves it", "kernel/gate.py",
     "        if closed(th):\n", '        if th["resolved"]:\n', ("tests.test_decide.OnlyAPersonEnds",)),
    ("a person's thread resolved by anyone closes", "kernel/gate.py",
     '        return is_person(by) and by["name"] == opener["name"]\n', "        return True\n",
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("a person's thread resolved by another writer closes", "kernel/gate.py",
     '        return is_person(by) and by["name"] == opener["name"]\n', "        return is_person(by)\n",
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("a Lens's thread resolved by anyone closes", 'kernel/gate.py',
     '        return is_person(by) or (by["kind"] == "queue" and (th["ruling"] == "accepted" or th.get("superseded") is True))\n',
     '        return True\n', ('tests.test_decide.OnlyAPersonEnds',)),
    ("a Lens's thread resolved by its own App closes", 'kernel/gate.py',
     'by["kind"] == "queue" and (th["ruling"]',
     'by["kind"] in ("queue", "lens") and (th["ruling"]', ('tests.test_decide.OnlyAPersonEnds',)),
    ("a person cannot close a Lens's thread", 'kernel/gate.py',
     'return is_person(by) or (by["kind"] == "queue"',
     'return (by["kind"] == "queue"', ('tests.test_decide.OnlyAPersonEnds',)),
    ("any App closes a Lens's thread on its accepted ruling", 'kernel/gate.py',
     '(by["kind"] == "queue" and',
     '(by["kind"] != "human" and', ('tests.test_decide.OnlyAPersonEnds',)),
    ('a ruling no Kernel word is read', 'kernel/derive.py',
     '    if "ruling" not in th or (th["ruling"] is not None and th["ruling"] not in t.RULINGS):\n        return True\n',
     '', ('tests.test_decide.OnlyAPersonEnds',)),
    ('a null ruling is unreadable', 'kernel/derive.py',
     '(th["ruling"] is not None and th["ruling"] not in t.RULINGS)',
     '(th["ruling"] not in t.RULINGS)', ('tests.test_decide.OnlyAPersonEnds',)),
    ('the queue App is no actor the Kernel knows', 'kernel/terms.py',
     '("human", "lens", "queue", "app", "machine_user")',
     '("human", "lens", "app", "machine_user")', ('tests.test_decide.OnlyAPersonEnds',)),
    ("a person's gate waits behind the resolve act", 'kernel/derive.py',
     ' and not any(g["by"]["kind"] == "human" for g in open_gates):', ':', ('tests.test_decide.OnlyAPersonEnds',)),
    ('a thread its Lens accepted is never resolved', 'kernel/derive.py',
     '    if due and "resolve_due" not in past and not any(',
     '    if False and not any(', ('tests.test_decide.OnlyAPersonEnds',)),
    ('a thread its Lens rejected is resolved', 'kernel/derive.py',
     '           and (th["ruling"] == "accepted" or th.get("superseded") is True)]',
     '           and (th["ruling"] is not None or th.get("superseded") is True)]', ('tests.test_decide.OnlyAPersonEnds',)),
    ('a thread already resolved is resolved again', 'kernel/derive.py',
     'if th["opened_by"]["kind"] == "lens" and not th["resolved"]\n',
     'if th["opened_by"]["kind"] == "lens"\n', ('tests.test_decide.OnlyAPersonEnds',)),
    ("a person's thread is resolved by the act", 'kernel/derive.py',
     'if th["opened_by"]["kind"] == "lens" and not th["resolved"]\n',
     'if not th["resolved"]\n', ('tests.test_decide.OnlyAPersonEnds',)),
    ('a queued item resolves before a gating thread takes it out', 'kernel/terms.py',
     ', "awaiting_review", "resolve_due")',
     ', "awaiting_review")', ('tests.test_decide.OnlyAPersonEnds',)),
    ('the resolve act is another act', 'kernel/decide.py',
     '    if reason == "resolve_due":\n        return "resolve_thread"\n',
     '', ('tests.test_decide.OnlyAPersonEnds',)),
    ('a resolve act is never made', 'kernel/decide.py',
     '    if state == t.CONVERGED or reason == "resolve_due":',
     '    if state == t.CONVERGED:', ('tests.test_decide.OnlyAPersonEnds',)),
    ('a resolve act is held at the Run ceiling', 'kernel/decide.py',
     '    if state == t.ADJUDICATING and reason != "resolve_due":',
     '    if state == t.ADJUDICATING:', ('tests.test_decide.OnlyAPersonEnds',)),
    ("a thread's opener is not read", "kernel/derive.py",
     'if not readable_actor(th.get("opened_by"), facts, config) or ', "if ", ("tests.test_decide.OnlyAPersonEnds",)),
    ("whether a thread is resolved is read loosely", "kernel/derive.py",
     ' or type(th.get("resolved")) is not bool:', ":", ("tests.test_decide.OnlyAPersonEnds",)),
    ("who resolved a thread is not read", "kernel/derive.py",
     '    if th["resolved"] and not readable_actor(th.get("resolved_by"), facts, config):\n        return True\n', "",
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("an open thread that names who resolved it is trusted", "kernel/derive.py",
     '    if not th["resolved"] and th.get("resolved_by") is not None:\n        return True\n', "",
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("a required Lens's thread resolved by another App is not read", "kernel/derive.py",
     'return (not closed(th) and th["opened_by"]', 'return (not th["resolved"] and th["opened_by"]',
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("a minor finding gates", "kernel/gate.py",
     'th["severity"] in GATING_SEVERITIES', "True", ("tests.test_decide.Convergence",)),
    ("a null category on a required Lens's thread is read as not security", "kernel/derive.py",
     'th.get("category") not in t.CATEGORIES', 'th.get("category") not in t.CATEGORIES + (None,)',
     ("tests.test_decide.Convergence",)),
    ("a null severity is readable", "kernel/derive.py",
     'th.get("severity") not in t.SEVERITIES', 'th.get("severity") not in t.SEVERITIES + (None,)',
     ("tests.test_decide.Convergence",)),
    ("a category outside the enum is read", "kernel/derive.py",
     'th.get("category") not in t.CATEGORIES', 'th.get("category") is None', ("tests.test_decide.Convergence",)),
    ("a thread from a Lens that is not required must be readable", "kernel/derive.py",
     'th["opened_by"]["kind"] == "lens" and th["opened_by"]["name"] in lenses\n',
     'th["opened_by"]["kind"] == "lens"\n', ("tests.test_decide.Convergence",)),
    ("a model Lens's unreadable thread is read on a dependency update", "kernel/derive.py",
     '    lenses = config["required_lenses"]["model"]\n', "    lenses = required_model_lenses(facts, config)\n",
     ("tests.test_decide.Convergence",)),
    ("an unreadable thread is read after a model review is admitted", "kernel/derive.py",
     *moved_after("kernel/derive.py", THREAD_GUARD, REVIEW_WAIT), ("tests.test_decide.OnlyAPersonEnds",)),
    ("an unreadable thread is not the Maintainer's to see", "kernel/decide.py",
     '"review_unreadable", "thread_unreadable",', '"review_unreadable",', ("tests.test_decide.OnlyAPersonEnds",)),
    ("a security finding gates by its severity", "kernel/gate.py",
     'th["category"] == SECURITY or ', "", ("tests.test_decide.Convergence",)),
    ("a security finding from a lens that is not required gates", "kernel/gate.py",
     'by["name"] in required and (', '(by["name"] in required or th["category"] == SECURITY) and (',
     ("tests.test_decide.Convergence",)),
    ("an empty diff converges", "kernel/derive.py",
     'if facts["diff"]["files"] == 0:', "if False:", ("tests.test_decide.HumanControl",)),
    ("admission survives a push", "kernel/derive.py",
     'return placed["at"] > facts["last_push_at"]', "return True", ("tests.test_decide.OnlyAPersonEnds",)),
    ("an admission anyone placed admits", "kernel/derive.py",
     '    if placed is None or not is_person(placed["by"]):\n', "    if placed is None:\n",
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("an unreadable label event is trusted", "kernel/derive.py", LABEL_GUARD, "",
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("an unreadable label event is read after a Hold", "kernel/derive.py",
     *moved_after("kernel/derive.py", LABEL_GUARD,
                  '        return {"state": t.HELD, "reason": "human_hold", "evidence": stops}\n'),
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("an unreadable label event is not the Maintainer's to see", "kernel/decide.py",
     '"thread_unreadable", "label_unreadable",', '"thread_unreadable",', ("tests.test_decide.OnlyAPersonEnds",)),
    ("an event whose label cannot be read is passed over", "kernel/derive.py",
     '        if not isinstance(ev, dict) or not isinstance(ev.get("label"), str):\n            return True\n',
     '        if not isinstance(ev, dict) or not isinstance(ev.get("label"), str):\n            continue\n',
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("what was done to a label is not read", "kernel/derive.py",
     '        if ev.get("action") not in t.LABEL_ACTIONS:\n            return True\n', "",
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("when a label event happened is not read", "kernel/derive.py",
     '        if not is_time(ev.get("at")):\n            return True\n', "", ("tests.test_decide.OnlyAPersonEnds",)),
    ("who added or removed a label is not read", "kernel/derive.py",
     '        if not readable_actor(ev.get("by"), facts, config):\n            return True\n', "",
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("a label anyone removes is released", "kernel/derive.py",
     '        elif is_person(ev["by"]):\n', "        else:\n", ("tests.test_decide.OnlyAPersonEnds",)),
    ("label events are read in the order given", "kernel/derive.py",
     'sorted([ev for ev in facts["label_events"] if ev["label"] in t.CONTROL_LABELS], key=label_order)',
     '[ev for ev in facts["label_events"] if ev["label"] in t.CONTROL_LABELS]', ("tests.test_decide.OnlyAPersonEnds",)),
    ("in the same second a label event is read in the order given", "kernel/derive.py",
     '    return ev["at"], (ev["action"] == "labeled") == placed_last\n', '    return ev["at"], False\n',
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("in the same second an admission stands", "kernel/derive.py",
     '    placed_last = ev["label"] != t.LABEL_ADMIT\n', "    placed_last = True\n",
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("in the same second a Hold is ended", "kernel/derive.py",
     '    placed_last = ev["label"] != t.LABEL_ADMIT\n', '    placed_last = ev["label"] == t.LABEL_HANDS_OFF\n',
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("in the same second hands-off is ended", "kernel/derive.py",
     '    placed_last = ev["label"] != t.LABEL_ADMIT\n', '    placed_last = ev["label"] == t.LABEL_HOLD\n',
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("anyone's removal in the same second ties with hands-off", "kernel/derive.py",
     '\n               and is_person(ev["by"]) for ev in facts["label_events"])', ' for ev in facts["label_events"])',
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("another label's removal in the same second ties with hands-off", "kernel/derive.py",
     'return any(ev["label"] == placed["label"] and ev["action"]', 'return any(ev["action"]',
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("a removal at another time ties with hands-off", "kernel/derive.py",
     ' and ev["action"] == "unlabeled" and ev["at"] == placed["at"]\n', ' and ev["action"] == "unlabeled"\n',
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("a person's thread is closed by anyone of that person's name", "kernel/gate.py",
     '        return is_person(by) and by["name"] == opener["name"]\n', '        return by["name"] == opener["name"]\n',
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("the queue App closes a Lens's thread on any ruling", 'kernel/gate.py',
     '(by["kind"] == "queue" and (th["ruling"] == "accepted" or',
     '(by["kind"] == "queue" and (True or', ('tests.test_decide.OnlyAPersonEnds',)),
    ("hands-off tied with its removal binds as hands-off", "kernel/derive.py",
     ' and is_person(placed["by"]) and not tied(placed, facts)\n', ' and is_person(placed["by"])\n',
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("anyone placing a label again replaces a person's placement", "kernel/derive.py",
     '            if not (ev["label"] in out and is_person(out[ev["label"]]["by"]) and not is_person(ev["by"])):\n',
     "            if True:\n", ("tests.test_decide.OnlyAPersonEnds",)),
    ("hands-off is read from a timeline read short", "kernel/derive.py",
     '    if "timeline" in incomplete(facts) or unreadable_labels(facts, config):\n',
     "    if unreadable_labels(facts, config):\n", ("tests.test_decide.OnlyAPersonEnds",)),
    ("a person named like an App's bot is read", "kernel/derive.py",
     '    if actor["kind"] == "human" and actor["name"].endswith(t.BOT_SUFFIX):\n        return False\n', "",
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("the machine user's approval stands without write access", "kernel/derive.py",
     '            and rv["by"]["can_write"] is True\n', "", ("tests.test_decide.OnlyAPersonEnds",)),
    ("hands-off anyone placed binds as hands-off", "kernel/derive.py",
     '    return placed is not None and is_person(placed["by"]) and not tied(placed, facts)\n',
     "    return placed is not None and not tied(placed, facts)\n", ("tests.test_decide.OnlyAPersonEnds",)),
    ("hands-off anyone else placed is ignored", "kernel/derive.py",
     STOPS, STOPS.replace("(t.LABEL_HOLD, t.LABEL_HANDS_OFF)", "(t.LABEL_HOLD,)"),
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("hands-off with an unreadable event leaves a queued item alone", "kernel/derive.py",
     '    if "timeline" in incomplete(facts) or unreadable_labels(facts, config):\n',
     '    if "timeline" in incomplete(facts):\n', ("tests.test_decide.OnlyAPersonEnds",)),
    # Not the old line, `rv["by"]["name"] == config["approver"]`: readable_actor holds that name to the machine user
    # and the machine user to it, so put back it would be an equivalent mutant, which no test can notice.
    ("an approval by anyone stands", "kernel/derive.py",
     '            rv["by"]["kind"] == t.MACHINE_USER\n', '            rv["by"]["kind"] in t.ACTOR_KINDS\n',
     ("tests.test_decide.HumanControl",)),
    ("the approver read as a person is trusted", "kernel/derive.py",
     '(actor["kind"] == t.MACHINE_USER) != (actor["name"] == config["approver"])',
     'actor["kind"] == t.MACHINE_USER and actor["name"] != config["approver"]', ("tests.test_decide.HumanControl",)),
    ("another name read as the machine user is trusted", "kernel/derive.py",
     '(actor["kind"] == t.MACHINE_USER) != (actor["name"] == config["approver"])',
     'actor["name"] == config["approver"] and actor["kind"] != t.MACHINE_USER', ("tests.test_decide.OnlyAPersonEnds",)),
    ("an author bot read as a person is trusted", "kernel/derive.py",
     '    return not (facts["class"] in t.BOT_CLASSES and actor["name"] == facts["author"] and actor["kind"] != t.APP)\n',
     "    return True\n", ("tests.test_decide.OnlyAPersonEnds",)),
    ("the author of a maintainer's pull request must be an App", "kernel/derive.py",
     'return not (facts["class"] in t.BOT_CLASSES and actor["name"]', 'return not (actor["name"]',
     ("tests.test_decide.Readability",)),
    ("an approval of other content stands", "kernel/derive.py",
     'and rv["content_id"] == facts["content_id"]\n            and (facts', "and (facts", ("tests.test_decide.Classes",)),
    ("a review of other content counts", "kernel/derive.py",
     '        and r["content_id"] == facts["content_id"]\n        and r["status"] == "completed"',
     '        and r["status"] == "completed"', ("tests.test_decide.Content",)),
    ("the hold label is ignored", "kernel/derive.py",
     STOPS, STOPS.replace("(t.LABEL_HOLD, t.LABEL_HANDS_OFF)", "(t.LABEL_HANDS_OFF,)"),
     ("tests.test_decide.Readability",)),
    ("an unknown merge state is read as mergeable", "kernel/derive.py",
     '    if mergeable is not True and "mergeable_unreadable" not in past:\n', "    if False:\n",
     ("tests.test_decide.Readability",)),
    ("only a null merge state is unknown", "kernel/derive.py",
     'if mergeable is not True and', "if mergeable is None and", ("tests.test_decide.Readability",)),
    ("a conflict is not sent back to the author", "kernel/derive.py",
     "    if mergeable is False:\n", "    if False:\n", ("tests.test_decide.HumanControl",)),
    ("the merge state is read before a merged, closed, held, draft or queued item", "kernel/derive.py",
     '    if facts["state"] == "merged":\n',
     '    if facts.get("mergeable") is not True and facts.get("mergeable") is not False:\n'
     '        return {"state": None, "reason": "mergeable_unreadable", "evidence": []}\n'
     '    if facts["state"] == "merged":\n', ("tests.test_decide.Readability",)),
    ("a dependency update waits for a model review", "kernel/derive.py",
     "    lenses = required_model_lenses(facts, config)\n",
     '    lenses = config["required_lenses"]["model"]\n', ("tests.test_decide.Classes",)),
    ("a model Lens's thread does not gate a dependency update", "kernel/gate.py",
     '    required = set(config["required_lenses"]["model"])\n',
     '    lenses = config["required_lenses"]\n'
     '    required = set() if facts["class"] in lenses["model_not_required_for"] and facts["last_pusher"] == '
     'facts["author"] else set(lenses["model"])\n', ("tests.test_decide.Classes",)),
    # The token sweep after slice 1's third dry run: each step's token holds every read its code can reach.
    ("a check no Lens names is foreign where its App is not shown", "kernel/derive.py",
     '            if not named_for(c, lens) or reports_for(c, lens):\n',
     '            if reports_for(c, lens) or (not named_for(c, lens) and type(c.get("app_id")) is int):\n',
     ("tests.test_decide.Content.test_a_check_no_lens_names_whose_app_is_not_shown_changes_no_decision",)),
    ("a null App is taken for a Lens's", "kernel/derive.py",
     '    return type(app) is int and type(lens["app_id"]) is int and app == lens["app_id"]\n',
     '    return app is None or (type(app) is int and type(lens["app_id"]) is int and app == lens["app_id"])\n',
     ("tests.test_decide.Content.test_a_check_from_another_app_is_unreadable_for_its_lens",)),
    # Decision 0232: a pull request the Factory opened stands with its issue, held while a person holds or has closed it.
    ('a pull request whose issue a person held or closed goes on', 'kernel/derive.py',
     '        if stands != t.ISSUE_OPEN:\n            return {"state": t.HELD, "reason": "issue_stopped", "evidence": [stands]}\n',
     '', STOOD),
    ('how its issue stands, not read, is read as a stop', 'kernel/derive.py',
     '        if stands not in t.ISSUE_STANDS:\n            return {"state": None, "reason": "issue_stands_unreadable", "evidence": []}\n',
     '', STOOD),
    ('a pull request whose issue was closed goes on', 'kernel/derive.py',
     '        if stands != t.ISSUE_OPEN:\n',
     '        if stands == "held":\n', STOOD),
    ('a word the Kernel does not know for how its issue stands is a stop', 'kernel/derive.py',
     '        if stands not in t.ISSUE_STANDS:\n',
     '        if stands is None:\n', STOOD),
    ('every pull request stands with an issue', 'kernel/derive.py',
     '    if opened_for_an_issue(facts):\n        stands = facts.get("issue_stands")\n',
     '    if True:\n        stands = facts.get("issue_stands")\n', STOOD),
    ('an issue a person closed stops nothing', 'kernel/terms.py',
     'ISSUE_OPEN = "open"\n',
     'ISSUE_OPEN = "closed"\n', STOOD),
    ('an issue a person held is a word the Kernel does not know', 'kernel/terms.py',
     'ISSUE_STANDS = ("open", "held", "closed")',
     'ISSUE_STANDS = ("open", "closed")', STOOD),
    ('a pull request held for its issue calls nobody', 'kernel/decide.py',
     '"human_hold", "issue_stopped", "issue_stands_unreadable",',
     '"human_hold", "issue_stands_unreadable",', STOOD),
    ('an issue that was not read calls nobody', 'kernel/decide.py',
     '"human_hold", "issue_stopped", "issue_stands_unreadable",',
     '"human_hold", "issue_stopped",', STOOD),
    ("a pull request's issue is read before a person's own Hold on it", 'kernel/derive.py',
     '    if stops:\n        return {"state": t.HELD, "reason": "human_hold", "evidence": stops}\n    # A pull request the Factory opened',
     '    if stops and not (opened_for_an_issue(facts) and facts.get("issue_stands") != t.ISSUE_OPEN):\n        return {"state": t.HELD, "reason": "human_hold", "evidence": stops}\n    # A pull request the Factory opened', STOOD),
    ("a person's hands-off yields to a stop on its issue", 'kernel/derive.py',
     '    if hands_off(facts, config):\n        return {"state": t.HELD, "reason": "hands_off", "evidence": [t.LABEL_HANDS_OFF]}\n',
     '    if hands_off(facts, config) and not (opened_for_an_issue(facts) and facts.get("issue_stands") != t.ISSUE_OPEN):\n        return {"state": t.HELD, "reason": "hands_off", "evidence": [t.LABEL_HANDS_OFF]}\n', STOOD),
    ('how an issue stands is read from a state GitHub does not give', 'kernel/issue.py',
     '    if not isinstance(facts, dict) or facts.get("state") not in ISSUE_STATES:\n        return None\n    if facts["state"] == "closed":\n',
     '    if not isinstance(facts, dict):\n        return None\n    if facts.get("state") == "closed":\n', STANDS_UNREAD),
    ('an issue closed stops nothing', 'kernel/issue.py',
     '    if facts["state"] == "closed":\n        return "closed"\n',
     '', STANDS_READ),
    ('an issue closed is read only from label events read whole', 'kernel/issue.py',
     '    if facts["state"] == "closed":\n        return "closed"\n',
     '    if facts["state"] == "closed" and readable_events(facts.get("label_events"), config):\n        return "closed"\n', STANDS_READ),
    ('label events read short are read for how an issue stands', 'kernel/issue.py',
     '    if not (isinstance(flags, dict) and flags.get("timeline") is True and readable_events(',
     '    if not (isinstance(flags, dict) and readable_events(', STANDS_UNREAD),
    ('a timeline flag of any truth reads as whole for how an issue stands', 'kernel/issue.py',
     '    if not (isinstance(flags, dict) and flags.get("timeline") is True and readable_events(',
     '    if not (isinstance(flags, dict) and flags.get("timeline") and readable_events(', STANDS_UNREAD),
    ('a label event that cannot be read whole is read for how an issue stands', 'kernel/issue.py',
     ' and readable_events(facts.get("label_events"), config)):\n        return None\n    labels = standing_labels(facts)\n',
     '):\n        return None\n    labels = standing_labels(facts)\n', STANDS_UNREAD),
    ("a person's hands-off on an issue stops its pull request", 'kernel/issue.py',
     '    if placed_by_a_person(labels, facts):\n        return t.ISSUE_OPEN\n',
     '', STANDS_READ),
    ("a person's hands-off on an issue is read from label events read short", 'kernel/issue.py',
     '    if not (isinstance(flags, dict) and flags.get("timeline") is True and readable_events(facts.get("label_events"), config)):\n        return None\n    labels = standing_labels(facts)\n    if placed_by_a_person(labels, facts):\n        return t.ISSUE_OPEN\n',
     '    labels = standing_labels(facts) if isinstance(facts.get("label_events"), list) and all(isinstance(ev, dict) and "by" in ev and isinstance(ev["by"], dict) for ev in facts["label_events"]) else {}\n    if labels and placed_by_a_person(labels, facts):\n        return t.ISSUE_OPEN\n    if not (isinstance(flags, dict) and flags.get("timeline") is True and readable_events(facts.get("label_events"), config)):\n        return None\n', STANDS_UNREAD),
    ('a Hold on an issue stops nothing', 'kernel/issue.py',
     '    return t.HELD if t.LABEL_HOLD in labels or t.LABEL_HANDS_OFF in labels else t.ISSUE_OPEN\n',
     '    return t.HELD if t.LABEL_HANDS_OFF in labels else t.ISSUE_OPEN\n', STANDS_READ),
    ('hands-off on an issue stops nothing', 'kernel/issue.py',
     '    return t.HELD if t.LABEL_HOLD in labels or t.LABEL_HANDS_OFF in labels else t.ISSUE_OPEN\n',
     '    return t.HELD if t.LABEL_HOLD in labels else t.ISSUE_OPEN\n', STANDS_READ),
    ('factory:admit on an issue holds its pull request', 'kernel/issue.py',
     '    return t.HELD if t.LABEL_HOLD in labels or t.LABEL_HANDS_OFF in labels else t.ISSUE_OPEN\n',
     '    return t.HELD if labels else t.ISSUE_OPEN\n', STANDS_READ),
    ('how an issue stands reads whether it is served', 'kernel/issue.py',
     '    labels = standing_labels(facts)\n    if placed_by_a_person(labels, facts):\n',
     '    labels = standing_labels(facts)\n    if not served(facts, config):\n        return t.ISSUE_OPEN\n    if placed_by_a_person(labels, facts):\n', ('tests.test_issue.Stands.test_no_row_of_the_issues_own_reading_is_read',)),
    # Issue 836, decision 0231: no issue rule reads when a Run's jobs began, so the records port asks no issue's Run.
    ('the readiness Run behind a label is dated by when its jobs began', 'kernel/issue.py',
     'if r["intent"] == JUDGE_READINESS and r["started_at"] <= at]',
     'if r["intent"] == JUDGE_READINESS and (r["began_at"] if r.get("began_at") else r["started_at"]) <= at]', ('tests.test_issue.RunStarts.test_an_issues_decision_is_the_same_whatever_began_at_its_runs_carry',)),
    ('the latest readiness Run is told by when its jobs began', 'kernel/issue.py',
     '    last = max(r["started_at"] for r in mine)\n',
     '    last = max((r["began_at"] if r.get("began_at") else r["started_at"]) for r in mine)\n', ('tests.test_issue.RunStarts.test_an_issues_decision_is_the_same_whatever_began_at_its_runs_carry',)),
    ("an investigation is current from when its Run's jobs began", 'kernel/issue.py',
     '    times = [r["started_at"] for r in kept\n',
     '    times = [(r["began_at"] if r.get("began_at") else r["started_at"]) for r in kept\n', ('tests.test_issue.RunStarts.test_an_issues_decision_is_the_same_whatever_began_at_its_runs_carry',)),
    ("a verdict is since the investigation by when its Run's jobs began", 'kernel/issue.py',
     'and r["started_at"] >= since\n',
     'and (r["began_at"] if r.get("began_at") else r["started_at"]) >= since\n', ('tests.test_issue.RunStarts.test_an_issues_decision_is_the_same_whatever_began_at_its_runs_carry',)),
    ("an issue last moved when a Run's jobs began", 'kernel/issue.py',
     '    times += [r["started_at"] for r in runs_on(runs, facts)]\n',
     '    times += [(r["began_at"] if r.get("began_at") else r["started_at"]) for r in runs_on(runs, facts)]\n', ('tests.test_issue.RunStarts.test_an_issues_decision_is_the_same_whatever_began_at_its_runs_carry',)),
    ('the Runs since a writer acted are counted by when their jobs began', 'kernel/derive.py',
     '    return [r for r in runs if r["started_at"] > mark]\n',
     '    return [r for r in runs if (r["began_at"] if r.get("began_at") else r["started_at"]) > mark]\n', ('tests.test_issue.RunStarts.test_an_issues_decision_is_the_same_whatever_began_at_its_runs_carry',)),
    ("an issue's Runs are ordered by when their jobs began", 'kernel/derive.py',
     '    return sorted(mine, key=lambda r: r["started_at"])\n',
     '    return sorted(mine, key=lambda r: r.get("began_at") or r["started_at"])\n', ('tests.test_issue.RunStarts.test_an_issues_decision_is_the_same_whatever_began_at_its_runs_carry',)),
    ('readiness Runs started in one second are tied by when their jobs began', 'kernel/issue.py',
     '               for r in mine if r["started_at"] == last)\n',
     '               for r in mine if (r.get("began_at") or r["started_at"]) == last)\n', ('tests.test_issue.RunStarts.test_an_issues_decision_is_the_same_whatever_began_at_its_runs_carry',)),
    # On a pull request the shards decline; on a merge group every shard runs.
    ("a conclusion the map does not name is read as passing", "kernel/derive.py",
     'config["check_conclusions"].get(check["conclusion"], "unreadable")',
     'config["check_conclusions"].get(check["conclusion"], "passing")', ("tests.test_decide.Content",)),
    ("a reading the Kernel does not know is trusted", "kernel/derive.py",
     '    if readings - {"passing", "pending", "concluding"}:\n', '    if "unreadable" in readings:\n',
     ("tests.test_decide.Content",)),
    ("an absent required check passes", "kernel/derive.py",
     '    if not mine:\n        return "pending"\n', '    if not mine:\n        return "passing"\n',
     ("tests.test_decide.Content",)),
    ("another App's check is read for a Lens", "kernel/derive.py",
     "    return named_for(check, lens) and from_its_app(check, lens) and from_its_workflow(check, lens)\n",
     "    return named_for(check, lens) and from_its_workflow(check, lens)\n", ("tests.test_decide.Content",)),
    ("an App id in the facts that is not a whole number is read", "kernel/derive.py",
     '    return type(app) is int and type(lens["app_id"]) is int and', '    return type(lens["app_id"]) is int and',
     ("tests.test_decide.Content",)),
    ("an App id in the configuration that is not a whole number is read", "kernel/derive.py",
     '    return type(app) is int and type(lens["app_id"]) is int and', "    return type(app) is int and",
     ("tests.test_decide.Content",)),
    ("another workflow file's check is read for a Lens", "kernel/derive.py",
     "    return named_for(check, lens) and from_its_app(check, lens) and from_its_workflow(check, lens)\n",
     "    return named_for(check, lens) and from_its_app(check, lens)\n", ("tests.test_decide.Content",)),
    ("a check that names no workflow is read for a Lens that names none", "kernel/derive.py",
     '    return "workflow" in check and check["workflow"] == lens["workflow"]\n',
     '    return check.get("workflow") == lens["workflow"]\n', ("tests.test_decide.Content",)),
    ("a workflow file is matched in any case", "kernel/derive.py",
     '    return "workflow" in check and check["workflow"] == lens["workflow"]\n',
     '    return "workflow" in check and str(check["workflow"]).casefold() == str(lens["workflow"]).casefold()\n',
     ("tests.test_decide.Content",)),
    ("a workflow file is matched by its name alone", "kernel/derive.py",
     '    return "workflow" in check and check["workflow"] == lens["workflow"]\n',
     '    return "workflow" in check and str(check["workflow"]).rsplit("/", 1)[-1] == str(lens["workflow"]).rsplit("/",'
     ' 1)[-1]\n', ("tests.test_decide.Content",)),
    ("a check is matched to a Lens by the Lens's own name", "kernel/derive.py",
     '    return check.get("name") == lens["check"]\n',
     '    return check.get("name") in (lens["check"], lens["lens"])\n', ("tests.test_decide.Content",)),
    ("a check's name is matched in any case and with space around it", "kernel/derive.py",
     '    return check.get("name") == lens["check"]\n',
     '    return str(check.get("name")).strip().casefold() == lens["check"].casefold()\n',
     ("tests.test_decide.Content",)),
    ("a check from another App is passed over", "kernel/derive.py",
     "    if foreign:\n", "    if False:\n", ("tests.test_decide.Content",)),
    ("another App's check is read after the failures of every Lens", "kernel/derive.py",
     *moved_after("kernel/derive.py",
                  '    foreign = foreign_checks(facts["checks"], config)\n    if foreign:\n'
                  '        return {"state": t.VERIFYING, "reason": "check_unreadable", "evidence": foreign}\n',
                  '        return {"state": t.ADDRESSING, "reason": "check_failed", "evidence": failed}\n'),
     ("tests.test_decide.Content",)),
    ("another App's check is read after a conflict", "kernel/derive.py",
     *moved_after("kernel/derive.py",
                  '    foreign = foreign_checks(facts["checks"], config)\n    if foreign:\n'
                  '        return {"state": t.VERIFYING, "reason": "check_unreadable", "evidence": foreign}\n',
                  '        return {"state": t.ADDRESSING, "reason": "conflict", "evidence": []}\n'),
     ("tests.test_decide.Content",)),
    ("another App's check is shown as its Lens alone", "kernel/derive.py",
     '                said = "%s:from_app:%s" % (lens["lens"], app if type(app) is int else "unreadable")\n',
     '                said = lens["lens"]\n', ("tests.test_decide.Content",)),
    ("an App id that is no whole number is shown as it is", "kernel/derive.py",
     'app if type(app) is int else "unreadable")', "app)", ("tests.test_decide.Content",)),
    ("another workflow file's check is shown as another App's", "kernel/derive.py",
     '                said = "%s:from_workflow:%s" % (lens["lens"], shown_path(c.get("workflow"), config))\n',
     '                said = "%s:from_app:%s" % (lens["lens"], c.get("app_id"))\n', ("tests.test_decide.Content",)),
    ("a workflow path is shown whatever its form", "kernel/derive.py",
     'shown_path(c.get("workflow"), config))', 'c.get("workflow"))', ("tests.test_decide.Content",)),
    ("a workflow path of any length is shown", "kernel/derive.py",
     '\n            and len(path) <= config["limits"]["max_path_length"]):', "):", ("tests.test_decide.Content",)),
    ("a workflow path of any characters is shown", "kernel/derive.py",
     "all(c in t.FILE_NAME_CHARS for c in stem)", "True", ("tests.test_decide.Content",)),
    ("a workflow path in any directory is shown", "kernel/derive.py",
     "path.startswith(t.WORKFLOW_DIR)", "True", ("tests.test_decide.Content",)),
    ("a workflow path with no file name is shown", "kernel/derive.py",
     'stem != "" and ', "", ("tests.test_decide.Content",)),
    ("a workflow path with any ending is shown", "kernel/derive.py",
     "name.endswith(ending) and ", "", ("tests.test_decide.Content",)),
    ("a check from another App and another file is shown as another file's", "kernel/derive.py",
     "            if not from_its_app(c, lens):\n", "            if from_its_workflow(c, lens):\n",
     ("tests.test_decide.Content",)),
    ("the last check with a Lens's name wins", "kernel/derive.py",
     "                else check_reading(c, config) for c, r in kept}\n",
     "                else check_reading(c, config) for c, r in kept[-1:]}\n", ("tests.test_decide.Content",)),
    ("the first check with a Lens's name wins", "kernel/derive.py",
     "                else check_reading(c, config) for c, r in kept}\n",
     "                else check_reading(c, config) for c, r in kept[:1]}\n", ("tests.test_decide.Content",)),
    ("a failing check among passing ones is ignored", "kernel/derive.py",
     '    if "failing" in readings:\n', '    if readings == {"failing"}:\n', ("tests.test_decide.Content",)),
    ("a check with no verdict among passing ones is ignored", "kernel/derive.py",
     '    if readings - {"passing", "pending", "concluding"}:\n', '    if not readings & {"passing", "pending", "concluding"}:\n',
     ("tests.test_decide.Content",)),
    ("a running check among passing ones passes", "kernel/derive.py",
     '    if "pending" in readings:\n', '    if readings == {"pending"}:\n', ("tests.test_decide.Content",)),
    ("a check with no verdict is read before a failing one of the same Lens", "kernel/derive.py",
     '    if "failing" in readings:\n',
     '    if "failing" in readings and not readings - {"passing", "pending", "failing"}:\n',
     ("tests.test_decide.Content",)),
    # Issue 808: no Role is named to open pull requests until open_pull_request has its writer.
    ("a check with no verdict is ignored", "kernel/derive.py",
     "    if unreadable:\n", "    if False:\n", ("tests.test_decide.Classes",)),
    ("a check with no verdict is read before a failed one", "kernel/derive.py",
     "    if failed:\n"
     '        return {"state": t.ADDRESSING, "reason": "check_failed", "evidence": failed}\n',
     "    if unreadable:\n"
     '        return {"state": t.VERIFYING, "reason": "check_unreadable", "evidence": unreadable}\n'
     "    if failed:\n"
     '        return {"state": t.ADDRESSING, "reason": "check_failed", "evidence": failed}\n',
     ("tests.test_decide.Content",)),
    ("a dependency bot's pull request someone else pushed to skips the model review", "kernel/derive.py",
     ' and facts["last_pusher"] == facts["author"]\n', "\n", ("tests.test_decide.Classes",)),
    ("a class the configuration does not name skips the model review", "kernel/derive.py",
     'facts["class"] in lenses["model_not_required_for"]', "True", ("tests.test_decide.Readability",)),
    ("a dependency update converges before its checks are read", "kernel/derive.py",
     "    # Deterministic Lenses first: a model's time is not spent on content they reject.\n",
     "    if not required_model_lenses(facts, config):\n"
     '        return {"state": t.CONVERGED, "reason": "approval_due", "evidence": []}\n',
     ("tests.test_decide.HumanControl",)),
    ("a dependency update converges before its threads are read", "kernel/derive.py",
     "    open_gates = gates(facts, config)\n",
     "    open_gates = gates(facts, config) if required_model_lenses(facts, config) else []\n",
     ("tests.test_decide.HumanControl",)),
    ("a writer's request for changes does not gate", "kernel/gate.py",
     "    return threads + standing_requests(facts)\n", "    return threads\n", ("tests.test_decide.HumanControl",)),
    ("a stranger's request for changes gates", "kernel/gate.py",
     'if is_person(rv["by"]) and', 'if rv["by"]["kind"] == "human" and', ("tests.test_decide.HumanControl",)),
    ("a Lens's request for changes gates", "kernel/gate.py",
     'if is_person(rv["by"]) and', 'if rv["by"]["can_write"] and', ("tests.test_decide.HumanControl",)),
    ("new content clears a request for changes", "kernel/gate.py",
     'for rv in sorted(facts["reviews"], key=verdict_order):',
     'for rv in sorted([rv for rv in facts["reviews"] if rv["content_id"] == facts["content_id"]],'
     ' key=verdict_order):', ("tests.test_decide.HumanControl",)),
    ("a review that only comments clears a request for changes", "kernel/gate.py",
     ' and rv["state"] != "commented":', ":", ("tests.test_decide.HumanControl",)),
    ("another writer's approval clears a request for changes", "kernel/gate.py",
     '            latest[rv["by"]["name"]] = rv\n', '            latest["anyone"] = rv\n',
     ("tests.test_decide.HumanControl",)),
    ("an earlier review is read as the latest", "kernel/gate.py",
     'sorted(facts["reviews"], key=verdict_order)', 'facts["reviews"]', ("tests.test_decide.HumanControl",)),
    ("a tie between a request and an approval resolves to the approval", "kernel/gate.py",
     '"changes_requested" in (rv["state"], rv.get("dismissed_from"))',
     '"changes_requested" not in (rv["state"], rv.get("dismissed_from"))', ("tests.test_decide.HumanControl",)),
    ("an App's dismissal clears a request for changes", "kernel/gate.py",
     '            if is_person(rv["dismissed_by"]):\n', '            if rv["dismissed_by"]["can_write"]:\n',
     ("tests.test_decide.HumanControl",)),
    ("a stranger's dismissal clears a request for changes", "kernel/gate.py",
     '            if is_person(rv["dismissed_by"]):\n', '            if rv["dismissed_by"]["kind"] == "human":\n',
     ("tests.test_decide.HumanControl",)),
    ("a standing approval is read before a request for changes", "kernel/derive.py",
     "    open_gates = gates(facts, config)\n",
     "    approval = standing_approval(facts, config)\n"
     "    if approval is not None:\n"
     '        return {"state": t.CONVERGED, "reason": "approved", "evidence": [approval["commit"]]}\n'
     "    open_gates = gates(facts, config)\n", ("tests.test_decide.HumanControl",)),
    ("an unreadable review is trusted", "kernel/derive.py",
     "    if unreadable_reviews(facts, config):\n", "    if False:\n", ("tests.test_decide.HumanControl",)),
    ("an unreadable review is read after the model review's wait", "kernel/derive.py",
     *moved_after("kernel/derive.py", REVIEW_GUARD, REVIEW_WAIT), ("tests.test_decide.HumanControl",)),
    ("a queued pull request whose approval is lost stays in the queue", "kernel/derive.py",
     STAYS, '    if d["reason"] in ("approved", "approval_due"):\n', ("tests.test_decide.OnlyAPersonEnds",)),
    ("a queued pull request with a gate open stays in the queue", "kernel/derive.py",
     STAYS, '    if d["reason"] == "approved" or d["reason"] in t.GATE_REASONS:\n',
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("a Hold leaves a queued pull request in the queue", "kernel/derive.py",
     STAYS, '    if d["reason"] == "approved" or d["state"] == t.HELD:\n', ("tests.test_decide.OnlyAPersonEnds",)),
    ("a read that fails leaves a pull request in the queue", "kernel/derive.py",
     STAYS, '    if d["reason"] == "approved" or d["state"] is None:\n', ("tests.test_decide.OnlyAPersonEnds",)),
    ("a check that no longer passes leaves a pull request in the queue", "kernel/derive.py",
     STAYS, '    if d["reason"] in ("approved", "check_failed", "check_unreadable", "conflict"):\n',
     ("tests.test_decide.Queue",)),
    ("an approved head that conflicts is not sent back to its author", "kernel/derive.py",
     "    if mergeable is False:\n",
     '    if mergeable is False and (facts["queue"] or standing_approval(facts, config) is None):\n',
     ("tests.test_decide.Queue.test_a_conflict_read_a_pass_late_is_the_authors_turn_at_the_next_pass_and_leaves_the_queue",)),
    ("a queued pull request that conflicts stays in the queue", "kernel/derive.py",
     STAYS, '    if d["reason"] in ("approved", "conflict"):\n',
     ("tests.test_decide.Queue.test_a_conflict_read_a_pass_late_is_the_authors_turn_at_the_next_pass_and_leaves_the_queue",)),
    ("a merge state not worked out yet takes a queued pull request out", "kernel/derive.py",
     ' and "mergeable_unreadable" not in past', "", ("tests.test_decide.Queue",)),
    ("a required check not reported yet takes a queued pull request out", "kernel/derive.py",
     ' and "awaiting_checks" not in past', "", ("tests.test_decide.Queue",)),
    ("a required Lens that has not reported takes a queued pull request out", "kernel/derive.py",
     ' and ("awaiting_review" not in past or rules):', ":", ("tests.test_decide.Queue",)),
    ("a wait is read past on a pull request that is not queued", "kernel/derive.py",
     "    d = reading(facts, runs, config, ())\n", "    d = reading(facts, runs, config, t.QUEUE_WAITS)\n",
     ("tests.test_decide.Readability",)),
    ("a draft stays in the merge queue", "kernel/derive.py",
     STAYS, '    if d["reason"] == "approved" or d["state"] == t.DRAFT:\n', ("tests.test_decide.Queue",)),
    ("hands-off takes a pull request out of the queue", "kernel/derive.py",
     LEFT_ALONE, LEFT_ALONE.replace(" or hands_off(facts, config)", ""), ("tests.test_decide.OnlyAPersonEnds",)),
    ("hands-off anyone placed leaves a queued pull request in the queue", "kernel/derive.py",
     LEFT_ALONE, LEFT_ALONE.replace("hands_off(facts, config)", 't.LABEL_HANDS_OFF in [ev.get("label") for ev in'
                                    ' facts["label_events"] if isinstance(ev, dict)]'),
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("a pull request that is not queued is dequeued", "kernel/derive.py",
     LEFT_ALONE, LEFT_ALONE.replace(' or not facts["queue"]', ""), ("tests.test_decide.Readability",)),
    ("a pull request that is not served is dequeued", "kernel/derive.py",
     LEFT_ALONE, LEFT_ALONE.replace("d[\"state\"] in t.ADMITS_NOTHING", "d[\"state\"] in (t.MERGED, t.CLOSED)"),
     ("tests.test_decide.Queue",)),
    ("a pull request that is not served is someone's to see", "kernel/decide.py",
     '    if state in t.ADMITS_NOTHING or state == t.DRAFT or reason == "hands_off":\n',
     '    if state in (t.MERGED, t.CLOSED) or state == t.DRAFT or reason == "hands_off":\n',
     ("tests.test_decide.Classes",)),
    ("a Run in progress on a pull request that is not served is shown as working", "kernel/decide.py",
     "    if state in t.ADMITS_NOTHING or state in (t.DRAFT, t.QUEUED):\n",
     "    if state in (t.MERGED, t.CLOSED) or state in (t.DRAFT, t.QUEUED):\n", ("tests.test_decide.Classes",)),
    ("a State the Lifecycle does not know is given", "kernel/derive.py",
     '        return {"state": t.DRAFT, "reason": "draft", "evidence": []}\n',
     '        return {"state": t.DRAFT, "reason": "draft", "evidence": []}\n'
     '    if facts.get("frozen"):\n        return {"state": "frozen", "reason": "too_large", "evidence": []}\n',
     ("tests.test_transitions.Transitions.test_every_state_and_reason_the_kernel_gives_has_facts",)),
    ("a reason that is not written out", "kernel/derive.py",
     '        return {"state": t.DRAFT, "reason": "draft", "evidence": []}\n',
     '        why = "draft"\n        return {"state": t.DRAFT, "reason": why, "evidence": []}\n',
     ("tests.test_transitions.Transitions.test_every_state_and_reason_the_kernel_gives_has_facts",)),
    ("a reason beside derive's State that no facts give", "kernel/decide.py",
     "    if state == t.HELD:\n        return _decision(facts, state, reason, evidence, t.HOLD)\n",
     '    if facts.get("frozen"):\n        return _decision(facts, state, "untested_reason", evidence, t.HOLD)\n'
     "    if state == t.HELD:\n        return _decision(facts, state, reason, evidence, t.HOLD)\n",
     ("tests.test_transitions.Transitions.test_every_state_and_reason_the_kernel_gives_has_facts",)),
    ("a person's Finding is read as a Lens's", "kernel/derive.py",
     '            if any(g["by"]["kind"] == "human" for g in open_gates if g["id"] in for_author):\n',
     "            if False:\n", ("tests.test_decide.HumanControl",)),
    ("the States that admit nothing are only the ends", "kernel/terms.py",
     "ADMITS_NOTHING = frozenset({MERGED, CLOSED, NOT_SERVED})", "ADMITS_NOTHING = frozenset({MERGED, CLOSED})",
     ("tests.test_decide.Classes",)),
    ("a pause lets a dequeue through", "kernel/decide.py",
     "        if pause:\n", "        if False:\n", ("tests.test_decide.Queue",)),
    ("a deferred dequeue is not the Maintainer's to see", "kernel/decide.py",
     ", attention=t.NEEDS_YOU)", ")", ("tests.test_decide.Queue",)),
    ("a dequeue is held to the act ceiling", "kernel/decide.py",
     DEQUEUE,
     '        if facts.get("acts_since_writer") is None or facts["acts_since_writer"] >= config["limits"]["max_acts_per_item"]:\n'
     '            return _decision(facts, t.HELD, "act_ceiling", [], t.HOLD)\n' + DEQUEUE,
     ("tests.test_decide.Queue",)),
    ("a Run in progress keeps a pull request in the queue", "kernel/decide.py",
     DEQUEUE_IF,
     "    if in_progress(runs_on(runs, facts)):\n"
     "        return _decision(facts, state, reason, evidence, t.NOTHING, working=True)\n" + DEQUEUE_IF,
     ("tests.test_decide.Classes",)),
    ("a draft or a queued item is left alone before the dequeue is read", "kernel/decide.py",
     DEQUEUE_IF,
     "    if state in t.ADMITS_NOTHING or state in (t.DRAFT, t.QUEUED):\n"
     "        return _decision(facts, state, reason, evidence, t.NOTHING)\n" + DEQUEUE_IF,
     ("tests.test_decide.Queue",)),
    ("a read that fails defers before the dequeue is read", "kernel/decide.py",
     DEQUEUE_IF,
     "    if state is None:\n"
     "        return _decision(facts, None, reason, evidence, t.DEFER)\n" + DEQUEUE_IF,
     ("tests.test_decide.OnlyAPersonEnds",)),
    ("an unreadable review is read before what needs no review", "kernel/derive.py",
     '    if facts["state"] == "merged":\n', REVIEW_GUARD + '    if facts["state"] == "merged":\n',
     ("tests.test_decide.HumanControl",)),
    ("an unreadable dismissal is trusted", "kernel/derive.py",
     '        if rv["state"] == "dismissed" and not readable_actor(rv.get("dismissed_by"), facts, config):\n',
     "        if False:\n", ("tests.test_decide.HumanControl",)),
    ("a dismissed approval is read as a request for changes", "kernel/gate.py",
     '            if rv["dismissed_from"] != "changes_requested":\n                continue\n', "",
     ("tests.test_decide.HumanControl",)),
    ("a dismissed approval does not end an earlier request", "kernel/gate.py",
     'if rv["state"] == "dismissed" and rv["dismissed_from"] == "commented":',
     'if rv["state"] == "dismissed" and rv["dismissed_from"] != "changes_requested":',
     ("tests.test_decide.HumanControl",)),
    ("a dismissed comment ends an earlier request", "kernel/gate.py",
     '        if rv["state"] == "dismissed" and rv["dismissed_from"] == "commented":\n            continue\n', "",
     ("tests.test_decide.HumanControl",)),
    ("a review not dismissed that carries dismissal fields is trusted", "kernel/derive.py",
     '        if rv["state"] != "dismissed" and (rv.get("dismissed_by") is not None'
     ' or rv.get("dismissed_from") is not None):\n',
     "        if False:\n", ("tests.test_decide.HumanControl",)),
    ("an unreadable dismissed_from is trusted", "kernel/derive.py",
     '        if rv["state"] == "dismissed" and rv.get("dismissed_from") not in t.DISMISSED_FROM:\n',
     "        if False:\n", ("tests.test_decide.HumanControl",)),
    ("write access that is not exactly true or false is read", "kernel/derive.py",
     'and type(actor.get("can_write")) is bool', 'and "can_write" in actor', ("tests.test_decide.HumanControl",)),
    ("a kind the Kernel does not know is read", "kernel/derive.py",
     'actor.get("kind") in t.ACTOR_KINDS', '"kind" in actor', ("tests.test_decide.HumanControl",)),
    ("an empty name is read", "kernel/derive.py",
     ' and actor["name"] != ""', "", ("tests.test_decide.HumanControl",)),
    ("a review state the Kernel does not know is read", "kernel/derive.py",
     'rv.get("state") not in t.REVIEW_STATES', '"state" not in rv', ("tests.test_decide.HumanControl",)),
    ("a review with no time is read", "kernel/derive.py",
     '        if not is_time(rv.get("submitted_at")):\n            return True\n', "",
     ("tests.test_decide.HumanControl",)),
    ("a review's time in another format is read", "kernel/derive.py",
     'if not is_time(rv.get("submitted_at")):', 'if not isinstance(rv.get("submitted_at"), str):',
     ("tests.test_decide.HumanControl",)),
    ("an unreadable review is not the Maintainer's to see", "kernel/decide.py",
     '"check_unreadable", "review_unreadable",', '"check_unreadable",', ("tests.test_decide.HumanControl",)),
    ("an item with no State is never the Maintainer's to see", "kernel/decide.py",
     "    if state is None and reason not in NEEDS_YOU_REASONS:\n", "    if state is None:\n",
     ("tests.test_decide.HumanControl",)),
    ("a check with no verdict does not defer", "kernel/decide.py",
     '    if reason == "check_unreadable":\n', "    if False:\n", ("tests.test_decide.Content",)),
    ("two Runs on one item", "kernel/decide.py",
     "    if in_progress(mine):\n", "    if False:\n", ("tests.test_decide.Classes",)),
    ("the approver may be the author", "kernel/derive.py",
     'if config["approver"] in (facts["author"], facts["last_pusher"]):', "if False:",
     ("tests.test_decide.HumanControl",)),
    # Issue 163: the last pusher is read from the head branch's activity, and one nobody can name lets nothing through.
    ("an unreadable last pusher is read", "kernel/derive.py",
     '    if not isinstance(facts.get("last_pusher"), str) or facts["last_pusher"] == "":\n', "    if False:\n",
     PUSHER_TESTS),
    ("an empty last pusher is read", "kernel/derive.py",
     ' or facts["last_pusher"] == "":\n', ":\n", PUSHER_TESTS),
    ("an unreadable last pusher calls nobody", "kernel/decide.py",
     '    "last_pusher_unreadable",\n', "", PUSHER_TESTS),
    ("a pause admits a Run", "kernel/brakes.py",
     "    pause = paused(_decision, facts, state, evidence, context)\n    if pause:\n",
     "    pause = paused(_decision, facts, state, evidence, context)\n    if False:\n",
     ("tests.test_decide.Readability",)),
    ("a pause lets an approval or a merge through", "kernel/brakes.py",
     "    stopped = paused(_decision, facts, state, evidence, context)\n    if stopped:\n",
     "    stopped = paused(_decision, facts, state, evidence, context)\n    if False:\n",
     ("tests.test_decide.Readability",)),
    ("a pause hides the approver Hold", "kernel/decide.py",
     "    if state == t.HELD:\n        return _decision(facts, state, reason, evidence, t.HOLD)\n",
     '    if state == t.HELD and reason == "approver_is_author_or_last_pusher" and brakes.paused(_decision, facts,'
     ' state, evidence, context):\n'
     "        return brakes.paused(_decision, facts, state, evidence, context)\n"
     "    if state == t.HELD:\n        return _decision(facts, state, reason, evidence, t.HOLD)\n",
     ("tests.test_decide.HumanControl",)),
    ("the approver is read before the gates", "kernel/derive.py",
     "    # Every gate before the approval: a standing approval never passes over a person's objection.\n",
     '    if config["approver"] in (facts["author"], facts["last_pusher"]):\n'
     '        return {"state": t.HELD, "reason": "approver_is_author_or_last_pusher", "evidence": []}\n'
     "    # Every gate before the approval: a standing approval never passes over a person's objection.\n",
     ("tests.test_decide.Acceptance",)),
    # Convergence's fourth condition: the acceptance contract (I-31).
    ("a criterion with no passing evidence converges", "kernel/derive.py",
     '    if said == "missing":\n', "    if False:\n", ("tests.test_decide.Acceptance",)),
    ("evidence for other content counts", "kernel/derive.py",
     '\n                             and ev["content_id"] == facts["content_id"]}', "}",
     ("tests.test_decide.Acceptance",)),
    ("a failing criterion converges", "kernel/derive.py",
     '    if said == "failing":\n', "    if False:\n", ("tests.test_decide.Acceptance",)),
    ("a failing criterion is read as a wait for its evidence", "kernel/derive.py",
     '    if fails:\n        return "failing", fails\n', "", ("tests.test_decide.Acceptance",)),
    ("a failure beside a pass on the same content is passed over", "kernel/derive.py",
     'if "failing" in said[c]]', 'if said[c] == {"failing"}]', ("tests.test_decide.Acceptance",)),
    ("a criterion still waiting is read before a failing one", "kernel/derive.py",
     '    if fails:\n        return "failing", fails\n',
     '    if fails and len(fails) == len(ids):\n        return "failing", fails\n', ("tests.test_decide.Acceptance",)),
    ("a failed criterion admits no fix Run", "kernel/decide.py",
     ',\n                                              "acceptance_failed")', ")", ("tests.test_decide.Acceptance",)),
    ("unreadable acceptance is trusted", "kernel/derive.py",
     "    if not readable_contract(contract, facts, config):\n", "    if False:\n", ("tests.test_decide.Acceptance",)),
    ("facts with no acceptance are read as no contract", "kernel/derive.py",
     '    if "acceptance" not in facts:\n        return unreadable\n',
     '    if "acceptance" not in facts:\n        return None\n', ("tests.test_decide.Acceptance",)),
    # Issue 173: a now, a Lifecycle, a limit or a context that cannot be read never raises out of a pull request's decide.
    ("a now that is no moment raises on a pull request", "kernel/derive.py",
     "    if not is_time(now):\n        return None\n", "", (STALE + "test_a_now_that_is_no_moment_shows_a_wait_as_stale_and_raises_nothing",)),
    # The deferral of a Run, read once for either kind of Work item (derive.run_deferral): the model provider's
    # deadline (issues 165 and 173), the org's count of active Runs (issue 218) and a Run listed unnamed (decision 0036).
    ("a capacity deadline that cannot be compared is trusted", "kernel/derive.py",
     "    if until is not None and not (is_time(until) and is_time(now)):\n", "    if False:\n",
     (STALE + "test_a_now_that_is_no_moment_shows_a_wait_as_stale_and_raises_nothing",) + ISSUE_TESTS),
    ("a capacity deadline that is no moment is compared", "kernel/derive.py",
     "not (is_time(until) and is_time(now))", "not is_time(now)",
     (STALE + "test_a_now_that_is_no_moment_shows_a_wait_as_stale_and_raises_nothing",) + ISSUE_TESTS),
    ("a capacity deadline is compared with a now that is no moment", "kernel/derive.py",
     "not (is_time(until) and is_time(now))", "not is_time(until)",
     (STALE + "test_a_now_that_is_no_moment_shows_a_wait_as_stale_and_raises_nothing",) + ISSUE_TESTS),
    ("a capacity fault does not defer", "kernel/derive.py",
     "    if until is not None and until > now:\n", "    if False:\n", ("tests.test_decide.Ceilings",) + ISSUE_TESTS),
    ("a deferral that ends now still defers", "kernel/derive.py",
     "until is not None and until > now", "until is not None and until >= now",
     (STALE + "test_a_now_that_is_no_moment_shows_a_wait_as_stale_and_raises_nothing",) + ISSUE_TESTS),
    ("an unreadable count of active Runs is trusted", "kernel/derive.py",
     COUNT_GUARD, "    if False:\n", ("tests.test_decide.Readability",) + ISSUE_TESTS),
    ("a count of active Runs that is no number is compared", "kernel/derive.py",
     COUNT_GUARD, "    if active is None:\n", COUNT_TESTS + ISSUE_COUNT_TESTS),
    ("a bool is read as a count of active Runs", "kernel/derive.py",
     COUNT_GUARD, "    if not isinstance(active, int) or active < 0:\n", COUNT_TESTS + ISSUE_COUNT_TESTS),
    ("a negative count of active Runs is read", "kernel/derive.py",
     COUNT_GUARD, "    if type(active) is not int:\n", COUNT_TESTS + ISSUE_COUNT_TESTS),
    ("the org limit is ignored", "kernel/derive.py",
     '    if active >= limits["org_max_active_runs"]:\n', "    if False:\n", ("tests.test_decide.Ceilings",) + ISSUE_TESTS),
    ("the org's concurrency defers only past its limit", "kernel/derive.py",
     'active >= limits["org_max_active_runs"]', 'active > limits["org_max_active_runs"]',
     ("tests.test_decide.Ceilings",) + ISSUE_TESTS),
    ("an unidentified Run admits a Run", "kernel/derive.py",
     '    if unnamed_within(context, now, limits) != []:\n', "    if False:\n",
     (UNIDENTIFIED + "test_an_unidentified_run_defers_a_run_on_a_pull_request",
      "tests.test_issue.UnidentifiedRuns.test_an_unidentified_run_defers_an_issues_run")),
    ("an unreadable list of unidentified Runs is read as empty", "kernel/derive.py",
     '    if unnamed_within(context, now, limits) != []:\n', '    if unnamed_within(context, now, limits):\n',
     (UNIDENTIFIED + "test_a_list_of_unidentified_runs_that_cannot_be_read_defers",
      "tests.test_issue.UnidentifiedRuns.test_an_unidentified_run_defers_an_issues_run")),
    ("a Lifecycle not the pull request's is read", "kernel/derive.py",
     '    if not (isinstance(lifecycle, dict) and lifecycle.get("work_item") == work_item):\n', "    if False:\n",
     (STALE + "test_a_lifecycle_whose_limit_cannot_be_read_shows_the_wait_as_stale",)),
    ("a pull request's limit that cannot be read is trusted", "kernel/derive.py",
     "    if not (type(cap) in (int, float) and abs(cap) < float(\"inf\")):\n", "    if False:\n",
     (STALE + "test_a_lifecycle_whose_limit_cannot_be_read_shows_the_wait_as_stale",)),
    ("a bool is read as a pull request's limit", "kernel/derive.py",
     "type(cap) in (int, float)", "isinstance(cap, (int, float))",
     (STALE + "test_a_lifecycle_whose_limit_cannot_be_read_shows_the_wait_as_stale",)),
    ("a pull request's end goes stale", "kernel/derive.py",
     "    if isinstance(ends, list) and state in ends:\n        return False\n", "",
     (STALE + "test_an_end_never_goes_stale",)),
    ("a pull request's Lifecycle is read from the configuration by force", "kernel/decide.py",
     'overdue(config.get("lifecycle"), WORK_ITEM', 'overdue(config["lifecycle"], WORK_ITEM',
     (STALE + "test_a_lifecycle_whose_limit_cannot_be_read_shows_the_wait_as_stale",)),
    ("a context that cannot be read raises on a pull request", "kernel/decide.py",
     "    known = context if isinstance(context, dict) else {}\n", "    known = context\n",
     (STALE + "test_a_context_that_cannot_be_read_says_nothing_of_the_passes",)),
    # Issue 183: a Result is scored against a held-out case.
    ("an acceptance contract read short is trusted", "kernel/derive.py",
     "[name for name in t.READ_IN_FULL if flags.get(name) is not True]",
     '[name for name in t.READ_IN_FULL if name != "acceptance" and flags.get(name) is not True]',
     ("tests.test_decide.Readability",)),
    ("an empty criterion id, or one in another form, is read", "kernel/derive.py",
     "all(in_form(i, t.CRITERION_PREFIX, t.DIGITS) for i in ids)", "all(isinstance(i, str) for i in ids)",
     ("tests.test_decide.Acceptance",)),
    ("a criterion id that is no string is read", "kernel/derive.py",
     "all(in_form(i, t.CRITERION_PREFIX, t.DIGITS) for i in ids)", 'all(i != "" for i in ids)',
     ("tests.test_decide.Acceptance",)),
    ("a name in another prefix is in form", "kernel/derive.py",
     "isinstance(value, str) and value.startswith(prefix) and len(value)", "isinstance(value, str) and len(value)",
     ("tests.test_decide.Acceptance",)),
    ("a prefix with nothing after it is in form", "kernel/derive.py",
     " and len(value) > len(prefix)\n", "\n", ("tests.test_decide.Acceptance",)),
    ("a name in other digits is in form", "kernel/derive.py",
     "\n            and all(c in digits for c in value[len(prefix):]))", ")", ("tests.test_decide.Acceptance",)),
    ("a result that is no object is read", "kernel/derive.py",
     "        if not isinstance(ev, dict):\n            return False\n", "", ("tests.test_decide.Acceptance",)),
    ("a result's content id in another form is read as earlier content", "kernel/derive.py",
     '        if not in_form(ev.get("content_id"), t.CONTENT_PREFIX, t.HEX_DIGITS):\n',
     '        if not isinstance(ev.get("content_id"), str):\n', ("tests.test_decide.Acceptance",)),
    ("a result's criterion id in another form is read", "kernel/derive.py",
     '        if not in_form(ev.get("criterion"), t.CRITERION_PREFIX, t.DIGITS):\n', "        if False:\n",
     ("tests.test_decide.Acceptance",)),
    ("a result on earlier content is judged too", "kernel/derive.py",
     '        if ev["content_id"] != content:\n            continue\n', "", ("tests.test_decide.Acceptance",)),
    # Issue 445, decision 0149: a result's check is read as any check is, so one a job created is foreign to its reporter.
    ("a result whose check has no file is its reporter's", "kernel/derive.py",
     '        elif reports_for(ev["check"], lens):\n',
     '        elif reports_for(ev["check"], lens) or (ev["check"].get("workflow") is None and from_its_app(check, lens)):\n',
     RESULT_PORT + ("tests.test_decide.Acceptance.test_a_result_counts_only_from_the_reporter_its_kind_names",)),
    ("only the first criterion that failed is named", "kernel/derive.py",
     '        return "failing", fails\n', '        return "failing", fails[:1]\n', ("tests.test_decide.Acceptance",)),
    ("a contract with no criteria converges", "kernel/derive.py",
     "isinstance(criteria, list) and criteria and all(", "isinstance(criteria, list) and all(",
     ("tests.test_decide.Acceptance",)),
    ("a criterion named twice is read", "kernel/derive.py",
     " for i in ids) or len(set(ids)) != len(ids):\n", " for i in ids):\n", ("tests.test_decide.Acceptance",)),
    ("a result on this content for a criterion the contract does not name is passed over", "kernel/derive.py",
     'if ev["criterion"] not in ids or ev.get("result")', 'if ev.get("result")', ("tests.test_decide.Acceptance",)),
    ("a result on this content in a word the Kernel does not know is passed over", "kernel/derive.py",
     ' or ev.get("result") not in t.EVIDENCE_RESULTS:\n', ":\n", ("tests.test_decide.Acceptance",)),
    ("unreadable acceptance is not the Maintainer's to see", "kernel/decide.py",
     '    "acceptance_unreadable", "acceptance_bounded",', '    "acceptance_bounded",', ("tests.test_decide.Acceptance",)),
    ("a queued item waiting for its evidence stays in the queue", "kernel/derive.py",
     '    if said == "missing":\n', '    if said == "missing" and "awaiting_review" not in past:\n',
     ("tests.test_decide.Queue",)),
    ("acceptance is read before the gates", "kernel/derive.py",
     "    # Every gate before the approval: a standing approval never passes over a person's objection.\n",
     "    said, criteria = acceptance_reading(facts)\n"
     '    if said == "missing":\n'
     '        return {"state": t.VERIFYING, "reason": "acceptance_evidence_missing", "evidence": criteria}\n'
     "    # Every gate before the approval: a standing approval never passes over a person's objection.\n",
     ("tests.test_decide.Acceptance",)),
    ("acceptance is read before the checks", "kernel/derive.py",
     "    # Deterministic Lenses first: a model's time is not spent on content they reject.\n",
     "    said, criteria = acceptance_reading(facts)\n"
     '    if said == "failing":\n'
     '        return {"state": t.ADDRESSING, "reason": "acceptance_failed", "evidence": criteria}\n'
     "    # Deterministic Lenses first: a model's time is not spent on content they reject.\n",
     ("tests.test_decide.Acceptance",)),
    ("acceptance is read after the approver Hold", "kernel/derive.py",
     "    # Then the acceptance contract's evidence, where the item has one:",
     '    if config["approver"] in (facts["author"], facts["last_pusher"]):\n'
     '        return {"state": t.HELD, "reason": "approver_is_author_or_last_pusher", "evidence": []}\n'
     "    # Then the acceptance contract's evidence, where the item has one:", ("tests.test_decide.Acceptance",)),
    # The contract a person approved, and the reporter its kind names (issue 108, decision 0025).
    # A missing approval read as one that passes, and so converges: a wrong Decision, not None passed on to a crash.
    ("nobody's approval is read as an approval", "kernel/derive.py",
     '    if approved is None or not is_person(approved["by"]):\n',
     "    if approved is None:\n"
     '        return {"state": t.CONVERGED, "reason": "approval_due", "evidence": []}\n'
     '    if not is_person(approved["by"]):\n', ("tests.test_decide.Acceptance",)),
    ("an approval by anyone is read as a person's", "kernel/derive.py",
     ' or not is_person(approved["by"]):\n', ":\n", ("tests.test_decide.Acceptance",)),
    ("a contract changed since its approval is read as unchanged", "kernel/derive.py",
     '    if contract["head"] != approved["digest"]:\n', "    if False:\n", ("tests.test_decide.Acceptance",)),
    ("a deleted contract is read as unchanged", "kernel/derive.py",
     '    if contract["head"] != approved["digest"]:\n',
     '    if contract["head"] is not None and contract["head"] != approved["digest"]:\n',
     ("tests.test_decide.Acceptance",)),
    ("the contract is read after a conflict", "kernel/derive.py",
     *moved_after("kernel/derive.py", CONTRACT_GUARD,
                  '        return {"state": t.ADDRESSING, "reason": "conflict", "evidence": []}\n'),
     ("tests.test_decide.Acceptance",)),
    ("the contract is read after the checks", "kernel/derive.py",
     *moved_after("kernel/derive.py", CONTRACT_GUARD,
                  '        return {"state": t.ADDRESSING, "reason": "check_failed", "evidence": failed}\n'),
     ("tests.test_decide.Acceptance",)),
    ("a contract that says nothing of its approval or its head is read", "kernel/derive.py",
     'all(name in contract for name in ("approved", "head", "results"))', '"results" in contract',
     ("tests.test_decide.Acceptance",)),
    ("an approval's digest in another form is read", "kernel/derive.py",
     'is_digest(approved.get("digest"))', '"digest" in approved', ("tests.test_decide.Acceptance",)),
    ("an approver that cannot be read is read", "kernel/derive.py",
     'readable_actor(approved.get("by"), facts, config)', 'isinstance(approved.get("by"), dict)',
     ("tests.test_decide.Acceptance",)),
    ("a criterion's kind the Kernel does not know is read", "kernel/derive.py",
     'all(c.get("kind") in t.CRITERION_KINDS for c in criteria)', 'all("kind" in c for c in criteria)',
     ("tests.test_decide.Acceptance",)),
    ("a head in another form is read", "kernel/derive.py",
     "not (head is None or is_digest(head)) or ", "", ("tests.test_decide.Acceptance",)),
    ("a result on this content with no check is read", "kernel/derive.py",
     '        if not isinstance(ev.get("check"), dict):\n            return True\n', "",
     ("tests.test_decide.Acceptance",)),
    ("a result from another App counts", "kernel/derive.py",
     'reports_for(ev["check"], lens)', 'named_for(ev["check"], lens) and from_its_workflow(ev["check"], lens)',
     ("tests.test_decide.Acceptance",)),
    ("a result from another workflow file counts", "kernel/derive.py",
     'reports_for(ev["check"], lens)', 'named_for(ev["check"], lens) and from_its_app(ev["check"], lens)',
     ("tests.test_decide.Acceptance",)),
    ("a result from another check counts", "kernel/derive.py",
     'reports_for(ev["check"], lens)', 'from_its_app(ev["check"], lens) and from_its_workflow(ev["check"], lens)',
     ("tests.test_decide.Acceptance",)),
    ("a result from anyone but its reporter is passed over", "kernel/derive.py",
     "    if impostors:\n", "    if False:\n", ("tests.test_decide.Acceptance",)),
    ("a result's App id that is no whole number is shown as it is", "kernel/derive.py",
     'shown if type(shown) is int else "unreadable")', "shown)", ("tests.test_decide.Acceptance",)),
    ("a result's workflow path is shown whatever its form", "kernel/derive.py",
     'shown_path(check.get("workflow"), config))', 'check.get("workflow"))', ("tests.test_decide.Acceptance",)),
    ("any check passes a kind with no reporter", "kernel/derive.py",
     '            said = "%s:no_reporter" % ev["criterion"]\n', "            continue\n",
     ("tests.test_decide.Acceptance",)),
    ("a reporter no required Lens is named is read as the first", "kernel/derive.py",
     ' if lens["lens"] == name), None)', "), None)", ("tests.test_decide.Acceptance",)),
    ("a check may report a human criterion", "kernel/derive.py",
     "    if kind == t.HUMAN_KIND:\n        return None\n", "", ("tests.test_decide.Acceptance",)),
    ("a person's approval does not pass a human criterion", "kernel/derive.py",
     '        if c["kind"] == t.HUMAN_KIND:\n', "        if False:\n", ("tests.test_decide.Acceptance",)),
    ("anyone's approval passes a human criterion", "kernel/derive.py",
     'return any(is_person(rv["by"]) and rv["content_id"] == facts["content_id"]',
     'return any(rv["content_id"] == facts["content_id"]', ("tests.test_decide.Acceptance",)),
    ("an approval of other content passes a human criterion", "kernel/derive.py",
     'return any(is_person(rv["by"]) and rv["content_id"] == facts["content_id"]',
     'return any(is_person(rv["by"])', ("tests.test_decide.Acceptance",)),
    ("a person's dismissal leaves a human criterion passed", "kernel/derive.py",
     ' and not is_person(rv["dismissed_by"])))\n', "))\n", ("tests.test_decide.Acceptance",)),
    ("an App's dismissal ends a person's approval of a human criterion", "kernel/derive.py",
     '\n                    or (rv["dismissed_from"] == "approved" and not is_person(rv["dismissed_by"])))', ")",
     ("tests.test_decide.Acceptance",)),
    ("a contract no person approved is not the Maintainer's to see", "kernel/decide.py",
     '    "contract_not_approved", "contract_changed",', '    "contract_changed",', ("tests.test_decide.Acceptance",)),
    ("a contract changed since is not the Maintainer's to see", "kernel/decide.py",
     '    "contract_not_approved", "contract_changed", "acceptance_reporters_unreadable",\n',
     '    "contract_not_approved", "acceptance_reporters_unreadable",\n', ("tests.test_decide.Acceptance",)),
    # The fix round on issue 108: the approval is a review GitHub holds, every field of a review read is read whole,
    # the configuration's reporters are read, and a digest is a whole SHA-256.
    ("an approval of the contract with no review behind it is trusted", "kernel/derive.py",
     "    if not approval_stands(approved, facts):\n", "    if False:\n", ("tests.test_decide.Acceptance",)),
    ("a review on another commit holds the contract's approval", "kernel/derive.py",
     ' and rv["commit"] == approved["commit"] and (', " and (", ("tests.test_decide.Acceptance",)),
    ("another person's review holds the contract's approval", "kernel/derive.py",
     ' and rv["by"]["name"] == approved["by"]["name"]\n', "\n", ("tests.test_decide.Acceptance",)),
    ("anyone's review holds the contract's approval", "kernel/derive.py",
     '        theirs = is_person(rv["by"]) and ', "        theirs = ", ("tests.test_decide.Acceptance",)),
    ("a person's dismissal leaves the contract approved", "kernel/derive.py",
     ' and not is_person(rv["dismissed_by"]))):\n', ")):\n", ("tests.test_decide.Acceptance",)),
    ("an App's dismissal ends the contract's approval", "kernel/derive.py",
     ' or (rv["dismissed_from"] == "approved" and not is_person(rv["dismissed_by"]))):\n', "):\n",
     ("tests.test_decide.Acceptance",)),
    ("an approval on no commit is read", "kernel/derive.py",
     '            and isinstance(approved.get("commit"), str) and approved["commit"] != ""\n', "",
     ("tests.test_decide.Acceptance",)),
    ("a review on no commit is read", "kernel/derive.py",
     '        if not (isinstance(rv.get("commit"), str) and rv["commit"] != ""):\n            return True\n', "",
     ("tests.test_decide.Acceptance",)),
    ("a review's content id in another form is read", "kernel/derive.py",
     '        if not in_form(rv.get("content_id"), t.CONTENT_PREFIX, t.HEX_DIGITS):\n            return True\n', "",
     ("tests.test_decide.Acceptance",)),
    ("a review that says nothing of its dismissal is read", "kernel/derive.py",
     '        if "dismissed_by" not in rv or "dismissed_from" not in rv:\n            return True\n', "",
     ("tests.test_decide.Acceptance",)),
    ("reporters that cannot be read are read", "kernel/derive.py",
     "    if not readable_reporters(config):\n", "    if False:\n", ("tests.test_decide.Acceptance",)),
    ("a reporter named by anything but a name is read", "kernel/derive.py",
     "all(name is None or isinstance(name, str) for name in reporters.values())", "True",
     ("tests.test_decide.Acceptance",)),
    ("reporters that cannot be read are not the Maintainer's to see", "kernel/decide.py",
     ' "acceptance_reporters_unreadable",\n', "\n", ("tests.test_decide.Acceptance",)),
    ("a digest of any length is read", "kernel/derive.py",
     " and len(value) == len(t.DIGEST_SHAPE)", "", ("tests.test_decide.Acceptance",)),
    # A required model Lens has reported only through a review of this content that succeeded, and a Result that
    # leaves a criterion of its rubric uncovered is refused (decision 0029, I-37).
    ("a failed review Run counts as a report", "kernel/derive.py",
     '        and r["status"] == "completed"\n        and r["conclusion"] == "success"\n        for r in runs\n',
     '        and r["status"] == "completed"\n        for r in runs\n', (REPORTED + "test_a_review_run_that_failed_has_not_reported",)),
    ("a success with a fault is read as a report", "kernel/derive.py",
     '    if odd:\n        return {"state": None, "reason": "run_unreadable", "evidence": odd}\n', "",
     (REPORTED + "test_a_review_that_succeeded_with_a_fault_is_unreadable",)),
    ("a success with a fault is not the Maintainer's to see", "kernel/decide.py",
     '    "run_unreadable", "model_lens_input_needs_person",\n', '    "model_lens_input_needs_person",\n',
     (REPORTED + "test_a_review_that_succeeded_with_a_fault_is_unreadable",)),
    ("** is read within one name by the Kernel", "kernel/derive.py",
     "        if run == t.ANY_NAMES:\n", "        if False:\n",
     ("tests.test_tools.TheList.test_two_stars_as_a_whole_name_stand_for_any_run_of_names",)),
    ("a criterion left out is covered", "kernel/coverage.py",
     "        if len(mine) != 1 or not reported(mine[0], c in cites):\n",
     "        if len(mine) > 1 or (mine and not reported(mine[0], c in cites)):\n",
     (COVERAGE + "test_a_criterion_that_applies_must_be_covered",)),
    ("a criterion given twice is covered", "kernel/coverage.py",
     "        if len(mine) != 1 or not reported(mine[0], c in cites):\n",
     "        if not mine or not reported(mine[0], c in cites):\n",
     (COVERAGE + "test_a_criterion_that_applies_must_be_covered",)),
    ("a verdict that is none of the three is read", "kernel/coverage.py",
     "    if verdict not in t.VERDICTS:\n        return False\n", "",
     (COVERAGE + "test_a_criterion_that_applies_must_be_covered",)),
    ("an entry for a criterion the rubric lacks is passed over", "kernel/coverage.py",
     "        if said not in ids:\n", "        if False:\n",
     (COVERAGE + "test_a_criterion_that_applies_must_be_covered",)),
    ("an applies_when that cannot be read applies to nothing", "kernel/coverage.py",
     "        return True\n    return any(matches(", "        return False\n    return any(matches(",
     (COVERAGE + "test_a_criterion_that_applies_must_be_covered",)),
    ("the previous path is not read", "kernel/coverage.py",
     "    paths = names(changed)\n", '    paths = [entry["path"] for entry in changed]\n',
     (COVERAGE + "test_a_renamed_files_old_path_makes_a_criterion_apply",)),
    ("not_applicable needs no reason", "kernel/coverage.py",
     '    return verdict != t.NOT_APPLICABLE or is_code(entry.get("reason"))\n', "    return True\n",
     (COVERAGE + "test_not_applicable_needs_a_reason_code",)),
    ("finding needs no Finding", "kernel/coverage.py",
     "    if verdict == t.FINDING and not cited:\n        return False\n", "",
     (COVERAGE + "test_a_finding_verdict_needs_a_finding_that_cites_it",)),
    ("a Finding that cites a criterion met or not applicable is passed over", "kernel/coverage.py",
     "    if cited and verdict != t.FINDING:\n        return False\n", "",
     (COVERAGE + "test_a_finding_verdict_needs_a_finding_that_cites_it",)),
    ("an id with no letters is in form", "kernel/coverage.py",
     'hyphen != "" and letters != "" and digits != ""', 'hyphen != "" and digits != ""',
     (COVERAGE + "test_a_criterion_that_applies_must_be_covered",)),
    ("an id with no digits after its hyphen is in form", "kernel/coverage.py",
     "\n            and all(c in t.DIGITS for c in digits))", ")",
     (COVERAGE + "test_a_criterion_that_applies_must_be_covered",)),
    ("an id the rubric lacks is shown as it is, in any form", "kernel/coverage.py",
     '    shown = said if is_criterion_id(said) else "unreadable"\n', "    shown = said\n",
     (COVERAGE + "test_a_criterion_that_applies_must_be_covered",)),
    ("an id the rubric lacks is named as often as it is given", "kernel/coverage.py",
     "    if shown not in out:\n        out.append(shown)\n", "    out.append(shown)\n",
     (COVERAGE + "test_a_criterion_that_applies_must_be_covered",)),
    ("a rubric that names a criterion twice is read", "kernel/coverage.py",
     " and len(set(ids)) == len(ids)\n", "\n",
     (COVERAGE + "test_an_unreadable_rubric_is_unreadable_never_covered",)),
    ("paths that cannot be read whole are read", "kernel/coverage.py",
     "    return isinstance(changed, list) and all(readable_file(entry) for entry in changed)\n",
     "    return isinstance(changed, list)\n",
     (COVERAGE + "test_an_unreadable_rubric_is_unreadable_never_covered",)),
    # A Finding that cites a criterion has the rubric's severity, never the model's (section 3.14, issue 373).
    ("a cited Finding keeps any severity the model gives it", "kernel/coverage.py",
     '(f.get("severity"), f.get("category")) != given[said]',
     '(f.get("severity") in t.SEVERITIES, f.get("category")) != (True, given[said][1])',
     (COVERAGE + "test_a_finding_that_cites_a_criterion_has_the_rubrics_severity",
      "tests.test_apply.Apply.test_an_uncovered_result_writes_nothing")),
    # Issue 407: a Finding that cites a criterion is of the category the rubric gives it.
    ('a cited Finding keeps any category the model gives it', 'kernel/coverage.py',
     '(f.get("severity"), f.get("category")) != given[said]',
     '(f.get("severity"), f.get("category") in t.CATEGORIES) != (given[said][0], True)', (COVERAGE + "test_a_finding_that_cites_a_criterion_has_the_rubrics_category", "tests.test_apply.Apply.test_an_uncovered_result_writes_nothing")),
    ('a rubric whose criterion gives no category is read', 'kernel/coverage.py',
     '\n            and all(c.get("category") in t.CATEGORIES for c in criteria))',
     ')', (COVERAGE + "test_an_unreadable_rubric_is_unreadable_never_covered",)),
    ("a cited Finding is held to another criterion's category", 'kernel/coverage.py',
     'given = {c["id"]: (c["severity_if_violated"], c["category"]) for c in rubric["criteria"]}',
     'given = {c["id"]: (c["severity_if_violated"], rubric["criteria"][0]["category"]) for c in rubric["criteria"]}', (COVERAGE + "test_a_finding_that_cites_a_criterion_has_the_rubrics_category", "tests.test_apply.Apply.test_an_uncovered_result_writes_nothing")),
    # The reads of #405: every Finding is read, and one that cites an id the rubric lacks is uncovered.
    ('a Finding after the first is not read', 'kernel/coverage.py',
     '    for f in findings:\n        said = f.get("criterion") if isinstance(f, dict) else None\n',
     '    for f in findings[:1]:\n        said = f.get("criterion") if isinstance(f, dict) else None\n', (COVERAGE + "test_a_finding_that_cites_a_criterion_has_the_rubrics_severity",)),
    ('a wrong severity ends the reading of the Findings', 'kernel/coverage.py',
     '            out.append(said)\n        elif said is not None and said not in ids:\n',
     '            out.append(said)\n            break\n        elif said is not None and said not in ids:\n', (COVERAGE + "test_a_finding_that_cites_a_criterion_has_the_rubrics_severity",)),
    ('a Finding citing an id the rubric lacks is passed over', 'kernel/coverage.py',
     '        elif said is not None and said not in ids:\n            _off(said, out)\n',
     '', (COVERAGE + "test_a_finding_that_cites_a_criterion_has_the_rubrics_severity",)),
    ("only a criterion that applies gives a cited Finding its severity", "kernel/coverage.py",
     "        if said in ids and ", "        if said in applying and ",
     (COVERAGE + "test_a_finding_that_cites_a_criterion_has_the_rubrics_severity",)),
    ("a criterion cited at another severity is named as often as it is cited", "kernel/coverage.py",
     ' and said not in out:\n            out.append(said)\n', ':\n            out.append(said)\n',
     (COVERAGE + "test_a_finding_that_cites_a_criterion_has_the_rubrics_severity",)),
    ("a rubric whose criterion gives no severity is read", "kernel/coverage.py",
     '\n            and all(c.get("severity_if_violated") in t.SEVERITIES for c in criteria)\n', "\n",
     (COVERAGE + "test_an_unreadable_rubric_is_unreadable_never_covered",)),
    ("a contradictory Run by a Role no required Lens is is read", "kernel/derive.py",
     'if r["role"] in lenses and contradicts(r, facts)]', "if contradicts(r, facts)]",
     (REPORTED + "test_a_review_that_succeeded_with_a_fault_is_unreadable",)),
    ("a contradictory Run of another Intent is read", "kernel/derive.py",
     '    return (run["intent"] == "review-change" and run["content_id"] == facts["content_id"]\n',
     '    return (run["content_id"] == facts["content_id"]\n',
     (REPORTED + "test_a_review_that_succeeded_with_a_fault_is_unreadable",)),
    ("a contradictory Run on other content is read", "kernel/derive.py",
     '    return (run["intent"] == "review-change" and run["content_id"] == facts["content_id"]\n',
     '    return (run["intent"] == "review-change"\n',
     (REPORTED + "test_a_review_that_succeeded_with_a_fault_is_unreadable",)),
    ("a Run not yet completed can contradict itself", "kernel/derive.py",
     '            and run["status"] == "completed" and run["conclusion"] == "success" and run.get("outcome") is not None)',
     '            and run["conclusion"] == "success" and run.get("outcome") is not None)',
     (REPORTED + "test_a_review_that_succeeded_with_a_fault_is_unreadable",)),
    ("a review that failed by a fault contradicts itself", "kernel/derive.py",
     '            and run["status"] == "completed" and run["conclusion"] == "success" and run.get("outcome") is not None)',
     '            and run["status"] == "completed" and run.get("outcome") is not None)',
     (REPORTED + "test_a_review_that_succeeded_with_a_fault_is_unreadable",)),
    ("a review that succeeded with no fault contradicts itself", "kernel/derive.py",
     '            and run["status"] == "completed" and run["conclusion"] == "success" and run.get("outcome") is not None)',
     '            and run["status"] == "completed" and run["conclusion"] == "success")',
     (REPORTED + "test_a_review_that_succeeded_with_a_fault_is_unreadable",)),
    ("unreadable is read as covered", "kernel/coverage.py",
     '        return "unreadable", []\n', '        return "covered", []\n',
     (COVERAGE + "test_an_unreadable_rubric_is_unreadable_never_covered",)),
    # A change to the Factory's own rules or a Lens's input is reviewed by every model Lens (decision 0020, I-45).
    ("the list is never read", "kernel/derive.py",
     '    return [p for p in dict.fromkeys(config["protected_paths"]) if any(matches(p, path) for path in changed)]\n',
     "    return []\n", ("tests.test_decide.TheFactorysOwnRules",)),
    ("only the first path a pull request changes is read", "kernel/derive.py",
     'dict.fromkeys(config["protected_paths"]) if any(matches(p, path) for path in changed)]',
     'dict.fromkeys(config["protected_paths"]) if any(matches(p, path) for path in changed[:1])]',
     ("tests.test_decide.TheFactorysOwnRules",)),
    ("the path a file had before a rename is not matched", "kernel/derive.py",
     ' + [entry["previous"] for entry in changed if entry["previous"] is not None]', "",
     ("tests.test_decide.TheFactorysOwnRules",)),
    ("a pattern named twice is named twice", "kernel/derive.py",
     "for p in dict.fromkeys(config[\"protected_paths\"])", "for p in config[\"protected_paths\"]",
     ("tests.test_decide.TheFactorysOwnRules",)),
    ("two pieces of a pattern may overlap", "kernel/derive.py",
     "    return end >= at and path.endswith(", "    return path.endswith(",
     ("tests.test_decide.TheFactorysOwnRules",)),
    ("the pieces between two stars are not read", "kernel/derive.py",
     "    for piece in pieces[1:-1]:\n", "    for piece in pieces[1:1]:\n", ("tests.test_decide.Classes",)),
    ("a piece between two stars that is not there is passed over", "kernel/derive.py",
     "        if found < 0:\n", "        if False:\n", ("tests.test_decide.Classes",)),
    ("a pattern that matches nothing is read", "kernel/derive.py",
     "all(readable_pattern(p) for p in rules)", "all(isinstance(p, str) and p != \"\" for p in rules)",
     ("tests.test_decide.TheFactorysOwnRules",)),
    ("a pattern's final separator is read as a name", "kernel/derive.py",
     "    return readable_name(pattern[:-1] if pattern.endswith(t.SEPARATOR) else pattern)\n",
     "    return readable_name(pattern)\n", ("tests.test_decide.Readability",)),
    ("a record that is no file's is read", "kernel/derive.py",
     "    return (isinstance(entry, dict) and readable_name(", "    return (readable_name(",
     ("tests.test_decide.TheFactorysOwnRules",)),
    ("an unreadable previous path is read", "kernel/derive.py",
     '            and (entry["previous"] is None or readable_name(entry["previous"])))',
     '            and True)', ("tests.test_decide.TheFactorysOwnRules",)),
    ("a record without its previous path is read", "kernel/derive.py",
     ' and "previous" in entry\n', "\n", ("tests.test_decide.TheFactorysOwnRules",)),
    ("a list longer than the diff is read", "kernel/derive.py",
     "    return len(changed) == files and", "    return len(changed) >= files and",
     ("tests.test_decide.TheFactorysOwnRules",)),
    ("a path given twice is read", "kernel/derive.py",
     " and len(set(paths)) == len(paths)\n", "\n", ("tests.test_decide.TheFactorysOwnRules",)),
    ("a dependency update is excused on the list", "kernel/derive.py",
     "\n            and not touched(facts, config)):", "):", ("tests.test_decide.TheFactorysOwnRules",)),
    ("a final separator names only the directory", "kernel/derive.py",
     "        return any(n > 0 for n in counts)\n", "        return path.count(t.SEPARATOR) + 1 in counts\n",
     ("tests.test_decide.TheFactorysOwnRules",)),
    ("case is compared", "kernel/derive.py",
     "    pattern, path = pattern.casefold(), path.casefold()\n", "    pattern, path = pattern, path\n",
     ("tests.test_decide.TheFactorysOwnRules",)),
    ("a list of paths read short is trusted", "kernel/derive.py",
     "[name for name in t.READ_IN_FULL if flags.get(name) is not True]",
     '[name for name in t.READ_IN_FULL if name != "changed_paths" and flags.get(name) is not True]',
     ("tests.test_decide.Readability",)),
    ("an unreadable path is read", "kernel/derive.py",
     '    if not readable_paths(facts.get("changed_paths"), facts["diff"]["files"]):\n', "    if False:\n",
     ("tests.test_decide.TheFactorysOwnRules",)),
    ("a list of paths shorter than the diff is read", "kernel/derive.py",
     "    return len(changed) == files and", "    return len(changed) <= files and",
     ("tests.test_decide.TheFactorysOwnRules",)),
    ("an unreadable list of protected paths is read", "kernel/derive.py",
     "    if not readable_rules(config):\n", "    if False:\n", ("tests.test_decide.TheFactorysOwnRules",)),
    ("an empty list of protected paths is read", "kernel/derive.py",
     "isinstance(rules, list) and len(rules) > 0 and all(", "isinstance(rules, list) and all(",
     ("tests.test_decide.TheFactorysOwnRules",)),
    ("an unreadable list of protected paths is not the Maintainer's to see", "kernel/decide.py",
     ' "protected_paths_unreadable",\n', "\n", ("tests.test_decide.TheFactorysOwnRules",)),
    ("a name `..` is read", "kernel/terms.py",
     'NOT_A_NAME = ("", ".", "..")', 'NOT_A_NAME = ("", ".")', ("tests.test_decide.TheFactorysOwnRules",)),
    ("an empty name in a path is read", "kernel/terms.py",
     'NOT_A_NAME = ("", ".", "..")', 'NOT_A_NAME = (".", "..")', ("tests.test_decide.TheFactorysOwnRules",)),
    ("a list of paths that is no list is read", "kernel/derive.py",
     "    if not (isinstance(changed, list) and all(", "    if not (all(", ("tests.test_decide.TheFactorysOwnRules",)),
    ("a path that is not text is read", "kernel/derive.py",
     "    return isinstance(path, str) and not any(", "    return not any(",
     ("tests.test_decide.TheFactorysOwnRules",)),
    ("unreadable paths are not the Maintainer's to see", "kernel/decide.py",
     ' "paths_unreadable", "protected_paths_unreadable",', ' "protected_paths_unreadable",',
     ("tests.test_decide.TheFactorysOwnRules",)),
    ("unreadable paths are read before what needs no paths", "kernel/derive.py",
     '    if facts["state"] == "merged":\n', PATHS_GUARD + '    if facts["state"] == "merged":\n',
     ("tests.test_decide.HumanControl",)),
    ("the evidence is the paths", "kernel/derive.py",
     '"evidence": [lens] + rules}', '"evidence": [lens] + facts["changed_paths"]}', ("tests.test_decide.Readability",)),
    ("the wait names nothing on the list", "kernel/derive.py",
     '"evidence": [lens] + rules}', '"evidence": [lens]}', ("tests.test_decide.TheFactorysOwnRules",)),
    ("a queued change to the list is read past its missing review", "kernel/derive.py",
     '("awaiting_review" not in past or rules)', '"awaiting_review" not in past',
     ("tests.test_decide.TheFactorysOwnRules",)),
    # Issue 845: the scan's settings are read from a pull request's head beside SONAR_TOKEN.
    ("an unreadable pause is read as no pause", "kernel/brakes.py",
     'if context.get("paused") is False:', 'if not context.get("paused"):', ("tests.test_decide.Readability",)),
    ("attempts are unlimited", "kernel/brakes.py",
     '    if len(attempts) >= limits["max_attempts"]:\n', "    if False:\n",
     ("tests.test_decide.AReviewThatReported",)),
    ("the brakes are not asked about a Run", "kernel/decide.py",
     "    brake = brakes.on_run(", "    brake = None and brakes.on_run(", ("tests.test_decide.Readability",)),
    ("the brakes are not asked about an act", "kernel/decide.py",
     "    brake = brakes.on_act(", "    brake = None and brakes.on_act(", ("tests.test_decide.Readability",)),
    ("capacity faults count as attempts", "kernel/brakes.py",
     '            and (r.get("outcome") == "item" or (r.get("outcome") is None and r["conclusion"] in t.RAN_AND_DIED))]',
     "            ]", ("tests.test_decide.AReviewThatReported",)),
    # Issue 286's ruling: a Run that ran and left no outcome is an attempt; one cancelled, or that never ran, is none.
    ("a Run that ran and left no outcome is no attempt", "kernel/brakes.py",
     ' or (r.get("outcome") is None and r["conclusion"] in t.RAN_AND_DIED))]', ")]",
     ("tests.test_decide.AReviewThatReported.test_a_run_that_ran_and_left_no_outcome_is_an_attempt",)),
    # Issue 595: an approval killed with no outcome counts toward max_attempts, in the Kernel and in the simulator.
    ("an approval killed with no outcome is no attempt", "kernel/brakes.py",
     'r.get("outcome") is None and r["conclusion"] in t.RAN_AND_DIED',
     'r.get("outcome") is None and r["conclusion"] in t.RAN_AND_DIED and intent != t.ISSUE_APPROVAL',
     ("tests.test_decide.Ceilings.test_an_approval_that_ran_and_left_no_outcome_is_an_attempt",
      "tests.test_simulator.Simulation.test_an_approval_killed_with_no_outcome_is_bounded")),
    ("a Run cancelled with no outcome is an attempt", "kernel/brakes.py",
     'r.get("outcome") is None and r["conclusion"] in t.RAN_AND_DIED', 'r.get("outcome") is None',
     ("tests.test_decide.AReviewThatReported.test_a_review_run_that_failed_has_not_reported",
      "tests.test_decide.AReviewThatReported.test_a_run_that_ran_and_left_no_outcome_is_an_attempt")),
    ("a Run that timed out with no outcome is no attempt", "kernel/terms.py",
     'RAN_AND_DIED = ("failure", "timed_out")', 'RAN_AND_DIED = ("failure",)',
     ("tests.test_decide.AReviewThatReported.test_a_run_that_ran_and_left_no_outcome_is_an_attempt",)),
    ("a Run with any outcome but the item's is an attempt", "kernel/brakes.py",
     'r.get("outcome") is None and r["conclusion"] in t.RAN_AND_DIED', 'r.get("outcome") != "item" and r["conclusion"] in t.RAN_AND_DIED',
     ("tests.test_decide.AReviewThatReported.test_a_run_that_ran_and_left_no_outcome_is_an_attempt",)),
    ("rounds are unlimited", "kernel/brakes.py",
     '        if len(rounds) >= limits["max_rounds"]:\n', "        if False:\n", ("tests.test_decide.Ceilings",)),
    ("the run ceiling is ignored", "kernel/brakes.py",
     '    if len(_spent(recent)) >= limits["max_runs_per_item"]:\n', "    if False:\n",
     ("tests.test_decide.AReviewThatReported",)),
    ("a landed approval counts toward the Run ceiling", "kernel/brakes.py",
     '[r for r in recent if not (r["intent"] in (t.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.ENQUEUE_MERGE, t.DEQUEUE_MERGE)\n                                      and r["conclusion"] == "success") and r not in apart]',
     '[r for r in recent if r not in apart]', ("tests.test_decide.Ceilings",)),
    # Issue 757: a Role's Run that ended environment or never started is counted apart from the Run ceiling.
    ("a Run that ended environment counts toward the Run ceiling", "kernel/brakes.py",
     '                                      and r["conclusion"] == "success") and r not in apart]',
     '                                      and r["conclusion"] == "success")]', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("a Run that ended environment is bound by nothing", "kernel/brakes.py",
     '    if len(_outside(recent)) >= limits["max_environment_runs_per_item"]:\n', "    if False:\n",
     ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("the bound apart holds one Run late", "kernel/brakes.py",
     '    if len(_outside(recent)) >= limits["max_environment_runs_per_item"]:\n',
     '    if len(_outside(recent)) > limits["max_environment_runs_per_item"]:\n', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("an act's job that ended environment is counted apart", "kernel/brakes.py",
     '    return [r for r in recent if r["intent"] not in (t.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.ENQUEUE_MERGE, t.DEQUEUE_MERGE)\n            and (',
     '    return [r for r in recent if (', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("a Run that failed before its Engine step is not counted apart", "kernel/brakes.py",
     '            and ((r.get("outcome") == "environment" and r.get("engine_started") is False)\n                 or (',
     '            and ((', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("a Run that never started counts toward the Run ceiling", "kernel/brakes.py",
     ' or (r.get("never_ran") is not None and r.get("outcome") is None))]', ')]', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("a word beside an outcome is counted apart", "kernel/brakes.py",
     '(r.get("never_ran") is not None and r.get("outcome") is None)', 'r.get("never_ran") is not None',
     ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("a Run that reached the Engine is counted apart", "kernel/brakes.py",
     ' and r.get("engine_started") is False)\n', ')\n', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("a Run that does not say whether it reached the Engine is counted apart", "kernel/brakes.py",
     'r.get("engine_started") is False)', 'r.get("engine_started") is not True)', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("a resolution's job that spent no model is counted apart", "kernel/brakes.py",
     'r["intent"] not in (t.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.ENQUEUE_MERGE, t.DEQUEUE_MERGE)\n            and ((',
     'r["intent"] not in (t.ISSUE_APPROVAL, t.ENQUEUE_MERGE, t.DEQUEUE_MERGE)\n            and ((', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("an enqueue's job that spent no model is counted apart", "kernel/brakes.py",
     'r["intent"] not in (t.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.ENQUEUE_MERGE, t.DEQUEUE_MERGE)\n            and ((',
     'r["intent"] not in (t.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.DEQUEUE_MERGE)\n            and ((', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("a dequeue's job that spent no model is counted apart", "kernel/brakes.py",
     'r["intent"] not in (t.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.ENQUEUE_MERGE, t.DEQUEUE_MERGE)\n            and ((',
     'r["intent"] not in (t.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.ENQUEUE_MERGE)\n            and ((', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("a Run of any outcome that failed before its Engine step is counted apart", "kernel/brakes.py",
     '(r.get("outcome") == "environment" and r.get("engine_started") is False)', '(r.get("engine_started") is False)', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("a Run with no outcome is counted apart as one that never started", "kernel/brakes.py",
     '(r.get("never_ran") is not None and r.get("outcome") is None)', '(r.get("outcome") is None)', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("an approval's job that spent no model is counted apart", "kernel/brakes.py",
     'r["intent"] not in (t.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.ENQUEUE_MERGE, t.DEQUEUE_MERGE)\n            and ((',
     'r["intent"] not in (t.RESOLVE_THREAD, t.ENQUEUE_MERGE, t.DEQUEUE_MERGE)\n            and ((', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("the bound apart is named before the Run ceiling", "kernel/brakes.py",
     '    # The Run ceiling is the cost ceiling (FR-39). A landed approval spent no model, and is counted as an act.\n',
     '    # The Run ceiling is the cost ceiling (FR-39). A landed approval spent no model, and is counted as an act.\n'
     '    if len(_outside(recent)) >= limits["max_environment_runs_per_item"]:\n'
     '        return _decision(facts, t.HELD, "environment_ceiling", [], t.HOLD)\n', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    ("the bound apart calls nobody", "kernel/decide.py",
     '"run_ceiling", "environment_ceiling", "max_rounds"', '"run_ceiling", "max_rounds"', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    # Issue 962: a conflict the base's next move clears at once, and the platform's ending of a ceiling Hold.
    ("an approval that did not land is free of the Run ceiling", "kernel/brakes.py",
     'not (r["intent"] in (t.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.ENQUEUE_MERGE, t.DEQUEUE_MERGE)\n                                      and r["conclusion"] == "success")', 'r["intent"] not in (t.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.ENQUEUE_MERGE, t.DEQUEUE_MERGE)',
     ("tests.test_decide.Ceilings",)),
    ("an approval that keeps failing for the environment is issued for ever", "kernel/brakes.py",
     '    if len(_spent(since)) >= limits["max_runs_per_item"]:\n', "    if False:\n", ("tests.test_decide.Ceilings",)),
    ("an approval that does not land is issued for ever", "kernel/brakes.py",
     '    failed = _attempts(since, intent)\n    if len(failed) >= limits["max_attempts"]:\n', '    failed = _attempts(since, intent)\n    if False:\n', ("tests.test_decide.Ceilings",)),
    ("with no writer's action, no Run counts toward a ceiling", "kernel/derive.py",
     "    if mark is None:\n        return runs\n    return [r for r in runs if r[\"started_at\"] > mark]",
     "    if mark is None:\n        return []\n    return [r for r in runs if r[\"started_at\"] > mark]",
     ("tests.test_decide.Ceilings",)),
    ("a writer's action does not renew an approval's allowance", "kernel/decide.py",
     "    since = since_writer(mine, facts)\n", "    since = mine\n", ("tests.test_decide.Ceilings",)),
    ("a failed model Run counts as an approval attempt", "kernel/brakes.py",
     "_attempts(since, intent)",
     '[r for r in since if r["status"] == "completed" and r["conclusion"] != "success" and r.get("outcome") == "item"]',
     ("tests.test_decide.Ceilings",)),
    ("an approval's failed attempts stop an enqueue", "kernel/brakes.py",
     '    if action in run_acts:\n        held = approval_ceilings(_decision, facts, since, limits, run_acts[action])', '    if action in run_acts or action == "enqueue":\n        held = approval_ceilings(_decision, facts, since, limits, run_acts.get(action, t.ISSUE_APPROVAL))', ("tests.test_decide.Ceilings",)),
    ("acts are unlimited", "kernel/brakes.py",
     '    if readable and acts + _landed(acted) >= limits["max_acts_per_item"]:\n', "    if False:\n", ("tests.test_decide.Classes",)),
    ("the act ceiling is reached one act late", "kernel/brakes.py",
     'acts + _landed(acted) >= limits["max_acts_per_item"]', 'acts + _landed(acted) > limits["max_acts_per_item"]', ("tests.test_decide.Classes",)),
    ("an enqueue is not held to the act ceiling", "kernel/brakes.py",
     '    if readable and acts + _landed(acted) >= limits["max_acts_per_item"]:\n',
     '    if readable and acts + _landed(acted) >= limits["max_acts_per_item"] and action == "issue_approval":\n',
     ("tests.test_decide.Ceilings",)),
    ("an unreadable count of acts is read as none", "kernel/brakes.py",
     '    acts = facts.get("acts_since_writer")\n', '    acts = facts.get("acts_since_writer") or 0\n',
     ("tests.test_decide.Ceilings",)),
    ("a count of acts that is not a whole number is trusted", "kernel/brakes.py",
     "readable = type(acts) is int and acts >= 0", "readable = isinstance(acts, int) and acts >= 0",
     ("tests.test_decide.Ceilings",)),
    ("a negative count of acts is trusted", "kernel/brakes.py",
     "readable = type(acts) is int and acts >= 0", "readable = type(acts) is int", ("tests.test_decide.Ceilings",)),
    ("the act ceiling is not the Maintainer's to see", "kernel/decide.py",
     '"awaiting_human", "act_ceiling",', '"awaiting_human",', ("tests.test_decide.Ceilings",)),
    ("an unreadable check is not the Maintainer's to see", "kernel/decide.py",
     '"act_ceiling", "check_unreadable",', '"act_ceiling",', ("tests.test_decide.Content",)),
    ("the act ceiling stops a Run", "kernel/decide.py",
     "    wanted = _wanted_run(facts, state, reason, config, evidence)\n",
     '    if facts.get("acts_since_writer") is None or facts["acts_since_writer"] >= config["limits"]["max_acts_per_item"]:\n'
     '        return _decision(facts, t.HELD, "act_ceiling", [], t.HOLD)\n'
     "    wanted = _wanted_run(facts, state, reason, config, evidence)\n", ("tests.test_decide.Classes",)),
    # Issue 855: with two model Lenses, the one the evidence names is the one admitted.
    ("the first model Lens is admitted whatever the evidence names", "kernel/decide.py",
     '        return (evidence[0], "review-change")\n', '        return (config["required_lenses"]["model"][0], "review-change")\n',
     ("tests.test_decide.OnlyAPersonEnds.test_with_two_model_lenses_the_one_awaited_is_the_one_admitted",)),
    # Decision 0036: a Run listed before its run-name defers every admission, an approval among them, after the brakes.
    ("an unidentified Run lets an approval through", "kernel/decide.py",
     '    if action == "issue_approval" and unnamed_within(context, now, config["limits"]) != []:\n', "    if False:\n",
     (UNIDENTIFIED + "test_an_unidentified_run_defers_an_approval",)),
    ("an unreadable list of unidentified Runs lets an approval through", "kernel/decide.py",
     '    if action == "issue_approval" and unnamed_within(context, now, config["limits"]) != []:\n',
     '    if action == "issue_approval" and unnamed_within(context, now, config["limits"]):\n',
     (UNIDENTIFIED + "test_a_list_of_unidentified_runs_that_cannot_be_read_defers_an_approval",)),
    ("an unidentified Run hides an approval's Hold", "kernel/decide.py",
     *moved_after("kernel/decide.py", ACT_BRAKES, UNIDENTIFIED_DEFERS),
     (UNIDENTIFIED + "test_an_unidentified_run_defers_an_approval",)),
    # Issue 270: an unidentified Run past max_unnamed_run_seconds defers nothing and is one alert, by its run id.
    ("a Run unnamed past the window still defers", "kernel/derive.py",
     '            if unnamed_age(entry, now) < window or entry["status"] != t.RUN_COMPLETED]',
     '            if True]', (UNIDENTIFIED + "test_an_unidentified_run_past_the_window_admits_and_is_one_alert",)),
    ("a Run unnamed for the whole window still defers", "kernel/derive.py",
     'if unnamed_age(entry, now) < window or', 'if unnamed_age(entry, now) <= window or', (UNIDENTIFIED + "test_an_unidentified_run_past_the_window_admits_and_is_one_alert",)),
    ("a Run unnamed past the window that has not completed admits", "kernel/derive.py",
     '            if unnamed_age(entry, now) < window or entry["status"] != t.RUN_COMPLETED]',
     '            if unnamed_age(entry, now) < window]', (UNIDENTIFIED + "test_an_unidentified_run_past_the_window_admits_and_is_one_alert",)),
    ("a window of no seconds is read", "kernel/derive.py",
     'type(window) is int and window >= 1', 'type(window) is int and window >= 0', (UNIDENTIFIED + "test_an_unidentified_run_that_cannot_be_read_defers_and_raises_no_alert",)),
    ("a window that is no whole number of seconds is read", "kernel/derive.py",
     'type(window) is int and window >= 1', 'isinstance(window, (int, float)) and window >= 1', (UNIDENTIFIED + "test_an_unidentified_run_that_cannot_be_read_defers_and_raises_no_alert",)),
    ("a bound of no Runs is read", "kernel/derive.py",
     'type(most) is int and most >= 1', 'type(most) is int and most >= 0', (UNIDENTIFIED + "test_an_unidentified_run_that_cannot_be_read_defers_and_raises_no_alert",)),
    ("a bound that is no whole number is read", "kernel/derive.py",
     'type(most) is int and most >= 1', 'isinstance(most, (int, float)) and most >= 1', (UNIDENTIFIED + "test_an_unidentified_run_that_cannot_be_read_defers_and_raises_no_alert",)),
    ("an empty list of unnamed Runs asks for the window and the moment", "kernel/derive.py",
     '    if listed == []:\n        return []\n', '', ("tests.test_issue.Stale.test_a_now_that_is_no_moment_shows_a_wait_as_stale_and_raises_nothing",)),
    ("an unnamed Run whose id is no number is read", "kernel/derive.py",
     '                and all(c in t.DIGITS for c in entry["run"]) and is_time(entry.get("created_at"))\n',
     '                and is_time(entry.get("created_at"))\n', (UNIDENTIFIED + "test_an_unidentified_run_that_cannot_be_read_defers_and_raises_no_alert",)),
    ("an unnamed Run with an empty id is read", "kernel/derive.py",
     'isinstance(entry.get("run"), str) and entry["run"]\n', 'isinstance(entry.get("run"), str)\n', (UNIDENTIFIED + "test_an_unidentified_run_that_cannot_be_read_defers_and_raises_no_alert",)),
    ("an unnamed Run whose status cannot be read is read", "kernel/derive.py",
     '\n                and entry.get("status") in t.RUN_STATUSES):', '):', (UNIDENTIFIED + "test_an_unidentified_run_that_cannot_be_read_defers_and_raises_no_alert",)),
    ("an alert names a Run inside the window", "kernel/derive.py",
     '        if unnamed_age(entry, now) >= window and entry["run"] not in past:\n',
     '        if entry["run"] not in past:\n', (UNIDENTIFIED + "test_an_unidentified_run_past_the_window_admits_and_is_one_alert",)),
    ("an unnamed Run is an alert each time it is listed", "kernel/derive.py",
     '        if unnamed_age(entry, now) >= window and entry["run"] not in past:\n',
     '        if unnamed_age(entry, now) >= window:\n', (UNIDENTIFIED + "test_an_unidentified_run_past_the_window_admits_and_is_one_alert",)),
    ("an alert names a Run of a list that cannot be read", "kernel/derive.py",
     '    listed, within = unnamed_runs(context), unnamed_within(context, now, limits)\n    if listed is None or within is None:\n        return []\n',
     '    listed, within = unnamed_runs(context), unnamed_within(context, now, limits)\n    if listed is None:\n        return []\n',
     (UNIDENTIFIED + "test_an_unidentified_run_that_cannot_be_read_defers_and_raises_no_alert",)),
    ("an alert of a configuration that is no object raises", "kernel/decide.py",
     '    limits = config.get("limits") if isinstance(config, dict) else None\n', '    limits = config["limits"]\n',
     (UNIDENTIFIED + "test_an_unidentified_run_that_cannot_be_read_defers_and_raises_no_alert",)),
    ("an alert of a context that is no object raises", "kernel/derive.py",
     '    listed = context.get("unidentified_runs") if isinstance(context, dict) else None\n',
     '    listed = context.get("unidentified_runs")\n',
     (UNIDENTIFIED + "test_an_unidentified_run_that_cannot_be_read_defers_and_raises_no_alert",)),
    ("the bound of Runs unnamed is read with none past the window", "kernel/derive.py",
     'if past and len(past) > limits["max_unnamed_runs"]', 'if len(past) > limits["max_unnamed_runs"]',
     (UNIDENTIFIED + "test_past_max_unnamed_runs_every_run_defers",)),
    ("the bound of Runs unnamed comes before an approval's brakes", "kernel/decide.py",
     '    brake = brakes.on_act(_decision, facts, state, evidence, context, action, since, config["limits"],\n                          acted_since_writer(mine, facts))\n    if brake:\n        return brake\n',
     '    past = unnamed_past(context, now, config["limits"]) if action == "issue_approval" else []\n    if past and len(past) > config["limits"]["max_unnamed_runs"]:\n        return _decision(facts, state, "runs_unnamed", evidence, t.DEFER)\n    brake = brakes.on_act(_decision, facts, state, evidence, context, action, since, config["limits"])\n    if brake:\n        return brake\n',
     (UNIDENTIFIED + "test_past_max_unnamed_runs_every_run_defers",)),
    ("the scope's reading never defers", "kernel/decide.py",
     '    defers = unnamed_within(context, now, limits) != []\n', '    defers = False\n',
     (UNIDENTIFIED + "test_the_scope_reads_the_unnamed_runs_as_each_decision_does",)),
    ("the scope's reading is never bounded", "kernel/decide.py",
     '"bounded": not defers and bool(alerts) and len(alerts) > most}', '"bounded": False}',
     (UNIDENTIFIED + "test_the_scope_reads_the_unnamed_runs_as_each_decision_does",)),
    ("the scope's bound is reached at the bound", "kernel/decide.py",
     '"bounded": not defers and bool(alerts) and len(alerts) > most}',
     '"bounded": not defers and bool(alerts) and len(alerts) >= most}',
     (UNIDENTIFIED + "test_the_scope_reads_the_unnamed_runs_as_each_decision_does",)),
    ("Runs unnamed past the window are not bounded", "kernel/derive.py",
     '    if past and len(past) > limits["max_unnamed_runs"]:\n', "    if False:\n", (UNIDENTIFIED + "test_past_max_unnamed_runs_every_run_defers",)),
    ("as many Runs unnamed past the window as the bound defer", "kernel/derive.py",
     'if past and len(past) > limits["max_unnamed_runs"]', 'if past and len(past) >= limits["max_unnamed_runs"]', (UNIDENTIFIED + "test_past_max_unnamed_runs_every_run_defers",)),
    ("an approval past the bound of Runs unnamed goes ahead", "kernel/decide.py",
     '    if past and len(past) > config["limits"]["max_unnamed_runs"]:\n', "    if False:\n", (UNIDENTIFIED + "test_past_max_unnamed_runs_every_run_defers",)),
    ("the approval reads the bound with none past the window", "kernel/decide.py",
     '    if past and len(past) > config["limits"]["max_unnamed_runs"]:\n',
     '    if len(past) > config["limits"]["max_unnamed_runs"]:\n', (UNIDENTIFIED + "test_past_max_unnamed_runs_every_run_defers",)),
    ("as many Runs unnamed past the window as the bound defer an approval", "kernel/decide.py",
     'if past and len(past) > config["limits"]["max_unnamed_runs"]:',
     'if past and len(past) >= config["limits"]["max_unnamed_runs"]:', (UNIDENTIFIED + "test_past_max_unnamed_runs_every_run_defers",)),
    ("the bound of Runs unnamed defers an enqueue", "kernel/decide.py",
     '    past = unnamed_past(context, now, config["limits"]) if action == "issue_approval" else []\n',
     '    past = unnamed_past(context, now, config["limits"])\n', (UNIDENTIFIED + "test_past_max_unnamed_runs_every_run_defers",)),
    ("the bound's deferral goes stale", "kernel/terms.py",
     '"run_unidentified", "runs_unnamed"})', '"run_unidentified"})',
     ("tests.test_decide.Staleness.test_a_deferral_of_the_whole_scope_is_never_stale",)),
    ("an unidentified Run defers an enqueue", "kernel/decide.py",
     '    if action == "issue_approval" and unnamed_within(context, now, config["limits"]) != []:\n',
     '    if unnamed_within(context, now, config["limits"]) != []:\n',
     (UNIDENTIFIED + "test_an_unidentified_run_stops_no_enqueue_and_no_dequeue",)),
    ("an unidentified Run hides a Hold", "kernel/decide.py",
     *moved_after("kernel/decide.py", RUN_BRAKES, DEFERRAL_CALL),
     (UNIDENTIFIED + "test_an_unidentified_run_is_asked_after_the_brakes",)),
    ("an unidentified Run's deferral goes stale", "kernel/terms.py",
     '"run_unidentified", "runs_unnamed"})', '"runs_unnamed"})',
     ("tests.test_decide.Staleness.test_a_deferral_of_the_whole_scope_is_never_stale",)),
    # Decision 0248: every reason is in one of two sets, a pull request's and an issue's own.
    ("a member is dropped from REASONS", "kernel/terms.py",
     '"thread_unreadable", "too_large",\n', '"thread_unreadable",\n', ("tests.test_reasons.Given.test_every_decision_and_every_member_keeps_to_its_set",)),
    ("a member nothing produces is added", "kernel/terms.py",
     "\nREASONS = frozenset({\n", '\nREASONS = frozenset({"never_given",\n', ("tests.test_reasons.Given.test_every_decision_and_every_member_keeps_to_its_set",)),
    ("a literal reason in SCOPE_DEFERRALS is in neither set", "kernel/terms.py",
     '"capacity_unreadable", "concurrency",\n', '"capacity_unreadable", "concurrence",\n',
     ("tests.test_reasons.Written.test_every_reason_the_kernel_writes_is_in_its_set",)),
    ("an issue-only reason is listed as a pull-request one", "kernel/terms.py",
     '"too_large",\n})\nISSUE_REASONS = frozenset({\n    "acceptance_due", ',
     '"too_large", "acceptance_due",\n})\nISSUE_REASONS = frozenset({\n    ', ("tests.test_reasons.Given.test_every_decision_and_every_member_keeps_to_its_set",)),
    ("the two sets share a reason", "kernel/terms.py",
     "\nISSUE_REASONS = frozenset({\n", '\nISSUE_REASONS = frozenset({"draft",\n',
     ("tests.test_reasons.Written.test_the_two_sets_are_apart_and_each_is_codes",)),
    ("a pull request's reason is listed as an issue's alone", "kernel/terms.py",
     '"thread_unreadable", "too_large",\n})\nISSUE_REASONS = frozenset({\n',
     '"thread_unreadable",\n})\nISSUE_REASONS = frozenset({\n"too_large", ', ("tests.test_reasons.Written.test_every_reason_the_kernel_writes_is_in_its_set",)),
    ("an issue's own reason is dropped from ISSUE_REASONS", "kernel/terms.py",
     '"triage_stands", "type_unreadable",\n', '"triage_stands",\n',
     ("tests.test_reasons.Given.test_every_decision_and_every_member_keeps_to_its_set",)),
    ("a member no issue gives is added to ISSUE_REASONS", "kernel/terms.py",
     "\nISSUE_REASONS = frozenset({\n", '\nISSUE_REASONS = frozenset({"never_given",\n',
     ("tests.test_reasons.Given.test_every_decision_and_every_member_keeps_to_its_set",)),
    ("a member that is no code is added", "kernel/terms.py",
     "\nISSUE_REASONS = frozenset({\n", '\nISSUE_REASONS = frozenset({"not a code",\n',
     ("tests.test_reasons.Written.test_the_two_sets_are_apart_and_each_is_codes",)),
    ("a member of REASONS that is no code is added", "kernel/terms.py",
     "\nREASONS = frozenset({\n", '\nREASONS = frozenset({"Not a code",\n',
     ("tests.test_reasons.Written.test_the_two_sets_are_apart_and_each_is_codes",)),
    ("the Kernel reads the issue's set of reasons", "kernel/terms.py",
     '    "unmerged_closes", "writer_unreadable",\n})\n', '    "unmerged_closes", "writer_unreadable",\n})\nKNOWN = ISSUE_REASONS\n',
     ("tests.test_reasons.Written.test_no_kernel_rule_reads_the_sets",)),
    ("an issue reason the Kernel writes is in neither set", "kernel/terms.py",
     '"linked_twice", "linked_unreadable",', '"linked_unreadable",',
     ("tests.test_reasons.Written.test_every_reason_the_kernel_writes_is_in_its_set",)),
    ("the Kernel reads a set of reasons", "kernel/terms.py",
     "\nISSUE_REASONS = frozenset({\n", "\nISSUE_REASONS = REASONS ^ REASONS | frozenset({\n",
     ("tests.test_reasons.Written.test_no_kernel_rule_reads_the_sets",)),
    ("a wait is stale at its limit, not past it", "kernel/derive.py",
     "    return waited > lifecycle", "    return waited >= lifecycle", ("tests.test_decide.Staleness",)),
    ("a wait counts while no passes ran", "kernel/derive.py",
     "    starts = [x for x in (moved, passes_since) if is_time(x) and x <= now]\n",
     "    starts = [x for x in (moved,) if is_time(x) and x <= now]\n", ("tests.test_decide.Classes",)),
    ("an unreadable start of the passes is trusted", "kernel/derive.py",
     "    starts = [x for x in (moved, passes_since) if is_time(x) and x <= now]\n",
     "    starts = [x for x in (moved, passes_since) if x is not None]\n", ("tests.test_decide.Staleness",)),
    ("a start of the passes still to come is trusted", "kernel/derive.py",
     "    starts = [x for x in (moved, passes_since) if is_time(x) and x <= now]\n",
     "    starts = [x for x in (moved, passes_since) if is_time(x)]\n", ("tests.test_decide.Staleness",)),
    ("a wait counts from the item's first movement", "kernel/derive.py",
     "    return max(readable) if readable else None\n", "    return min(readable) if readable else None\n",
     ("tests.test_decide.Staleness",)),
    ("a time still to come moves an item", "kernel/derive.py",
     "    readable = [x for x in times if is_time(x) and x <= now]\n", "    readable = [x for x in times if is_time(x)]\n",
     ("tests.test_decide.Staleness",)),
    ("a time that is no moment moves an item", "kernel/derive.py",
     "    readable = [x for x in times if is_time(x) and x <= now]\n",
     "    readable = [x for x in times if isinstance(x, str) and x <= now]\n", ("tests.test_decide.Staleness",)),
    ("a required check that reports does not move an item", "kernel/derive.py",
     '    times += [c.get("completed_at") for c in facts["checks"]'
     " if any(reports_for(c, lens) for lens in required)]\n", "", ("tests.test_decide.Staleness",)),
    ("a check that is not required moves an item", "kernel/derive.py",
     ' for c in facts["checks"] if any(reports_for(c, lens) for lens in required)]', ' for c in facts["checks"]]',
     ("tests.test_decide.Staleness",)),
    ("a check from another App moves an item", "kernel/derive.py",
     " if any(reports_for(c, lens) for lens in required)]",
     " if any(named_for(c, lens) for lens in required)]", ("tests.test_decide.Staleness",)),
    ("a check from another workflow file moves an item", "kernel/derive.py",
     " if any(reports_for(c, lens) for lens in required)]",
     " if any(named_for(c, lens) and from_its_app(c, lens) for lens in required)]", ("tests.test_decide.Staleness",)),
    ("an App that is no Lens's moves an item", "kernel/derive.py",
     'actor.get("kind") in ("lens", t.MACHINE_USER)', 'actor.get("kind") in ("lens", t.MACHINE_USER, t.APP)',
     ("tests.test_decide.Staleness",)),
    ("the machine user's approval does not move an item", "kernel/derive.py",
     'actor.get("kind") in ("lens", t.MACHINE_USER)', 'actor.get("kind") == "lens"', ("tests.test_decide.Staleness",)),
    ("a writer's or a Lens's review does not move an item", "kernel/derive.py",
     '    times += [rv.get("submitted_at") for rv in facts["reviews"] if moves(rv.get("by"))]\n', "",
     ("tests.test_decide.Staleness",)),
    ("a writer's or a Lens's thread does not move an item", "kernel/derive.py",
     '    times += [th.get("opened_at") for th in facts["threads"] if moves(th.get("opened_by"))]\n', "",
     ("tests.test_decide.Staleness",)),
    ("a Run on another item moves this one", "kernel/derive.py",
     '    times += [r["started_at"] for r in runs_on(runs, facts)]\n', '    times += [r["started_at"] for r in runs]\n',
     ("tests.test_decide.Staleness",)),
    ("a day its month does not have is a moment", "kernel/derive.py",
     "1 <= day <= days_in(year, month)", "1 <= day", ("tests.test_decide.OnlyAPersonEnds",)),
    ("an hour past the day is a moment", "kernel/derive.py",
     "            and hour < t.HOURS_PER_DAY and minute", "            and minute", ("tests.test_decide.Staleness",)),
    ("a deferral of the whole scope goes stale", "kernel/decide.py",
     ' and d["reason"] not in t.SCOPE_DEFERRALS', "", ("tests.test_decide.Staleness",)),
    ("the model provider's deferral goes stale", "kernel/terms.py",
     '"pause_unreadable", "capacity", "capacity_unreadable"', '"pause_unreadable", "capacity_unreadable"',
     ("tests.test_decide.Staleness",)),
    ("a stale wait changes what happens", "kernel/decide.py",
     "        return dict(d, attention=t.STALE)\n", "        return dict(d, attention=t.STALE, outcome=t.NOTHING)\n",
     ("tests.test_decide.Staleness",)),
    ("an item that needs the Maintainer goes stale", "kernel/terms.py",
     "MAY_GO_STALE = frozenset({REVIEW, READY})", "MAY_GO_STALE = frozenset({REVIEW, READY, NEEDS_YOU})",
     ("tests.test_decide.HumanControl",)),
    ("a working item goes stale", "kernel/terms.py",
     "MAY_GO_STALE = frozenset({REVIEW, READY})", "MAY_GO_STALE = frozenset({REVIEW, READY, WORKING})",
     ("tests.test_decide.Staleness",)),
    ("a failed item goes stale", "kernel/terms.py",
     "MAY_GO_STALE = frozenset({REVIEW, READY})", "MAY_GO_STALE = frozenset({REVIEW, READY, FAILED})",
     ("tests.test_decide.Staleness",)),
    ("every hundredth year is a leap year", "kernel/derive.py",
     "(year % unless != 0 or year % still == 0)", "True", ("tests.test_decide.Staleness",)),
    ("a spent count waits behind a Run in flight", "kernel/decide.py",
     '        if held:\n            return held\n        return _decision(facts, state, reason, evidence, t.NOTHING, working=True)', '        return _decision(facts, state, reason, evidence, t.NOTHING, working=True)', ("tests.test_decide.Ceilings",)),
    ("a Run in flight counts toward the ceiling", "kernel/decide.py",
     'done = [r for r in since_writer(mine, facts) if r["status"] == "completed"]', "done = since_writer(mine, facts)",
     ("tests.test_decide.Ceilings",)),
    ("a converged item's spent approvals wait behind a Run in flight", "kernel/decide.py",
     '        if state == t.CONVERGED and _action(reason) == "issue_approval":\n', "        if False:\n",
     ("tests.test_decide.Ceilings",)),
    ("a spent count of the wanted Run waits behind a Run in flight", "kernel/decide.py",
     "        elif wanted is not None:\n", "        elif False:\n", ("tests.test_decide.Ceilings",)),
    ("failed approvals hold an approved item while a Run waits", "kernel/decide.py",
     ' and _action(reason) == "issue_approval":\n', ":\n", ("tests.test_decide.Ceilings",)),
    ("a deferral hides a spent approval count while a Run waits", "kernel/decide.py",
     "held = brakes.approval_ceilings(_decision, facts, done, config[\"limits\"], t.ISSUE_APPROVAL)",
     "held = brakes.on_act(_decision, facts, state, evidence, context, _action(reason), done, config[\"limits\"])",
     ("tests.test_decide.Ceilings",)),
    ("spent rounds wait behind a Run in flight", "kernel/decide.py",
     'wanted[1], done, config["limits"])', 'wanted[1], done, dict(config["limits"], max_rounds=len(done) + 1))',
     ("tests.test_decide.Ceilings",)),
    ("a deferral hides a spent count of Runs while a Run waits", "kernel/decide.py",
     "held = brakes.run_ceilings(_decision, facts, evidence, wanted[1], done, config[\"limits\"])",
     "held = brakes.on_run(_decision, facts, state, evidence, context, wanted[1], done, config[\"limits\"])",
     ("tests.test_decide.Ceilings",)),
    # Its first test is the one that tells it: the cases of LOST_TESTS put cd ~- after a cd the hook placed, which the
    # reading takes back before this line (decision 0040), so the mutant passed them and fell to the whole suite, which
    # outgrew TIMEOUT in a shard of PR 404.
    ("a spent count waits behind the Pause", "kernel/brakes.py",
     *moved_after("kernel/brakes.py",
                  "    held = run_ceilings(_decision, facts, evidence, intent, recent, limits)\n"
                  "    if held:\n        return held\n", "        return pause\n"), ("tests.test_decide.Ceilings",)),
    ("an approval's spent count waits behind the Pause", "kernel/brakes.py",
     *moved_after("kernel/brakes.py",
                  '    if action in run_acts:\n'
                  "        held = approval_ceilings(_decision, facts, since, limits, run_acts[action])\n"
                  "        if held:\n            return held\n", "        return stopped\n"),
     ("tests.test_decide.Ceilings",)),
    ("the act ceiling waits behind the Pause", "kernel/brakes.py",
     *moved_after("kernel/brakes.py",
                  '    if readable and acts + _landed(acted) >= limits["max_acts_per_item"]:\n'
                  '        return _decision(facts, t.HELD, "act_ceiling", [], t.HOLD)\n', "        return stopped\n"),
     ("tests.test_decide.Ceilings",)),
    ("an unreadable count of acts defers before the Pause", "kernel/brakes.py",
     *moved_after("kernel/brakes.py",
                  "    stopped = paused(_decision, facts, state, evidence, context)\n"
                  "    if stopped:\n        return stopped\n",
                  '        return _decision(facts, state, "acts_unreadable", evidence, t.DEFER)\n'),
     ("tests.test_decide.Ceilings",)),
    ("the Run ceiling holds an item that wants no Run", "kernel/decide.py",
     '    if reason == "check_unreadable":\n',
     '    if reason == "check_unreadable":\n'
     '        return brakes.run_ceilings(_decision, facts, evidence, "", since_writer(mine, facts), config["limits"]) or'
     " _decision(facts, state, reason, evidence, t.DEFER)\n"
     "    if False:\n", ("tests.test_decide.Ceilings",)),
    ("the Run ceiling holds an item that wants no Run while a Run waits", "kernel/decide.py",
     "        elif wanted is not None:\n"
     '            held = brakes.run_ceilings(_decision, facts, evidence, wanted[1], done, config["limits"])\n',
     "        else:\n"
     '            held = brakes.run_ceilings(_decision, facts, evidence, wanted[1] if wanted else "", done,'
     ' config["limits"])\n', ("tests.test_decide.Ceilings",)),
    # Issue 140: a change to a model Lens's own inputs needs a person.
    ("a change to a model Lens's input waits for nobody", 'kernel/derive.py',
     '    if own and not judged_by_a_person(facts):\n',
     '    if False:\n', ('tests.test_decide.TheFactorysOwnRules.test_a_change_to_a_model_lenss_own_input_waits_for_a_person',)),
    ("an approval of an earlier head is a person's judgment", 'kernel/derive.py',
     ' and standing and rv["content_id"] == facts["content_id"]:',
     ' and standing:', ('tests.test_decide.TheFactorysOwnRules.test_a_persons_approval_of_the_current_head_lets_it_converge',)),
    ("anyone's approval is a judge's", 'kernel/derive.py',
     '        if is_person(rv["by"]) and rv["state"] != "commented" and rv["dismissed_from"] != "commented":\n',
     '        if rv["state"] != "commented" and rv["dismissed_from"] != "commented":\n', ('tests.test_decide.TheFactorysOwnRules.test_a_persons_approval_of_the_current_head_lets_it_converge',)),
    ('an approval a later verdict supersedes still counts', 'kernel/derive.py',
     '    for rv in latest.values():\n        another',
     '    for rv in facts["reviews"]:\n        another', ('tests.test_decide.TheFactorysOwnRules.test_a_persons_approval_of_the_current_head_lets_it_converge',)),
    ("a person's verdicts are read in the order listed", 'kernel/derive.py',
     '    for rv in sorted(facts["reviews"], key=verdict_order):\n        if is_person(rv["by"]) and rv["state"] != "commented"',
     '    for rv in facts["reviews"]:\n        if is_person(rv["by"]) and rv["state"] != "commented"', ('tests.test_decide.TheFactorysOwnRules.test_a_persons_approval_of_the_current_head_lets_it_converge',)),
    ('a later comment supersedes an approval', 'kernel/derive.py',
     'if is_person(rv["by"]) and rv["state"] != "commented" and rv["dismissed_from"]',
     'if is_person(rv["by"]) and rv["dismissed_from"]', ('tests.test_decide.TheFactorysOwnRules.test_a_persons_approval_of_the_current_head_lets_it_converge',)),
    ("a rename out of a model Lens's input is not read", 'kernel/derive.py',
     '    """Each model Lens\'s own input this pull request changes, as the configuration names it, once, in its order: the\n    Role\'s manifest and prompt, its rubric, and what the Harness gives it and takes back (issue 140)."""\n    changed = names(facts["changed_paths"])',
     '    """Each model Lens\'s own input this pull request changes, as the configuration names it, once, in its order: the\n    Role\'s manifest and prompt, its rubric, and what the Harness gives it and takes back (issue 140)."""\n    changed = [e["path"] for e in facts["changed_paths"]]', ('tests.test_decide.TheFactorysOwnRules.test_a_change_to_a_model_lenss_own_input_waits_for_a_person',)),
    ("the author's approval is another judge's", 'kernel/derive.py',
     '        another = rv["by"]["name"] != facts["author"] and rv["by"]["name"] != facts["last_pusher"]\n',
     '        another = rv["by"]["name"] != facts["last_pusher"]\n', ('tests.test_decide.TheFactorysOwnRules.test_a_persons_approval_of_the_current_head_lets_it_converge',)),
    ("the last pusher's approval is another judge's", 'kernel/derive.py',
     '        another = rv["by"]["name"] != facts["author"] and rv["by"]["name"] != facts["last_pusher"]\n',
     '        another = rv["by"]["name"] != facts["author"]\n', ('tests.test_decide.TheFactorysOwnRules.test_a_persons_approval_of_the_current_head_lets_it_converge',)),
    ("a comment or a request for changes is a person's judgment", 'kernel/derive.py',
     '        standing = rv["state"] == "approved" or (rv["dismissed_from"] == "approved" and not is_person(rv["dismissed_by"]))\n',
     '        standing = True\n', ('tests.test_decide.TheFactorysOwnRules.test_a_persons_approval_of_the_current_head_lets_it_converge',)),
    ("a person's dismissal leaves the approval standing", 'kernel/derive.py',
     'or (rv["dismissed_from"] == "approved" and not is_person(rv["dismissed_by"]))\n        if',
     'or rv["dismissed_from"] == "approved"\n        if', ('tests.test_decide.TheFactorysOwnRules.test_a_persons_approval_of_the_current_head_lets_it_converge',)),
    ("an App's dismissal ends a person's approval", 'kernel/derive.py',
     '        standing = rv["state"] == "approved" or (rv["dismissed_from"] == "approved" and not is_person(rv["dismissed_by"]))\n',
     '        standing = rv["state"] == "approved"\n', ('tests.test_decide.TheFactorysOwnRules.test_a_persons_approval_of_the_current_head_lets_it_converge',)),
    ("the model Lens's inputs are any input on the list", 'kernel/derive.py',
     '    return [p for p in dict.fromkeys(config["model_lens_inputs"]) if any(matches(p, path) for path in changed)]\n',
     '    return [p for p in dict.fromkeys(config["protected_paths"]) if any(matches(p, path) for path in changed)]\n', ('tests.test_decide.TheFactorysOwnRules.test_the_list_is_the_configurations_never_the_change',)),
    ("an unreadable list of a model Lens's inputs is read", 'kernel/derive.py',
     'for rules in (config.get("protected_paths"), config.get("model_lens_inputs")))',
     'for rules in (config.get("protected_paths"),))', ('tests.test_decide.TheFactorysOwnRules.test_an_unreadable_list_of_a_model_lenss_inputs_defers_for_the_maintainer',)),
    ("a change to a model Lens's input is nobody's to see", 'kernel/decide.py',
     '    "run_unreadable", "model_lens_input_needs_person",\n',
     '    "run_unreadable",\n', ('tests.test_decide.TheFactorysOwnRules.test_a_change_to_a_model_lenss_own_input_waits_for_a_person',)),
    # A change to a path only a person decides waits under its own code (issue 746, decision 0207).
    ("a change to a person-only path alone is named a model Lens's input", 'kernel/derive.py',
     '        if all(p in alone for p in own):\n',
     '        if False:\n',
     ('tests.test_decide.TheFactorysOwnRules.test_a_change_to_a_path_only_a_person_decides_waits_for_a_person',)),
    ("a change to a model Lens's input beside a person-only path is named for the path", 'kernel/derive.py',
     '        if all(p in alone for p in own):\n',
     '        if any(p in alone for p in own):\n',
     ('tests.test_decide.TheFactorysOwnRules.test_the_wait_is_named_for_a_model_lenss_input_wherever_the_change_touches_one',)),
    ("a change to a model Lens's input is named a person-only path", 'kernel/derive.py',
     '        if all(p in alone for p in own):\n',
     '        if True:\n',
     ('tests.test_decide.TheFactorysOwnRules.test_a_change_to_a_model_lenss_own_input_waits_for_a_person',)),
    ("a person-only path off the model Lenses' list waits for no one", 'kernel/derive.py',
     '    own = own + [p for p in alone if p not in own]\n',
     '    own = own + []\n',
     ('tests.test_decide.TheFactorysOwnRules.test_a_change_to_a_path_only_a_person_decides_waits_for_a_person',)),
    ("a person-only path is named in the evidence before a model Lens's input", 'kernel/derive.py',
     '    own = own + [p for p in alone if p not in own]\n',
     '    own = [p for p in alone if p not in own] + own\n',
     ('tests.test_decide.TheFactorysOwnRules.test_the_wait_is_named_for_a_model_lenss_input_wherever_the_change_touches_one',)),
    ("a person-only path off the model Lenses' list is left out of the evidence beside a Lens's input", 'kernel/derive.py',
     '    own = own + [p for p in alone if p not in own]\n',
     '    own = own or alone\n',
     ('tests.test_decide.TheFactorysOwnRules.test_the_wait_is_named_for_a_model_lenss_input_wherever_the_change_touches_one',)),
    ("a model Lens's input beside a person-only path off its list is dropped, and the change named for the path", 'kernel/derive.py',
     '    own = own + [p for p in alone if p not in own]\n',
     '    own = [p for p in alone if p not in own] or own\n',
     ('tests.test_decide.TheFactorysOwnRules.test_the_wait_is_named_for_a_model_lenss_input_wherever_the_change_touches_one',)),
    ('a rename out of a person-only path is not read', 'kernel/derive.py',
     '    order: no Lens reads one, and a person\'s approval is the only judgement of it (decisions 0200 and 0207)."""\n    changed = names(facts["changed_paths"])\n',
     '    order: no Lens reads one, and a person\'s approval is the only judgement of it (decisions 0200 and 0207)."""\n    changed = [e["path"] for e in facts["changed_paths"]]\n',
     ('tests.test_decide.TheFactorysOwnRules.test_a_change_to_a_path_only_a_person_decides_waits_for_a_person',)),
    ('a person-only path is matched as a whole name, never as a pattern', 'kernel/derive.py',
     '    return [p for p in dict.fromkeys(config["person_only_paths"]) if any(matches(p, path) for path in changed)]\n',
     '    return [p for p in dict.fromkeys(config["person_only_paths"]) if any(p == path for path in changed)]\n',
     ('tests.test_decide.TheFactorysOwnRules.test_a_change_to_a_path_only_a_person_decides_waits_for_a_person',)),
    ('a path on both lists is named in the evidence twice', 'kernel/derive.py',
     '    own = own + [p for p in alone if p not in own]\n',
     '    own = own + alone\n',
     ('tests.test_decide.TheFactorysOwnRules.test_the_wait_is_named_for_a_model_lenss_input_wherever_the_change_touches_one',)),
    ('a person-only path named twice is in the evidence twice', 'kernel/derive.py',
     '    return [p for p in dict.fromkeys(config["person_only_paths"]) if any(matches(p, path) for path in changed)]\n',
     '    return [p for p in config["person_only_paths"] if any(matches(p, path) for path in changed)]\n',
     ('tests.test_decide.TheFactorysOwnRules.test_the_wait_is_named_for_a_model_lenss_input_wherever_the_change_touches_one',)),
    ('every person-only path is taken as changed', 'kernel/derive.py',
     '    return [p for p in dict.fromkeys(config["person_only_paths"]) if any(matches(p, path) for path in changed)]\n',
     '    return [p for p in dict.fromkeys(config["person_only_paths"])]\n',
     ('tests.test_decide.TheFactorysOwnRules.test_the_wait_is_named_for_a_model_lenss_input_wherever_the_change_touches_one',)),
    ('a list of person-only paths that is not there is read as none', 'kernel/derive.py',
     '    persons = config.get("person_only_paths")\n',
     '    persons = config.get("person_only_paths", [])\n',
     ('tests.test_decide.TheFactorysOwnRules.test_an_unreadable_list_of_person_only_paths_defers_for_the_maintainer',)),
    ('a list of person-only paths that is no list is read', 'kernel/derive.py',
     '        and isinstance(persons, list) and all(readable_pattern(p) for p in persons)\n',
     '        and all(readable_pattern(p) for p in persons or [])\n',
     ('tests.test_decide.TheFactorysOwnRules.test_an_unreadable_list_of_person_only_paths_defers_for_the_maintainer',)),
    ('a person-only path of no readable shape is read', 'kernel/derive.py',
     '        and isinstance(persons, list) and all(readable_pattern(p) for p in persons)\n',
     '        and isinstance(persons, list)\n',
     ('tests.test_decide.TheFactorysOwnRules.test_an_unreadable_list_of_person_only_paths_defers_for_the_maintainer',)),
    ('a configuration that names no person-only path cannot be read', 'kernel/derive.py',
     '        and isinstance(persons, list) and all(readable_pattern(p) for p in persons)\n',
     '        and isinstance(persons, list) and len(persons) > 0 and all(readable_pattern(p) for p in persons)\n',
     ('tests.test_decide.TheFactorysOwnRules.test_an_unreadable_list_of_person_only_paths_defers_for_the_maintainer',)),
    ("a change to a person-only path is nobody's to see", 'kernel/decide.py',
     '    "path_needs_person",\n',
     '',
     ('tests.test_decide.TheFactorysOwnRules.test_a_change_to_a_path_only_a_person_decides_waits_for_a_person',)),
    # Issue 749: the fake GitHub starts another run of a Lens on the head, as P-65 recorded, and the Kernel never lets a
    # stopped run pass a Lens a completed failure fails.
    ("the latest run alone is read", 'kernel/derive.py',
     'if not (r is not None and r[1] in t.STOPPED_SUITES and going)]',
     'if r is None or r[0] == max(x[0] for x in runs if x)]', ("tests.test_decide.Content.test_a_cancelled_runs_checks_are_superseded_by_another_run_of_the_lens_on_the_head", "tests.test_simulator.Simulation.test_the_seeds_start_another_run_of_a_lens_on_the_head", "tests.test_simulator.Simulation.test_invariants_hold_under_faults")),
    ("the simulator's stopped run is never passed over", 'kernel/derive.py',
     'and r[1] in t.STOPPED_SUITES and going)]', 'and r[1] in t.STOPPED_SUITES and going and False)]', ("tests.test_simulator.Simulation.test_the_seeds_start_another_run_of_a_lens_on_the_head",)),
    ("every run is passed over beside a run that did not stop", 'kernel/derive.py',
     'if not (r is not None and r[1] in t.STOPPED_SUITES and going)]', 'if not (r is not None and going)]', ("tests.test_simulator.Simulation.test_invariants_hold_under_faults", "tests.test_simulator.Simulation.test_the_seeds_start_another_run_of_a_lens_on_the_head")),
    # Decision 0106: a fault of the Engine or the Factory is never the reviewer's.
    ("the machine user's approval judges a change to a model Lens's input", 'kernel/derive.py',
     '        if is_person(rv["by"]) and rv["state"] != "commented" and rv["dismissed_from"] != "commented":\n',
     '        if (is_person(rv["by"]) or rv["by"]["kind"] == t.MACHINE_USER) and rv["state"] != "commented" and rv["dismissed_from"] != "commented":\n', ('tests.test_decide.TheFactorysOwnRules.test_the_machine_users_approval_never_judges_a_change_to_a_model_lenss_input',)),
    # Decision 0234: an issue's timeline and its linked pull requests' are read to a bound, and past it the issue defers on
    # its own code and calls a person.
    ("a timeline past the port's bound defers as any short one", 'kernel/issue.py',
     '    if bounded is True:\n        return out(None, "timeline_bounded", ["timeline"])\n', '', F849_KERNEL),
    ("a bound flag of any truth is a bound", 'kernel/issue.py',
     '    if bounded is True:\n', '    if bounded:\n', F849_KERNEL),
    ("a bound flag that cannot be read is read as within the bound", 'kernel/issue.py',
     ' or (name == "timeline" and bounded is not False)]', ']', F849_KERNEL),
    ("only a cut of the issue's own timeline is a bound", 'kernel/issue.py',
     '    if bounded is True:\n', '    if bounded is True and "timeline" in unread_lists(facts):\n', F849_KERNEL),
    ("a timeline past the port's bound calls no one", 'kernel/issue.py',
     '    "human_hold",\n    "timeline_bounded",\n', '    "human_hold",\n', F849_KERNEL),
    # Issue 327: a review is given the whole diff or is not asked; one bound, the Kernel's.
    ('a diff one past the bound is reviewed', 'kernel/derive.py',
     '            or not 0 <= characters <= config["limits"]["max_diff_characters"]:\n',
     '            or not 0 <= characters <= config["limits"]["max_diff_characters"] + 1:\n', ('tests.test_decide.Content.test_a_diff_no_task_can_carry_whole_is_held_and_one_at_the_bound_is_reviewed',)),
    ('a diff at the bound is held', 'kernel/derive.py',
     '            or not 0 <= characters <= config["limits"]["max_diff_characters"]:\n',
     '            or not 0 <= characters < config["limits"]["max_diff_characters"]:\n', ('tests.test_decide.Content.test_a_diff_no_task_can_carry_whole_is_held_and_one_at_the_bound_is_reviewed',)),
    ("a length below nothing is read as a count", 'kernel/derive.py',
     '            or not 0 <= characters <= config["limits"]["max_diff_characters"]:\n',
     '            or not characters <= config["limits"]["max_diff_characters"]:\n',
     ('tests.test_decide.Content.test_a_diff_no_task_can_carry_whole_is_held_and_one_at_the_bound_is_reviewed',)),
    ("a diff whose length was not read is reviewed", 'kernel/derive.py',
     '    characters = facts["diff"].get("characters")\n',
     '    characters = facts["diff"].get("characters", 0)\n', ('tests.test_decide.Content.test_a_diff_no_task_can_carry_whole_is_held_and_one_at_the_bound_is_reviewed',)),
    ('a length that is a flag is read as a count', 'kernel/derive.py',
     '    if not isinstance(characters, int) or isinstance(characters, bool) \\\n',
     '    if not isinstance(characters, int) \\\n', ('tests.test_decide.Content.test_a_diff_no_task_can_carry_whole_is_held_and_one_at_the_bound_is_reviewed',)),
    ('a length that is no whole number is read as a count', 'kernel/derive.py',
     '    if not isinstance(characters, int) or isinstance(characters, bool) \\\n',
     '    if not isinstance(characters, (int, float)) or isinstance(characters, bool) \\\n', ('tests.test_decide.Content.test_a_diff_no_task_can_carry_whole_is_held_and_one_at_the_bound_is_reviewed',)),
    # Decision 0216: the author Role's fix is admitted only on a pull request the Factory opened (issue 823).
    ("the author's fix is admitted on anyone's pull request", "kernel/decide.py",
     '        if config["author_role"] is None or not opened_for_an_issue(facts):\n',
     '        if config["author_role"] is None:\n', ("tests.test_decide.Ceilings.test_the_authors_fix_is_admitted_only_on_a_pull_request_the_factory_opened",)),
    ("a fix is admitted on the Factory's pull request with no author Role named", "kernel/decide.py",
     '        if config["author_role"] is None or not opened_for_an_issue(facts):\n',
     '        if not opened_for_an_issue(facts):\n',
     ("tests.test_decide.Ceilings.test_no_author_role_means_nobody_is_admitted_to_fix",)),
    ("issue 0 is an issue the Factory opened a pull request for", "kernel/derive.py",
     "    return type(issue) is int and issue >= 1\n", "    return type(issue) is int and issue >= 0\n", ("tests.test_decide.Ceilings.test_the_authors_fix_is_admitted_only_on_a_pull_request_the_factory_opened",)),
    ("a truth value names the issue a pull request was opened for", "kernel/derive.py",
     "    return type(issue) is int and issue >= 1\n", "    return isinstance(issue, int) and issue >= 1\n", ("tests.test_decide.Ceilings.test_the_authors_fix_is_admitted_only_on_a_pull_request_the_factory_opened",)),
    ("a number with a fraction names the issue a pull request was opened for", "kernel/derive.py",
     "    return type(issue) is int and issue >= 1\n", "    return type(issue) in (int, float) and issue >= 1\n", ("tests.test_decide.Ceilings.test_the_authors_fix_is_admitted_only_on_a_pull_request_the_factory_opened",)),
    ("issue 1 is no issue a pull request was opened for", "kernel/derive.py",
     "    return type(issue) is int and issue >= 1\n", "    return type(issue) is int and issue > 1\n", ("tests.test_decide.Ceilings.test_the_authors_fix_is_admitted_only_on_a_pull_request_the_factory_opened",)),
    ("a number in words names the issue a pull request was opened for", "kernel/derive.py",
     "    return type(issue) is int and issue >= 1\n", "    return type(issue) is str or (type(issue) is int and issue >= 1)\n", ("tests.test_decide.Ceilings.test_the_authors_fix_is_admitted_only_on_a_pull_request_the_factory_opened",)),
    ("whatever the facts hold names the issue a pull request was opened for", "kernel/derive.py",
     "    return type(issue) is int and issue >= 1\n", "    return issue is not None\n", ("tests.test_decide.Ceilings.test_the_authors_fix_is_admitted_only_on_a_pull_request_the_factory_opened",)),
    ("facts that do not say whose a pull request is are read as the Factory's", "kernel/derive.py",
     '    issue = facts.get("opened_for")\n', '    issue = facts.get("opened_for", 1)\n', ("tests.test_decide.Ceilings.test_the_authors_fix_is_admitted_only_on_a_pull_request_the_factory_opened",)),
    ("a review is admitted only on a pull request the Factory opened", "kernel/decide.py",
     '    if state == t.VERIFYING and reason == "awaiting_review":\n',
     '    if state == t.VERIFYING and reason == "awaiting_review" and opened_for_an_issue(facts):\n', ("tests.test_decide.Ceilings.test_the_authors_fix_is_admitted_only_on_a_pull_request_the_factory_opened",)),
    ("an adjudication is admitted only on a pull request the Factory opened", "kernel/decide.py",
     '    if state == t.ADJUDICATING and reason != "resolve_due":\n',
     '    if state == t.ADJUDICATING and reason != "resolve_due" and opened_for_an_issue(facts):\n', ("tests.test_decide.Ceilings.test_the_authors_fix_is_admitted_only_on_a_pull_request_the_factory_opened",)),
    # Issue 366: an external Lens's approval never counts, in the Kernel or toward the Factory's ruleset.
    ("an external Lens's approval stands", 'kernel/derive.py',
     '            rv["by"]["kind"] == t.MACHINE_USER\n', '            rv["by"]["kind"] in (t.MACHINE_USER, "lens", t.APP)\n', ('tests.test_decide.OnlyAPersonEnds.test_an_external_lenss_approval_never_counts',)),
    ("an App with write judges a change to a model Lens's input", 'kernel/derive.py',
     '        if is_person(rv["by"]) and rv["state"] != "commented" and rv["dismissed_from"] != "commented":\n',
     '        if rv["by"]["can_write"] is True and rv["state"] != "commented" and rv["dismissed_from"] != "commented":\n', ('tests.test_decide.OnlyAPersonEnds.test_an_external_lenss_approval_never_counts',)),
    # #193's ruling 6: the status on the item, and what a pass carries for it.
    ('left alone with the timeline not read is not', 'kernel/decide.py',
     'return "timeline" in incomplete(facts) or unreadable_labels',
     'return unreadable_labels', ('tests.test_decide.HumanControl.test_an_item_is_left_alone_for_a_persons_hands_off_or_labels_that_cannot_be_read',)),
    ('left alone with a label event not read is not', 'kernel/decide.py',
     ' or unreadable_labels(facts, config) or hands_off(facts, config)',
     ' or hands_off(facts, config)', ('tests.test_decide.HumanControl.test_an_item_is_left_alone_for_a_persons_hands_off_or_labels_that_cannot_be_read',)),
    ("a person's hands-off leaves nothing alone", 'kernel/decide.py',
     ' or hands_off(facts, config)\n',
     '\n', ('tests.test_decide.HumanControl.test_an_item_is_left_alone_for_a_persons_hands_off_or_labels_that_cannot_be_read',)),
    # Issue 833, decision 0212: a push past a Lens's review, and a thread its later review dropped.
    ('a push past a review asks none while its thread gates', 'kernel/derive.py',
     '\n                or pushed_past_review(mine, facts, lens, config, due)) \\\n', ') \\\n', ('tests.test_decide.OnlyAPersonEnds.test_a_push_after_a_lenss_review_while_its_thread_gates_asks_that_review_again',)),
    ("a review begun in the push's own second answers it", 'kernel/derive.py',
     'and r["started_at"] > facts["last_push_at"]]', 'and r["started_at"] >= facts["last_push_at"]]', ('tests.test_decide.OnlyAPersonEnds.test_a_push_after_a_lenss_review_while_its_thread_gates_asks_that_review_again',)),
    ('a review at no time that can be read answers the push', 'kernel/derive.py',
     'if is_time(r["started_at"]) and r["started_at"] > facts', 'if r["started_at"] > facts', ('tests.test_decide.OnlyAPersonEnds.test_a_push_after_a_lenss_review_while_its_thread_gates_asks_that_review_again',)),
    ('a thread the Kernel is to resolve asks its review again', 'kernel/derive.py',
     ' == role and th["id"] not in due', ' == role', ('tests.test_decide.OnlyAPersonEnds.test_a_push_after_a_lenss_review_while_its_thread_gates_asks_that_review_again',)),
    ('a push at no time that can be read asks a review', 'kernel/derive.py',
     'if not is_time(facts.get("last_push_at")) or not any(', 'if not any(', ('tests.test_decide.OnlyAPersonEnds.test_a_push_after_a_lenss_review_while_its_thread_gates_asks_that_review_again',)),
    ('a thread said dropped is not marked superseded', 'kernel/derive.py',
     '    threads = [dict(th, superseded=True) if dropped_by_review(th, facts, runs) else th for th in threads]\n', '', ('tests.test_decide.OnlyAPersonEnds.test_a_thread_its_lenss_later_review_dropped_is_the_kernels_to_resolve',)),
    ("a security Finding's thread is closed on a review that dropped it", 'kernel/derive.py',
     'known = [c for c in t.CATEGORIES if c != SECURITY]', 'known = list(t.CATEGORIES)', ('tests.test_decide.OnlyAPersonEnds.test_a_thread_its_lenss_later_review_dropped_is_the_kernels_to_resolve',)),
    ('a dropped thread of no category the Kernel knows is closed', 'kernel/derive.py',
     ' or th.get("category") not in known', '', ('tests.test_decide.OnlyAPersonEnds.test_a_thread_its_lenss_later_review_dropped_is_the_kernels_to_resolve',)),
    ('a thread its Lens ruled rejected is dropped by a review', 'kernel/derive.py',
     ' or th.get("ruling") == "rejected"', '', ('tests.test_decide.OnlyAPersonEnds.test_a_thread_its_lenss_later_review_dropped_is_the_kernels_to_resolve',)),
    ('a dropped thread whose opening time cannot be read is borne out', 'kernel/derive.py',
     'or not is_time(th.get("opened_at")) or not is_time(pushed)', 'or not is_time(pushed)', ('tests.test_decide.OnlyAPersonEnds.test_a_thread_its_lenss_later_review_dropped_is_the_kernels_to_resolve',)),
    ('a push at no time that can be read bears a dropped thread out', 'kernel/derive.py',
     ' or not is_time(pushed) or th[', ' or th[', ('tests.test_decide.OnlyAPersonEnds.test_a_thread_its_lenss_later_review_dropped_is_the_kernels_to_resolve',)),
    ('a thread no push followed is dropped by a review', 'kernel/derive.py',
     ' or th["opened_at"] >= pushed \\\n', ' \\\n', ('tests.test_decide.OnlyAPersonEnds.test_a_thread_its_lenss_later_review_dropped_is_the_kernels_to_resolve',)),
    ('a review still running bears a dropped thread out', 'kernel/derive.py',
     'by.get("name") and r.get("intent") == "review-change" and r.get("status") == "completed"\n', 'by.get("name") and r.get("intent") == "review-change"\n', ('tests.test_decide.OnlyAPersonEnds.test_a_thread_its_lenss_later_review_dropped_is_the_kernels_to_resolve',)),
    ('a review at no time that can be read bears a dropped thread out', 'kernel/derive.py',
     'and is_time(r.get("started_at")) and r["started_at"] > pushed', 'and r["started_at"] > pushed', ('tests.test_decide.OnlyAPersonEnds.test_a_thread_its_lenss_later_review_dropped_is_the_kernels_to_resolve',)),
    ('a word of dropped that is no yes or no is read', 'kernel/derive.py',
     '    if "dropped" in th and type(th["dropped"]) is not bool:\n        return True\n', '', ('tests.test_decide.OnlyAPersonEnds.test_a_thread_its_lenss_later_review_dropped_is_the_kernels_to_resolve',)),
    ("a security Finding's thread its Lens accepted is the Kernel's to resolve", 'kernel/derive.py',
     'plain = [th for th in facts["threads"] if th.get("category") != SECURITY]', 'plain = list(facts["threads"])', ('tests.test_decide.OnlyAPersonEnds.test_resolve_thread_never_names_a_thread_still_raised_or_unreadable',)),
    ("another Lens's review bears a dropped thread out", 'kernel/derive.py',
     'return any(r.get("role") == by.get("name") and r.get("intent")', 'return any(r.get("intent")', ('tests.test_decide.OnlyAPersonEnds.test_resolve_thread_never_names_a_thread_still_raised_or_unreadable',)),
    ('a review that failed bears a dropped thread out', 'kernel/derive.py',
     'and r.get("conclusion") == "success" and r.get("content_id") == facts.get("content_id")', 'and r.get("content_id") == facts.get("content_id")', ('tests.test_decide.OnlyAPersonEnds.test_resolve_thread_never_names_a_thread_still_raised_or_unreadable',)),
    # Issue 420: an expired Run's open thread asks its Lens's review, gates, and closes on the queue App's act once superseded.
    ('a mark the facts arrive with is kept', 'kernel/derive.py',
     '    plain = [{k: v for k, v in th.items() if k not in MARKS} if isinstance(th, dict) else th for th in facts["threads"]]',
     '    plain = list(facts["threads"])', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('facts with marks and no expired thread are read as given', 'kernel/derive.py',
     '    if not expired and not marked:\n        return facts\n',
     '    if not expired:\n        return facts\n', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ("an expired thread's marks go by its id", 'kernel/derive.py',
     '    threads = [dict(th, expired=True, superseded=superseded(expired[place])) if place in expired else th\n               for place, th in enumerate(plain)]',
     '    ids = {plain[p].get("id"): p for p in expired}\n    threads = [dict(th, expired=True, superseded=superseded(expired[ids[th.get("id")]])) if isinstance(th, dict) and th.get("id") in ids else th\n               for place, th in enumerate(plain)]', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('an opening time that cannot be read joins a Run', 'kernel/derive.py',
     ' or not is_time(th.get("opened_at")) or not isinstance(th.get("id"), str):',
     ' or not isinstance(th.get("id"), str):', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ("another item's Run opens the thread", 'kernel/derive.py',
     'r.get("item") == facts.get("item") and is_time(r.get("started_at"))]',
     'is_time(r.get("started_at"))]', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ("a re-run's first attempt is read past", 'kernel/derive.py',
     'if before and not rerun and max(',
     'if before and max(', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('a re-run dispatched after the thread is its opener', 'kernel/derive.py',
     '                    and not (is_time(r.get("dispatched_at")) and r["dispatched_at"] > th["opened_at"]) for r in mine)',
     '                    for r in mine)', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('an expired thread resolved by anyone reads past', 'kernel/derive.py',
     '            and not (th.get("expired") is True and (not th["resolved"] or th["resolved_by"]["kind"] == "queue"))\n',
     '            and th.get("expired") is not True\n', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ("an expired Run's thread is read as any other", 'kernel/derive.py',
     '    facts = as_read(facts, runs, config)\n    d = reading(facts, runs, config, ())',
     '    d = reading(facts, runs, config, ())', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('a list of expired Runs that cannot be read names threads', 'kernel/derive.py',
     '    if not readable_expired(facts) or not isinstance(facts.get("threads"), list) or not isinstance(runs, list):\n        return {}',
     '    if not isinstance(facts.get("threads"), list) or not isinstance(runs, list):\n        return {}', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('a Lens that is not required has expired threads', 'kernel/derive.py',
     ' or by.get("name") not in required:\n            continue',
     ':\n            continue', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('a thread with a category is an expired one', 'kernel/derive.py',
     '        if th.get("category") is not None or th.get("severity") is not None',
     '        if th.get("severity") is not None', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('a thread with a severity is an expired one', 'kernel/derive.py',
     '        if th.get("category") is not None or th.get("severity") is not None or th.get("ruling") is not None',
     '        if th.get("category") is not None or th.get("ruling") is not None', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('a thread with a ruling is an expired one', 'kernel/derive.py',
     ' or th.get("ruling") is not None \\\n                or "ruling" not in th',
     ' \\\n                or "ruling" not in th', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ("a thread opened as its Run starts is not that Run's", 'kernel/derive.py',
     'r["role"] == by["name"] and r["started_at"] <= th["opened_at"]]',
     'r["role"] == by["name"] and r["started_at"] < th["opened_at"]]', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('any Run of the Lens before the thread is its opener', 'kernel/derive.py',
     'if before and not rerun and max(before, key=lambda r: r["started_at"])["run"] in facts["expired_reviews"]:',
     'if before and not rerun and any(r["run"] in facts["expired_reviews"] for r in before):', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ("another Lens's Run opens the thread", 'kernel/derive.py',
     'before = [r for r in mine if r["role"] == by["name"] and r["started_at"]',
     'before = [r for r in mine if r["started_at"]', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('an expired thread is never superseded', 'kernel/derive.py',
     'dict(th, expired=True, superseded=superseded(expired[place]))',
     'dict(th, expired=True, superseded=False)', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('an expired thread is superseded at once', 'kernel/derive.py',
     'dict(th, expired=True, superseded=superseded(expired[place]))',
     'dict(th, expired=True, superseded=True)', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('a failed review supersedes', 'kernel/derive.py',
     ' and r.get("status") == "completed"\n                   and r.get("conclusion") == "success"',
     '\n                  ', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('an earlier review supersedes', 'kernel/derive.py',
     ' and r["started_at"] > opener["started_at"]\n',
     ' and r["started_at"] >= opener["started_at"]\n', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ("another Lens's review supersedes an expired thread", 'kernel/derive.py',
     'return any(r.get("role") == opener["role"] and r.get("intent") == "review-change"',
     'return any(r.get("intent") == "review-change"', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('an adjudication supersedes an expired thread', 'kernel/derive.py',
     'return any(r.get("role") == opener["role"] and r.get("intent") == "review-change"',
     'return any(r.get("role") == opener["role"]', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ("another item's review supersedes", 'kernel/derive.py',
     '\n                   and r.get("item") == facts.get("item") for r in runs',
     '\n                   for r in runs', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ("an expired thread's missing category is unreadable", 'kernel/derive.py',
     '            and not (th.get("expired") is True and (not th["resolved"] or th["resolved_by"]["kind"] == "queue"))\n',
     '\n', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('a superseded thread is no act', 'kernel/derive.py',
     '           and (th["ruling"] == "accepted" or th.get("superseded") is True)]',
     '           and th["ruling"] == "accepted"]', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ("the queue's resolution of a superseded thread closes nothing", 'kernel/gate.py',
     '(by["kind"] == "queue" and (th["ruling"] == "accepted" or th.get("superseded") is True))',
     '(by["kind"] == "queue" and th["ruling"] == "accepted")', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ("any App's resolution of a superseded thread closes it", 'kernel/gate.py',
     '(by["kind"] == "queue" and (th["ruling"] == "accepted" or th.get("superseded") is True))',
     '(th["ruling"] == "accepted" and by["kind"] == "queue") or th.get("superseded") is True', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    ('an expired thread gates as what it says', 'kernel/gate.py',
     ' or th["severity"] in GATING_SEVERITIES or th.get("expired") is True):',
     ' or th["severity"] in GATING_SEVERITIES):', ('tests.test_decide.OnlyAPersonEnds.test_an_expired_runs_open_thread_asks_its_review_and_is_resolved_after_it',)),
    # Issue 381: the queue App's grant, and each resolution it lands counted as an act.
    ("a resolution in the writer's own second is no act", 'kernel/derive.py',
     '    return [r for r in runs if r["started_at"] >= mark]\n\n\ndef in_progress',
     '    return [r for r in runs if r["started_at"] > mark]\n\n\ndef in_progress', ('tests.test_decide.Ceilings.test_each_landed_resolution_counts_toward_the_act_ceiling',)),
    ('a resolution that keeps failing is decided again', 'kernel/brakes.py',
     '    run_acts = {"issue_approval": t.ISSUE_APPROVAL, "resolve_thread": t.RESOLVE_THREAD}',
     '    run_acts = {"issue_approval": t.ISSUE_APPROVAL}', ('tests.test_decide.Ceilings.test_each_landed_resolution_counts_toward_the_act_ceiling',)),
    ("a resolution's attempts are an approval's", 'kernel/brakes.py',
     '    run_acts = {"issue_approval": t.ISSUE_APPROVAL, "resolve_thread": t.RESOLVE_THREAD}',
     '    run_acts = {"issue_approval": t.ISSUE_APPROVAL, "resolve_thread": t.ISSUE_APPROVAL}', ('tests.test_decide.Ceilings.test_each_landed_resolution_counts_toward_the_act_ceiling',)),
    ('a landed resolution is no act', 'kernel/brakes.py',
     'if readable and acts + _landed(acted) >= limits["max_acts_per_item"]:',
     'if readable and acts >= limits["max_acts_per_item"]:', ('tests.test_decide.Ceilings.test_each_landed_resolution_counts_toward_the_act_ceiling',)),
    ('any Run that landed is a resolution', 'kernel/brakes.py',
     'return sum(1 for r in since if r["intent"] == t.RESOLVE_THREAD and r["status"] == "completed"',
     'return sum(1 for r in since if r["status"] == "completed"', ('tests.test_decide.Ceilings.test_each_landed_resolution_counts_toward_the_act_ceiling',)),
    ('a resolution that did not land counts as an act', 'kernel/brakes.py',
     '\n               and r["conclusion"] == "success")',
     '\n               )', ('tests.test_decide.Ceilings.test_each_landed_resolution_counts_toward_the_act_ceiling',)),
    ('a landed resolution spends a Run', 'kernel/brakes.py',
     't.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.ENQUEUE_MERGE, t.DEQUEUE_MERGE)\n                                      and r["conclusion"] == "success")',
     't.ISSUE_APPROVAL, t.ENQUEUE_MERGE, t.DEQUEUE_MERGE)\n                                      and r["conclusion"] == "success")', ('tests.test_decide.Ceilings.test_each_landed_resolution_counts_toward_the_act_ceiling',)),
    # Issue 381, the queue step's first part: each queue act a dispatched Run of the queue workflow once it is named.
    ("an enqueue's attempts are reached one late", 'kernel/brakes.py',
     '    failed = _attempts(since, t.ENQUEUE_MERGE)\n    if len(failed) >= limits["max_attempts"]:',
     '    failed = _attempts(since, t.ENQUEUE_MERGE)\n    if len(failed) > limits["max_attempts"]:', ('tests.test_decide.Ceilings.test_a_queue_job_spends_no_run_when_it_lands_and_is_held_by_its_own_when_it_does_not',)),
    ("an enqueue's Run ceiling is reached one late", 'kernel/brakes.py',
     'and r["conclusion"] != "success"]\n    if len(unlanded) >= limits["max_runs_per_item"]:\n        return _decision(facts, t.HELD, "run_ceiling", [], t.HOLD)\n    return None\n\n\ndef dequeue_ceiling',
     'and r["conclusion"] != "success"]\n    if len(unlanded) > limits["max_runs_per_item"]:\n        return _decision(facts, t.HELD, "run_ceiling", [], t.HOLD)\n    return None\n\n\ndef dequeue_ceiling', ('tests.test_decide.Ceilings.test_a_queue_job_spends_no_run_when_it_lands_and_is_held_by_its_own_when_it_does_not',)),
    ("a dequeue's Run ceiling is reached one late", 'kernel/brakes.py',
     '    unlanded = [r for r in since if r["intent"] == t.DEQUEUE_MERGE and r["status"] == "completed" and r["conclusion"] != "success"]\n    if len(unlanded) >= limits["max_runs_per_item"]:',
     '    unlanded = [r for r in since if r["intent"] == t.DEQUEUE_MERGE and r["status"] == "completed" and r["conclusion"] != "success"]\n    if len(unlanded) > limits["max_runs_per_item"]:', ('tests.test_decide.Ceilings.test_a_queue_job_spends_no_run_when_it_lands_and_is_held_by_its_own_when_it_does_not',)),
    ('a dequeue is sent again beside its own in flight', 'kernel/decide.py',
     '        if any(r["intent"] == t.DEQUEUE_MERGE for r in in_progress(mine)):\n            return _decision(facts, state, reason, evidence, t.NOTHING)\n',
     '', ('tests.test_decide.Ceilings.test_a_queue_job_spends_no_run_when_it_lands_and_is_held_by_its_own_when_it_does_not',)),
    ('another Run in flight holds a dequeue', 'kernel/decide.py',
     '        if any(r["intent"] == t.DEQUEUE_MERGE for r in in_progress(mine)):',
     '        if in_progress(mine):', ('tests.test_decide.Ceilings.test_a_queue_job_spends_no_run_when_it_lands_and_is_held_by_its_own_when_it_does_not',)),
    ('a dequeue that keeps failing is sent for ever', 'kernel/decide.py',
     '        held = brakes.dequeue_ceiling(_decision, facts, since_writer(mine, facts), config["limits"])\n        if held:\n            return held\n',
     '', ('tests.test_decide.Ceilings.test_a_queue_job_spends_no_run_when_it_lands_and_is_held_by_its_own_when_it_does_not',)),
    ('other Runs spent hold a dequeue', 'kernel/brakes.py',
     'unlanded = [r for r in since if r["intent"] == t.DEQUEUE_MERGE and r["status"] == "completed"',
     'unlanded = [r for r in since if r["status"] == "completed"', ('tests.test_decide.Ceilings.test_a_queue_job_spends_no_run_when_it_lands_and_is_held_by_its_own_when_it_does_not',)),
    ('a landed enqueue spends a Run', 'kernel/brakes.py',
     't.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.ENQUEUE_MERGE, t.DEQUEUE_MERGE)\n                                      and r["conclusion"] == "success")',
     't.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.DEQUEUE_MERGE)\n                                      and r["conclusion"] == "success")', ('tests.test_decide.Ceilings.test_a_queue_job_spends_no_run_when_it_lands_and_is_held_by_its_own_when_it_does_not',)),
    ('a landed dequeue spends a Run', 'kernel/brakes.py',
     't.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.ENQUEUE_MERGE, t.DEQUEUE_MERGE)\n                                      and r["conclusion"] == "success")',
     't.ISSUE_APPROVAL, t.RESOLVE_THREAD, t.ENQUEUE_MERGE)\n                                      and r["conclusion"] == "success")', ('tests.test_decide.Ceilings.test_a_queue_job_spends_no_run_when_it_lands_and_is_held_by_its_own_when_it_does_not',)),
    ('an enqueue that keeps failing is decided again', 'kernel/brakes.py',
     '    if action == "enqueue":\n        held = enqueue_ceilings(',
     '    if False:\n        held = enqueue_ceilings(', ('tests.test_decide.Ceilings.test_a_queue_job_spends_no_run_when_it_lands_and_is_held_by_its_own_when_it_does_not',)),
    ("an enqueue's attempts are unbounded", 'kernel/brakes.py',
     '    failed = _attempts(since, t.ENQUEUE_MERGE)\n    if len(failed) >= limits["max_attempts"]:',
     '    failed = _attempts(since, t.ENQUEUE_MERGE)\n    if False:', ('tests.test_decide.Ceilings.test_a_queue_job_spends_no_run_when_it_lands_and_is_held_by_its_own_when_it_does_not',)),
    ('an enqueue failing for the environment is unbounded', 'kernel/brakes.py',
     'and r["conclusion"] != "success"]\n    if len(unlanded) >= limits["max_runs_per_item"]:\n        return _decision(facts, t.HELD, "run_ceiling", [], t.HOLD)\n    return None\n\n\ndef dequeue_ceiling',
     'and r["conclusion"] != "success"]\n    if False:\n        return _decision(facts, t.HELD, "run_ceiling", [], t.HOLD)\n    return None\n\n\ndef dequeue_ceiling', ('tests.test_decide.Ceilings.test_a_queue_job_spends_no_run_when_it_lands_and_is_held_by_its_own_when_it_does_not',)),
    ('other Runs spent hold an enqueue', 'kernel/brakes.py',
     'unlanded = [r for r in since if r["intent"] == t.ENQUEUE_MERGE and r["status"] == "completed"',
     'unlanded = [r for r in since if r["status"] == "completed"', ('tests.test_decide.Ceilings.test_a_queue_job_spends_no_run_when_it_lands_and_is_held_by_its_own_when_it_does_not',)),
    # Issue 195: a machine user's approval is measured from the act's Run that read the description, not its landing.
    ("an act's approval is anchored at the approval", 'kernel/derive.py',
     '    if acts:\n        return max(acts)\n', '    if False:\n        return max(acts)\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("an act on other content anchors an approval", 'kernel/derive.py',
     '    mine = [r for r in runs if r["intent"] == t.ISSUE_APPROVAL and r["content_id"] == review["content_id"]]\n',
     '    mine = [r for r in runs if r["intent"] == t.ISSUE_APPROVAL]\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("an act begun after the approval anchors it", 'kernel/derive.py',
     '    acts = [made_at(r) for r in mine if made_at(r) <= at]\n',
     '    acts = [made_at(r) for r in mine]\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("any Run on the content is the act that read it", 'kernel/derive.py',
     '    mine = [r for r in runs if r["intent"] == t.ISSUE_APPROVAL and r["content_id"] == review["content_id"]]\n',
     '    mine = [r for r in runs if r["content_id"] == review["content_id"]]\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("the first act made before an approval anchors it", 'kernel/derive.py',
     '    if acts:\n        return max(acts)\n', '    if acts:\n        return min(acts)\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a re-run's start times the act", 'kernel/derive.py',
     '    times = [when for when in (run.get("dispatched_at"), run["started_at"]) if is_time(when)]\n',
     '    times = [run["started_at"]]\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a re-run act with no dispatch read is not unknown", 'kernel/derive.py',
     '    if any(made_at(r) > at and not is_time(r.get("dispatched_at")) and "rerun_by_dispatcher" in r for r in mine):\n',
     '    if False:\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a first attempt with no dispatch read is taken for a re-run", 'kernel/derive.py',
     '    if any(made_at(r) > at and not is_time(r.get("dispatched_at")) and "rerun_by_dispatcher" in r for r in mine):\n',
     '    if any(made_at(r) > at and not is_time(r.get("dispatched_at")) for r in mine):\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a malformed dispatch is a time", 'kernel/derive.py',
     '    times = [when for when in (run.get("dispatched_at"), run["started_at"]) if is_time(when)]\n',
     '    times = [when for when in (run.get("dispatched_at"), run["started_at"]) if when]\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a record whose time cannot be read anchors an approval", 'kernel/derive.py',
     '    if any(made_at(r) is None or not is_time(r["started_at"]) for r in runs):\n        return ""\n', '    if False:\n        return ""\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a record whose start is no time beside a dispatch anchors an approval", 'kernel/derive.py',
     '    if any(made_at(r) is None or not is_time(r["started_at"]) for r in runs):\n',
     '    if any(made_at(r) is None for r in runs):\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a record that waited in its lane reaches back by its start", 'kernel/derive.py',
     '    return at if any(is_time(r.get("began_at")) and made_at(r) <= r["began_at"] <= at for r in runs) else ""\n',
     '    return at if any(r["started_at"] <= at for r in runs) else ""\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a record said to have begun before it was made reaches back", 'kernel/derive.py',
     'any(is_time(r.get("began_at")) and made_at(r) <= r["began_at"] <= at for r in runs)',
     'any(is_time(r.get("began_at")) and r["began_at"] <= at for r in runs)', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a record that began in the second it was made does not reach back", 'kernel/derive.py',
     'any(is_time(r.get("began_at")) and made_at(r) <= r["began_at"] <= at for r in runs)',
     'any(is_time(r.get("began_at")) and made_at(r) < r["began_at"] <= at for r in runs)', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a record whose jobs were not read reaches back by its start", 'kernel/derive.py',
     'any(is_time(r.get("began_at")) and made_at(r) <= r["began_at"] <= at for r in runs)',
     'any(is_time(r.get("began_at", r["started_at"])) and made_at(r) <= r.get("began_at", r["started_at"]) <= at for r in runs)', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a beginning that is no time reaches back", 'kernel/derive.py',
     'any(is_time(r.get("began_at")) and made_at(r) <= r["began_at"] <= at for r in runs)',
     'any(isinstance(r.get("began_at"), str) and made_at(r) <= r["began_at"] <= at for r in runs)', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a re-run's first beginning before its last start does not reach back", 'kernel/derive.py',
     'any(is_time(r.get("began_at")) and made_at(r) <= r["began_at"] <= at for r in runs)',
     'any(is_time(r.get("began_at")) and r["started_at"] <= r["began_at"] <= at for r in runs)', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a record that began after the approval reaches back by its start", 'kernel/derive.py',
     'any(is_time(r.get("began_at")) and made_at(r) <= r["began_at"] <= at for r in runs)',
     'any(is_time(r.get("began_at")) and made_at(r) <= r["began_at"] and r["started_at"] <= at for r in runs)', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a record that never began reaches back by its start", 'kernel/derive.py',
     'any(is_time(r.get("began_at")) and made_at(r) <= r["began_at"] <= at for r in runs)',
     'any("began_at" in r and is_time(r["began_at"] or r["started_at"]) and made_at(r) <= (r["began_at"] or r["started_at"]) <= at for r in runs)', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a record dispatched during an act reaches back", 'kernel/derive.py',
     '    return at if any(is_time(r.get("began_at")) and made_at(r) <= r["began_at"] <= at for r in runs) else ""\n',
     '    return at if any(made_at(r) <= at for r in runs) else ""\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a browser's approval is unanchored", 'kernel/derive.py',
     '    return at if any(is_time(r.get("began_at")) and made_at(r) <= r["began_at"] <= at for r in runs) else ""\n', '    return ""\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("an approval with no record as old as it is the browser's", 'kernel/derive.py',
     '    return at if any(is_time(r.get("began_at")) and made_at(r) <= r["began_at"] <= at for r in runs) else ""\n', '    return at\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a record in the approval's second does not reach back", 'kernel/derive.py',
     '    return at if any(is_time(r.get("began_at")) and made_at(r) <= r["began_at"] <= at for r in runs) else ""\n',
     '    return at if any(is_time(r.get("began_at")) and made_at(r) <= r["began_at"] < at for r in runs) else ""\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("another item's records reach back before an approval", 'kernel/derive.py',
     '        mine = runs_on(runs, facts)\n', '        mine = runs\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("derive reads the description's anchor without the records", 'kernel/derive.py',
     '    anchor = description_anchor(facts, edited, runs=runs) if edited is not None else None\n',
     '    anchor = description_anchor(facts, edited, runs=[]) if edited is not None else None\n', ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    # The owed Muse reads of issues 608 and 626's changes: a Run in the approval's own second, the records always given,
    # and the plan's heads placed by heads_place.
    ("the description's anchor takes no records by default", 'kernel/derive.py',
     'def description_anchor(facts: dict, edited: str, *, runs: list):', 'def description_anchor(facts: dict, edited: str, *, runs: list = ()):',
     ('tests.test_decide.Convergence.test_an_approval_is_anchored_at_the_act_that_read_the_description',)),
    ("a broken chain defers as any short list", 'kernel/issue.py',
     '    if facts.get("spans_broken") is True:\n        return out(None, "spans_broken", ["linked"])\n', '', F849_BROKEN + F849_SAID),
    ("a break defers only beside a linked list read short", 'kernel/issue.py',
     'if facts.get("spans_broken") is True:', 'if facts.get("spans_broken") is True and facts["complete"]["linked"] is False:', F849_BROKEN),
    ("a break flag of any truth is a break", 'kernel/issue.py',
     'if facts.get("spans_broken") is True:', 'if facts.get("spans_broken"):', F849_BROKEN),
    ("a broken chain calls no one", 'kernel/issue.py',
     '    "timeline_bounded",\n    "spans_broken",\n', '    "timeline_bounded",\n', F849_BROKEN + F849_SAID),
    ("a broken chain is read before a cut read", 'kernel/issue.py',
     '    if bounded is True:\n        return out(None, "timeline_bounded", ["timeline"])\n', '    if bounded is True and facts.get("spans_broken") is not True:\n        return out(None, "timeline_bounded", ["timeline"])\n', F849_BROKEN),
    ("a cut acceptance read calls no one", 'kernel/decide.py',
     '"acceptance_unreadable", "acceptance_bounded", "paths_unreadable"', '"acceptance_unreadable", "paths_unreadable"', ('tests.test_decide.Acceptance.test_an_acceptance_read_cut_at_its_bound_defers_on_its_own_code_and_calls_a_person',)),
    ("a cut acceptance read defers as any read short", 'kernel/derive.py',
     '    if facts.get("acceptance_bounded") is True:\n        return {"state": None, "reason": "acceptance_bounded", "evidence": ["acceptance"]}\n', '', ('tests.test_decide.Acceptance.test_an_acceptance_read_cut_at_its_bound_defers_on_its_own_code_and_calls_a_person',)),
    ("a cut acceptance read is read after the lists read short", 'kernel/derive.py',
     '    if facts.get("acceptance_bounded") is True:\n        return {"state": None, "reason": "acceptance_bounded", "evidence": ["acceptance"]}\n    gaps = incomplete(facts)\n', '    gaps = incomplete(facts)\n    if not [g for g in gaps if g != "acceptance"] and facts.get("acceptance_bounded") is True:\n        return {"state": None, "reason": "acceptance_bounded", "evidence": ["acceptance"]}\n', ('tests.test_decide.Acceptance.test_an_acceptance_read_cut_at_its_bound_defers_on_its_own_code_and_calls_a_person',)),
    ("a cut acceptance read names no evidence", 'kernel/derive.py',
     '"reason": "acceptance_bounded", "evidence": ["acceptance"]}', '"reason": "acceptance_bounded", "evidence": []}', ('tests.test_decide.Acceptance.test_an_acceptance_read_cut_at_its_bound_defers_on_its_own_code_and_calls_a_person',)),
    ("any truthy flag is a cut acceptance read", 'kernel/derive.py',
     'if facts.get("acceptance_bounded") is True:', 'if facts.get("acceptance_bounded"):', ('tests.test_decide.Acceptance.test_an_acceptance_read_cut_at_its_bound_defers_on_its_own_code_and_calls_a_person',)),
    ("a cut flag that is no truth value is read as not cut", 'kernel/derive.py',
     '    if facts.get("acceptance_bounded", False) is not False and "acceptance" not in gaps:\n        gaps = ["acceptance"] + gaps\n', '', ('tests.test_decide.Acceptance.test_an_acceptance_read_cut_at_its_bound_defers_on_its_own_code_and_calls_a_person',)),
    ("an absent cut flag is a gap", 'kernel/derive.py',
     'if facts.get("acceptance_bounded", False) is not False', 'if facts.get("acceptance_bounded") is not False', ('tests.test_decide.Acceptance.test_an_acceptance_read_cut_at_its_bound_defers_on_its_own_code_and_calls_a_person',)),
    ("a cut flag that is no truth value and falsy is read as not cut", 'kernel/derive.py',
     'if facts.get("acceptance_bounded", False) is not False and', 'if facts.get("acceptance_bounded", False) and', ('tests.test_decide.Acceptance.test_an_acceptance_read_cut_at_its_bound_defers_on_its_own_code_and_calls_a_person',)),
]


# The classes a mutant may not name whole, nor the module that holds one: each takes long enough, whole and beside the
# other workers, to run past TIMEOUT and fail a shard for its length alone, which ejected a pull request from the queue
# at random, and more often as they grow. A mutant names the method that kills it. A class that grows slow joins them.
WHOLE_TOO_LONG = ("tests.test_tools.Trials", "tests.test_tools.Workflows", "tests.test_tools.Apps",
                  "tests.test_tools.AppThreads", "tests.test_tools.Verify", "tests.test_simulator.Simulation",
                  "tests.test_transitions.Transitions")
WORKERS = 4        # runs at once, at most, unless told: each is a whole run of the suite, in a copy of its own
TIMEOUT = 600      # seconds for one run of the suite. A run that takes longer is an ERROR, never a kill
# The baseline, the run of the unbroken tests before anything is broken, runs the tests the run's own mutants name,
# method by method, shared among its workers, each part one run held to TIMEOUT, never the whole suite, which outgrew
# TIMEOUT on a CI runner (issue 396). A shard runs a disjoint share of what every shard's mutants name, so that its
# baseline shrinks as shards are added (issue 398).
# The whole suite, which an edit tools/untested.py tries runs once the tests it names pass, runs in parts of at most PART_MOST tests dealt in
# turn, one after another, each one run held to TIMEOUT, so that no run grows with the suite (issue 398). On a loaded
# desk, where the suite took 940 s, its 1,311 tests made 14 parts of 9 to 124 s.
# A run filtered by path, `python3 -m tools.mutants PATH...`, is the one local run allowed (the Maintainer, 2026-10-19,
# issue 217): it breaks at most FILTER_MOST mutants, FILTER_WORKERS at a time, and never a shard.
PART_MOST = 100    # test methods in one run of the whole suite, at most
FILTER_MOST = 40
FILTER_WORKERS = 2
# What unittest prints last when a test failed or raised. Without it, the run broke some other way.
FAILED = re.compile(r"^FAILED \((?:failures|errors)=", re.M)
# unittest's stand-in for a test module that would not import: the copy is broken, not the rule.
UNIMPORTABLE = "unittest.loader._FailedTest"
# How every ERROR's reason ends. An ERROR says nothing of the rule, so the run is mended and made again.
AGAIN = "; fix the copy or run named here, then run python3 -m tools.mutants again"
# The line unittest prints under its rule of = for the test that failed or raised: its method, then its class in 3.10
# and earlier or its whole id from 3.11, then any subtest. A failure in setUpClass names the class. The rule above
# tells it from a line of the same form in a test's own message.
FAILURE_LINE = re.compile(r"^={70}\n(?:FAIL|ERROR): (\w+) \(([\w.]+)\)(?: .*)?$", re.M)
NAMED_MOST = 20     # the tests a failing baseline names, so that its log stays readable
NAMED_WIDTH = 200   # the characters of each
NAMED_SCAN = 200    # the lines after a failure's head its error is looked for in
# Said of a failure not shown to be the mutant's: one more run of the suite on the mutant decides.
UNCONFIRMED = "unconfirmed"
# Why a mutant the tests it names pass on is an ERROR: the whole suite does not run to find the test that kills it.
NOT_KILLED = "named_test_does_not_kill: %s passed on it; name the test that fails on it" + AGAIN
# How a FLAKY's reason ends. FLAKY fails the run as an ERROR does: nobody has shown that a test notices the mutant.
MEND = "; mark or mend that test, then run python3 -m tools.mutants again"


def suite(cwd: pathlib.Path, timeout: float = TIMEOUT, first: tuple = (), only=None) -> tuple:
    """Run the tests in `cwd` to the first failure: (exit status, output), the status None if it timed out.

    The tests named in `first` run on their own before the rest: when they pass, or none is named, the whole suite
    runs, so a mutant they miss is still read by every test. The one test, or class, named in `only` runs alone, or
    each of a tuple of them and no other.
    """
    if only:
        return _unittest(cwd, timeout, ["-q", "-f", *((only,) if isinstance(only, str) else only)])
    if first:
        status, output = _unittest(cwd, timeout, ["-q", "-f", *first])
        if status != 0:
            return status, output
    # Every module, named from the top so that a test's id is its dotted path, as `first` and `only` name it, the slow
    # ones last (issue 217), in parts, the next run only when the last passed (issue 398).
    status, output = 0, ""
    for part in whole_suite(cwd):
        status, output = _unittest(cwd, timeout, ["-q", "-f", *part])
        if status != 0:
            break
    return status, output


def whole_suite(cwd: pathlib.Path) -> list:
    """The whole suite in `cwd` as the runs it is made in: its test methods, as `cases` reads them there, dealt in turn
    into as few parts as hold at most PART_MOST each, each in the order `modules` gives, so that no run of the whole
    suite grows with it and its slow tests, which stand together, are spread among the parts. A module that cannot be
    read method by method is a part of its own, after them (issue 398)."""
    names = tuple(modules(cwd))
    tests = cases(names, cwd)
    methods = tuple(test for test in tests if test not in names)
    count = -(-len(methods) // PART_MOST)
    return [methods[at::count] for at in range(count)] + [(name,) for name in tests if name in names]


def modules(cwd: pathlib.Path) -> list:
    """Every test module under `cwd`'s tests/, `test*.py` as discovery finds them, a package nested in it included, as
    the dotted names unittest runs them by, in the order the suite runs: the modules tools/verify.py names in SLOW, and test_hooks, after all the others, so
    that a mutant the tests it names miss is still read by every test, the quick ones first. The modules are read from
    the tree by tools/walk.py, never listed here, so a new one is never left out (issue 217)."""
    names = sorted(".".join(path.relative_to(cwd).with_suffix("").parts) for path in walk.files(cwd)
                   if path.relative_to(cwd).parts[0] == "tests" and path.name.startswith("test") and path.suffix == ".py")
    slow = set("tests." + name for name in SLOW) | {"tests.test_hooks"}
    return [name for name in names if name not in slow] + [name for name in names if name in slow]


def unnamed(mutants: list, root: pathlib.Path = ROOT) -> list:
    """Why each mutant in `mutants` cannot be run: it names no test, or a test it names does not exist. Every mutant
    names the tests that kill it, as its fifth part, each the dotted name of a test module, class or method that
    exists, so that a kill is confirmed in seconds and a misspelt name is never an ERROR in CI (issue 217), and none of
    them a class in WHOLE_TOO_LONG or the module that holds it."""
    problems = []
    missing_of = _missing_apart([test for mutant in mutants for test in (mutant[4] if len(mutant) > 4 else ())], root)
    for mutant in mutants:
        name, tests = mutant[0], mutant[4] if len(mutant) > 4 else ()
        if not tests:
            problems.append("%r names no test; name the tests that kill it" % name)
        for test in tests:
            if any(whole == test or whole.startswith(test + ".") for whole in WHOLE_TOO_LONG):
                problems.append("%r names %s, which holds a class too slow to name whole beside the other workers; name "
                                "the method that kills it" % (name, test))
            missing = missing_of[test]
            if missing:
                problems.append("%r names %s, %s" % (name, test, missing))
    return problems


NAMING = """import json, sys
from tools.mutants import _missing
print(json.dumps({name: _missing(name) for name in json.loads(sys.stdin.read())}))
"""


def _missing_apart(tests: list, root: pathlib.Path = ROOT) -> dict:
    """`_missing` of each dotted name in `tests`, read in a process of its own in `root`: a test module's import runs
    there and never in the runner's, where a module that patched the runner could say a mutant it survived was killed
    (issue 511). A name the other process does not answer for is one that cannot be read."""
    names = sorted({test for test in tests if isinstance(test, str)})
    found = {}
    if names:
        try:
            said = subprocess.run([sys.executable, "-c", NAMING], cwd=str(root), input=json.dumps(names),
                                  capture_output=True, text=True, timeout=TIMEOUT)
            found = json.loads(said.stdout.strip().splitlines()[-1]) if said.stdout.strip() else {}
        except (OSError, ValueError, subprocess.TimeoutExpired):
            found = {}
    return {test: found[test] if isinstance(found.get(test), str) else "which could not be read" for test in names}


def _case(found) -> bool:
    """Whether `found` is a TestCase defined in a module under tests/."""
    return isinstance(found, type) and issubclass(found, unittest.TestCase) and found.__module__.startswith("tests.")


def _missing(test: str) -> str:
    """Why the dotted name `test` is not a test module under tests/, a TestCase in one, or a test method of one: ""
    where it is one of those."""
    parts = test.split(".")
    if parts[0] != "tests" or len(parts) < 2 or not all(parts):
        return "which is not a test module under tests/"
    for split in range(len(parts), 1, -1):
        try:
            found = importlib.import_module(".".join(parts[:split]))
        except (ImportError, ValueError, TypeError):
            continue
        break
    else:
        return "whose module does not exist"
    if not parts[split - 1].startswith("test"):      # the module found, below any package: test*.py, as modules() lists
        return "which is not a test module under tests/"
    rest, holder = parts[split:], None
    for part in rest:
        if not hasattr(found, part):
            return "which does not exist"
        found, holder = getattr(found, part), found
    if not rest:
        return ""
    if isinstance(found, type):
        return "" if _case(found) else "which is not a TestCase of a test module"
    if not _case(holder):
        return "which is not a method of a TestCase"
    return "" if callable(found) and rest[-1].startswith("test") else "which is not a test method"


def _unittest(cwd: pathlib.Path, timeout: float, args: list) -> tuple:
    """(exit status, output) of one run of unittest in `cwd`, the status None if it timed out."""
    env = dict(os.environ, SIM_SEEDS="40", MUTATING="1")
    with subprocess.Popen([sys.executable, "-m", "unittest"] + args, cwd=str(cwd),
                          env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          start_new_session=True) as run:
        try:
            out, _ = run.communicate(timeout=timeout)
            return run.returncode, out.decode(errors="replace")
        except subprocess.TimeoutExpired:
            # Its children go too, so that none is left holding the output open.
            os.killpg(run.pid, signal.SIGKILL)
            out, _ = run.communicate()
            return None, out.decode(errors="replace")


def verdict(status, output: str) -> tuple:
    """What a run of the suite says of its mutant: ("killed", "SURVIVED" or "ERROR", and why)."""
    if status is None:
        return "ERROR", "the run took longer than %d s%s" % (TIMEOUT, AGAIN)
    if status == 0:
        return "SURVIVED", ""
    if status == 1 and FAILED.search(output) and UNIMPORTABLE not in output:
        return "killed", ""
    last = next((line.strip() for line in reversed(output.splitlines()) if line.strip()), "no output")
    return "ERROR", "exit status %d and no test failed, ending %r%s" % (status, last, AGAIN)


def _test_id(method: str, where: str) -> str:
    """A failed test's id as unittest takes it, from the two forms the Python versions print."""
    return where if method == "setUpClass" or where.endswith("." + method) else where + "." + method


def failed_test(output: str):
    """The id of the one test that failed in `output`, as unittest takes it to run that test alone; else None."""
    found = {_test_id(method, where) for method, where in FAILURE_LINE.findall(output)}
    return found.pop() if len(found) == 1 else None


def failures(outputs: list) -> list:
    """Each test that failed in `outputs`, once, with the first line of its error, for a person to read in a log: at
    most NAMED_MOST of them, each cut to NAMED_WIDTH characters, and a last line saying how many more (issue 438)."""
    named = {}
    for output in outputs:
        for found in FAILURE_LINE.finditer(output):
            lines = output[found.end():].split("\n", NAMED_SCAN)[:NAMED_SCAN]
            error = ""
            # Past the rule, which a test's docstring may stand before, and the traceback, whose lines stand in, the first
            # line that stands out.
            for line in lines[lines.index("-" * 70) + 1:] if "-" * 70 in lines else []:
                if line.startswith("=" * 70):
                    break
                if line and line[0] != " " and not line.startswith("Traceback"):
                    error = line
                    break
            named.setdefault(_test_id(*found.groups()), error)
    said = ["%s: %s" % (test, error) if error else test for test, error in named.items()]
    return [line[:NAMED_WIDTH] for line in said[:NAMED_MOST]] + \
        (["and %d more" % (len(said) - NAMED_MOST)] if len(said) > NAMED_MOST else [])


def confirm(output: str, work: pathlib.Path, run, broken, unbroken) -> tuple:
    """Is the failure in `output` the mutant's? ("killed", ""), (UNCONFIRMED, why) or ("ERROR", why).

    The test that failed runs alone twice more in `work`: on the mutant, where it must fail again, and, once `unbroken`
    has put the file back, on the unbroken code, where it must pass; `broken` then breaks it again. Only both tell a
    failure the mutant causes from one already broken and from one caused by load, and both are in the same copy, so
    a test that fails in any copy, with no .git or under the system's temporary directory, fails on both.
    """
    test = failed_test(output)
    if test is None:
        return "ERROR", "the one test that failed cannot be read from the output%s" % AGAIN
    again = verdict(*run(work, only=test))
    unbroken()
    if again[0] == "ERROR":
        return again
    before = verdict(*run(work, only=test))
    broken()
    if before[0] == "ERROR":
        return before
    if again[0] == "killed" and before[0] == "SURVIVED":
        return "killed", ""
    if before[0] != "SURVIVED":
        return UNCONFIRMED, "%s failed on the unbroken code too%s" % (test, MEND)
    return UNCONFIRMED, "%s passed when run again on the mutant%s" % (test, MEND)


class Broken(RuntimeError):
    """A worker's copy no longer holds what the tree does: it is never lent again."""


class Trees:
    """The copies of `root` the workers run in: one made for each worker, and lent to one mutant at a time.

    A copy is made once, not for every mutant: hundreds of copies wrote hundreds of gigabytes in an afternoon.
    """

    def __init__(self, root: pathlib.Path, where: str):
        self.root, self.where, self.free = root, where, []

    @contextlib.contextmanager
    def lent(self):
        try:
            work = self.free.pop()      # one step, so no two workers are lent one copy
        except IndexError:
            work = pathlib.Path(tempfile.mkdtemp(dir=self.where)) / "repo"
            walk.copy(self.root, work)
        kept = True
        try:
            yield work
        except Broken:
            kept = False
            raise
        finally:
            if kept:
                self.free.append(work)


# Each mutant's text is given its own time, past the file's own, so that Python never takes the bytecode it compiled
# from one mutant, or from the unbroken file, for another of the same size.
STAMPS = iter(range(1, 2 ** 31))     # next() on it is one step, whichever worker asks


def attempt(mutant: tuple, root: pathlib.Path, run, trees: Trees = None, alone: bool = False) -> tuple:
    """Break one rule in a worker's copy of `root` and run the tests there: (outcome, why).

    A failure kills the mutant only once `confirm` shows it is the mutant's. One that is not runs the suite once more
    on the mutant: a pass is SURVIVED, and a second failure that is not the mutant's is FLAKY. However the runs end,
    the file's own bytes are written back and read again before the copy is lent to another mutant. `alone`, as the
    mutant run gives it, holds a mutant to the tests it names: a pass of them is an ERROR, NOT_KILLED, and the whole
    suite never runs after them; tools/untested.py's edits run it after their tests, as a mutant naming none does.
    """
    if trees is None:
        with tempfile.TemporaryDirectory() as where:
            return attempt(mutant, root, run, Trees(root, where), alone)
    name, rel, old, new, *first = mutant
    with trees.lent() as work:
        target = work / rel
        try:
            original = target.read_bytes()
        except OSError as err:
            raise Broken("%s could not be read in this copy: %s" % (rel, err)) from None
        if original != (root / rel).read_bytes():
            raise Broken("%s in this copy is not the tree's: a mutant before this one left it changed" % rel)
        text = original.decode()
        if text.count(old) != 1:
            return "STALE", "the code it mutates has changed"
        mutated, stamp = text.replace(old, new).encode(), os.stat(str(target)).st_mtime_ns

        def put(data: bytes, at: int) -> None:
            try:
                target.write_bytes(data)
                os.utime(str(target), ns=(at, at))
                same = target.read_bytes() == data
            except OSError as err:
                raise Broken("%s could not be written in this copy: %s" % (rel, err)) from None
            if not same:
                raise Broken("%s in this copy does not read back as written" % rel)

        def broken() -> None:
            put(mutated, stamp + next(STAMPS) * 10 ** 9)

        def unbroken() -> None:
            put(original, stamp)
        broken()
        try:
            # A mutant a decision's Boundary row names is held to the tests it lists, alone: one any other test kills
            # would let the row's test look like the one that notices the break (issue 590).
            named = ({"only": first[0]} if name in _held_by_rows(root) else {"first": first[0]}) if first else {}
            # A mutant the tests it names miss ran the whole suite after them, 10 to 21 minutes of a 27-minute leg, and
            # hid the wrong name (2026-11-09): run alone, it is told as an ERROR instead.
            if alone and first:
                named = {"only": first[0]}
            for again in range(2):
                status, output = run(work, **named)
                outcome, why = verdict(status, output)
                # A pass after a failure not shown to be the mutant's is a flaky test, not a wrong name.
                if outcome == "SURVIVED" and alone and first and not again:
                    return "ERROR", NOT_KILLED % ", ".join(first[0])
                if outcome != "killed":
                    return outcome, why
                outcome, why = confirm(output, work, run, broken, unbroken)
                if outcome != UNCONFIRMED:
                    return outcome, why
            return "FLAKY", why
        finally:
            unbroken()


def _held_by_rows(root: pathlib.Path) -> set:
    """The mutants the decision records in `root` name, read once for each root."""
    key = str(root)
    if key not in _ROWS:
        from tools import check_decisions
        _ROWS[key] = check_decisions.held_by_rows(root)
    return _ROWS[key]


_ROWS = {}


def guarded(mutant: tuple, root: pathlib.Path, run, trees: Trees = None) -> tuple:
    """`attempt`, with anything it raises made an ERROR for this mutant, so that the others still report."""
    try:
        return attempt(mutant, root, run, trees, alone=True)
    except Exception as err:    # a failed copy, read or run; never a kill
        return "ERROR", "the run failed with %s: %s%s" % (type(err).__name__, err, AGAIN)


def shard(mutants: list, index: int, count: int) -> list:
    """The mutants whose place in `mutants` is `index` modulo `count`: one of `count` shards, which hold each once."""
    return [mutant for place, mutant in enumerate(mutants) if place % count == index]


def selected(environ, paths: list = (), mutants: list = None) -> tuple:
    """(the mutants this run breaks, the words its summary ends with, how many run at once or None for the default,
    and a shard's share of the baseline for `shared`, or None for a run with no shard), read from MUTANTS_SHARD and
    MUTANTS_SHARDS, or from `paths`, the targets a filtered run is given.

    CI sets both from the matrix, the shard counted from 0. Neither set and no path: every mutant, as a run at a desk.
    With paths, the mutants whose target is one of them, at most FILTER_MOST of them, FILTER_WORKERS at a time, and no
    shard (issue 217). Raises ValueError for one of the pair without the other, a value that is not a whole number, a
    shard outside the count, a shard that holds no mutant, which cannot be told from a list that is broken, a path
    no mutant targets, more than FILTER_MOST mutants, a shard beside a filter, or a mutant that names no test or a
    test that does not exist.
    """
    mutants = MUTANTS if mutants is None else mutants
    problems = unnamed(mutants)
    if problems:
        raise ValueError("\n".join(problems + ["%d mutant(s) name no test, or one that does not exist" % len(problems)]))
    index, count = environ.get("MUTANTS_SHARD"), environ.get("MUTANTS_SHARDS")
    if paths:
        if index is not None or count is not None:
            raise ValueError("MUTANTS_SHARD and a path filter do not mix; unset the shard, or give no path")
        wanted = {re.sub(r"^(\./)+", "", str(pathlib.PurePosixPath(path))) for path in paths}
        untargeted = sorted(wanted - {mutant[1] for mutant in mutants})
        if untargeted:      # a path no mutant targets: a misspelt one, or one with no rule to break
            raise ValueError("no mutant targets %s" % ", ".join(untargeted))
        chosen = [mutant for mutant in mutants if mutant[1] in wanted]
        if len(chosen) > FILTER_MOST:
            raise ValueError("%d mutants target %s; a filtered run breaks at most %d: give fewer paths"
                             % (len(chosen), ", ".join(sorted(wanted)), FILTER_MOST))
        return chosen, ", of %s" % ", ".join(sorted(wanted)), FILTER_WORKERS, None
    if index is None and count is None:
        return mutants, "", None, None
    if not all(isinstance(said, str) and re.fullmatch(r"[0-9]+", said) for said in (index, count)):
        raise ValueError("MUTANTS_SHARD is %r and MUTANTS_SHARDS is %r; set both, to whole numbers, or neither"
                         % (index, count))
    index, count = int(index), int(count)
    if not 0 <= index < count:
        raise ValueError("MUTANTS_SHARD is %d and MUTANTS_SHARDS is %d; the shard is counted from 0, below the count"
                         % (index, count))
    chosen = shard(mutants, index, count)
    if not chosen:
        raise ValueError("shard %d of %d holds no mutant" % (index, count))
    return chosen, ", in shard %d of %d counted from 0" % (index, count), None, (mutants, index, count)


def named(mutants: list) -> tuple:
    """The tests `mutants` name, each once, sorted: what the baseline runs (issue 396)."""
    return tuple(sorted({test for mutant in mutants for test in (mutant[4] if len(mutant) > 4 else ())}))


# Read in a child, in the tree the baseline runs in, by unittest's own loader: the ids of the test methods each name
# holds, an empty list for one that holds none, and null for one it cannot read, or one that holds a test that is not
# a method of a TestCase by its own id, as a doctest a load_tests adds is: such a name runs only whole (issue 398).
LISTING = """import json, sys, unittest
def flat(s):
    return [c for i in s for c in flat(i)] if isinstance(s, unittest.TestSuite) else [s]
def method(c):
    kind = type(c)
    return isinstance(c, unittest.TestCase) and c.id() == "%s.%s.%s" % (kind.__module__, kind.__qualname__,
                                                                      getattr(c, "_testMethodName", ""))
said = []
for name in json.loads(sys.stdin.read()):
    try:
        found = flat(unittest.defaultTestLoader.loadTestsFromName(name))
        said.append([c.id() for c in found] if all(method(c) for c in found) else None)
    except Exception:
        said.append(None)
print(json.dumps(said))
"""


def cases(tests: tuple, root: pathlib.Path) -> tuple:
    """Each test method the dotted names in `tests` hold, as unittest's loader reads them in `root`, in their order,
    each once, so that a class or module named whole is shared among the baseline's parts and does not hold one of
    them. A name read as no test, or as any id that is not a test under tests/, is kept whole, for its own run to
    find; and every name is, where the tree cannot be read at all (issue 396)."""
    return read_cases(tests, root)[0]


def read_cases(tests: tuple, root: pathlib.Path) -> tuple:
    """(`cases`, and whether every name was read method by method: False where any is kept whole)."""
    try:
        listed = subprocess.run([sys.executable, "-c", LISTING], cwd=str(root), input=json.dumps(list(tests)),
                                capture_output=True, text=True, timeout=TIMEOUT,
                                env=dict(os.environ, SIM_SEEDS="40", MUTATING="1"))
        said = json.loads(listed.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        said = None
    if not isinstance(said, list) or len(said) != len(tests):
        return tuple(dict.fromkeys(tests)), False
    found, read = [], True
    for name, ids in zip(tests, said):
        # A module that holds no test, as one of shared helpers, is read as none: nothing of it runs, alone or whole.
        whole = isinstance(ids, list) and all(isinstance(i, str) and i.startswith("tests.") for i in ids)
        found.extend(ids if whole else [name])
        read = read and whole
    return tuple(dict.fromkeys(found)), read


def baseline(mutants: list, root: pathlib.Path, run, workers: int, share: tuple = None) -> list:
    """(exit status, output) of each run of the unbroken tests before anything is broken: the tests `mutants` name,
    method by method, in `workers` parts run at once, so that the baseline is shared among the run's workers and is
    never one run of the whole suite (issue 396). A list that names no test runs the whole suite, once. A shard runs
    its `share` of what every mutant names, which may hold no test, instead (issue 398)."""
    tests = shared(share, root)
    if tests is None:
        tests = cases(named(mutants), root)
        if not tests:
            return [run(root)]
    parts = [tests[at::workers] for at in range(min(workers, len(tests)))]
    if not parts:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(parts)) as pool:
        return list(pool.map(lambda part: run(root, only=part), parts))


def shared(share: tuple, root: pathlib.Path):
    """A shard's share of the baseline, given `share`, (every mutant of the run, the shard, the count of shards): of
    the tests every mutant names, method by method as `cases` reads them in `root`, each `count`-th from the shard's
    place, so that across the shards each runs once, whichever shard's mutants name it, and a shard's share shrinks as
    shards are added (issue 398). Where any name cannot be read method by method, one shard's list cannot be told to
    be another's, so the shard runs all of them, each read as far as it can be, and no named test is left in no
    share. None with no share, and for mutants that name no test."""
    if share is None:
        return None
    every, index, count = share
    tests, read = read_cases(named(every), root)
    if not tests:
        return None
    return tests[index::count] if read else tests


def main(mutants: list = None, root: pathlib.Path = ROOT, run=suite, workers: int = None, where: str = "",
         share: tuple = None) -> int:
    mutants = MUTANTS if mutants is None else mutants
    workers = workers or min(os.cpu_count() or 1, WORKERS)
    runs = baseline(mutants, root, run, workers, share)
    # A test that fails is told first, since it is a fault whatever else is slow, a part that ran out of time after
    # one failed among them; a part that only ran out of time failed no test that ran, and says so, so that a slow
    # baseline is never read as a red one.
    for status, output in runs:
        outcome, why = verdict(status, output)
        if (status is not None and outcome != "SURVIVED") or (status is None and FAILURE_LINE.search(output)):
            print("the tests fail before anything is broken; a mutant cannot be told from that%s"
                  % (" (%s)" % why if why else ""))
            # Each part stops at its first failure, so there may be more than these.
            for line in failures([said for _, said in runs]):
                print("    " + line)
            return 1
    if any(status is None for status, _ in runs):
        print("the tests the mutants name took longer than %d s before anything was broken, and none that ran failed; no "
              "mutant can be run in that time: name narrower tests in the mutants, or run more workers, then run "
              "python3 -m tools.mutants again" % TIMEOUT)
        return 1
    killed = 0
    # One run to a CPU, and no more than WORKERS: each holds a copy of the tree and runs the suite in it. map() hands
    # the results back in the order of `mutants`, however the runs finish.
    with tempfile.TemporaryDirectory() as made, \
            concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        trees = Trees(root, made)
        results = pool.map(lambda mutant: guarded(mutant, root, run, trees), mutants)
        for mutant, (outcome, why) in zip(mutants, results):
            print("%-9s %s%s" % (outcome, mutant[0], " (%s)" % why if why else ""), flush=True)
            killed += outcome == "killed"
    print("%d of %d mutants killed%s" % (killed, len(mutants), where))
    return 0 if killed == len(mutants) else 1


# On a pull request the shards decline and pass: on 2026-11-09 they were 77% of the runner minutes, about three quarters
# of them on pull requests, and in 94 pull-request runs they caught what the tests did not in 3, and 49 ran on a baseline
# already red. The merge group runs every shard in full, and a builder still owes the desk run. The event is the runner's
# own GITHUB_EVENT_NAME: the shard job's env is held to MUTANTS_SHARD and MUTANTS_SHARDS alone (tools/check_workflows.py).
DECLINED = "pull_request"


def front(environ, paths: list, run=suite, root: pathlib.Path = ROOT, mutants: list = None) -> int:
    """`python3 -m tools.mutants [PATH...]`: the run `selected` reads from `environ` and `paths`, as `main` runs it; on a
    pull request, nothing, and it passes."""
    if environ.get("GITHUB_EVENT_NAME") == DECLINED:
        print("the mutants decline on a pull request and pass: the merge group runs every shard, and the desk run is "
              "the builder's")
        return 0
    try:
        chosen, where, at_once, share = selected(environ, paths, mutants)
    except ValueError as err:
        print(err)
        return 1
    return main(chosen, root, run, workers=at_once, where=where, share=share)


if __name__ == "__main__":
    sys.exit(front(os.environ, sys.argv[1:]))
