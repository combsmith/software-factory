"""Can the tests fail? Break the Kernel on purpose, one rule at a time, and see.

Each mutant removes or inverts one rule. A mutant that the tests do not catch
is a rule nothing is checking. Run with `python3 -m tools.mutants`.
"""
from __future__ import annotations

import concurrent.futures
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile

from tools import walk

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
REVIEW_WAIT = '            return {"state": t.VERIFYING, "reason": "awaiting_review", "evidence": [lens]}\n'
STAYS = '    if d["reason"] == "approved":\n'
LEFT_ALONE = '    if d["state"] in t.TERMINAL or not facts["queue"] or hands_off(facts, config):\n'
DEQUEUE_IF = '    if d.get("dequeue"):\n'
DEQUEUE = ('        return _decision(facts, state, reason, evidence, t.ACT, action="dequeue",'
           ' content_id=facts["content_id"])\n')

MUTANTS = [
    ("incomplete facts are trusted", "kernel/derive.py",
     "    gaps = incomplete(facts)\n", "    gaps = []\n"),
    ("a list of Runs read short is trusted", "kernel/derive.py",
     "[name for name in t.READ_IN_FULL if flags.get(name) is not True]",
     '[name for name in t.READ_IN_FULL if name != "runs" and flags.get(name) is not True]'),
    ("a timeline read short is trusted", "kernel/derive.py",
     "[name for name in t.READ_IN_FULL if flags.get(name) is not True]",
     '[name for name in t.READ_IN_FULL if name != "timeline" and flags.get(name) is not True]'),
    ("a flag that is not exactly true counts as whole", "kernel/derive.py",
     "if flags.get(name) is not True]", "if not flags.get(name, True)]"),
    ("incomplete facts are read before a merged or closed item", "kernel/derive.py",
     '    if facts["state"] == "merged":\n',
     "    if incomplete(facts):\n"
     '        return {"state": None, "reason": "facts_incomplete", "evidence": incomplete(facts)}\n'
     '    if facts["state"] == "merged":\n'),
    ("model review before the checks pass", "kernel/derive.py",
     '    if waiting and "awaiting_checks" not in past:\n', "    if False:\n"),
    ("a failed check is ignored", "kernel/derive.py",
     "    if failed:\n", "    if False:\n"),
    ("a stranger's thread gates", "kernel/derive.py",
     "        if is_person(by):\n", '        if by["kind"] == "human":\n'),
    ("a stranger is a person", "kernel/derive.py",
     'actor.get("kind") == "human" and actor.get("can_write") is True', 'actor.get("kind") == "human"'),
    ("an App with write access is a person", "kernel/derive.py",
     'actor.get("kind") == "human" and actor.get("can_write") is True', 'actor.get("can_write") is True'),
    ("a thread is closed by whoever resolves it", "kernel/derive.py",
     "        if closed(th):\n", '        if th["resolved"]:\n'),
    ("a person's thread resolved by anyone closes", "kernel/derive.py",
     '        return is_person(by) and by["name"] == opener["name"]\n', "        return True\n"),
    ("a person's thread resolved by another writer closes", "kernel/derive.py",
     '        return is_person(by) and by["name"] == opener["name"]\n', "        return is_person(by)\n"),
    ("a Lens's thread resolved by anyone closes", "kernel/derive.py",
     '        return is_person(by) or (by["kind"] == "lens" and by["name"] == opener["name"])\n', "        return True\n"),
    ("a Lens's thread resolved by another Lens closes", "kernel/derive.py",
     'or (by["kind"] == "lens" and by["name"] == opener["name"])', 'or by["kind"] == "lens"'),
    ("a person cannot close a Lens's thread", "kernel/derive.py",
     'return is_person(by) or (by["kind"] == "lens"', 'return (by["kind"] == "lens"'),
    ("a thread's opener is not read", "kernel/derive.py",
     'if not readable_actor(th.get("opened_by"), facts, config) or ', "if "),
    ("whether a thread is resolved is read loosely", "kernel/derive.py",
     ' or type(th.get("resolved")) is not bool:', ":"),
    ("who resolved a thread is not read", "kernel/derive.py",
     '    if th["resolved"] and not readable_actor(th.get("resolved_by"), facts, config):\n        return True\n', ""),
    ("an open thread that names who resolved it is trusted", "kernel/derive.py",
     '    if not th["resolved"] and th.get("resolved_by") is not None:\n        return True\n', ""),
    ("a required Lens's thread resolved by another App is not read", "kernel/derive.py",
     'return (not closed(th) and th["opened_by"]', 'return (not th["resolved"] and th["opened_by"]'),
    ("a minor finding gates", "kernel/derive.py",
     'th["severity"] in t.GATING_SEVERITIES', "True"),
    ("a null category on a required Lens's thread is read as not security", "kernel/derive.py",
     'th.get("category") not in t.CATEGORIES', 'th.get("category") not in t.CATEGORIES + (None,)'),
    ("a null severity is readable", "kernel/derive.py",
     'th.get("severity") not in t.SEVERITIES', 'th.get("severity") not in t.SEVERITIES + (None,)'),
    ("a category outside the enum is read", "kernel/derive.py",
     'th.get("category") not in t.CATEGORIES', 'th.get("category") is None'),
    ("a thread from a Lens that is not required must be readable", "kernel/derive.py",
     'th["opened_by"]["kind"] == "lens" and th["opened_by"]["name"] in lenses\n',
     'th["opened_by"]["kind"] == "lens"\n'),
    ("a model Lens's unreadable thread is read on a dependency update", "kernel/derive.py",
     '    lenses = config["required_lenses"]["model"]\n', "    lenses = required_model_lenses(facts, config)\n"),
    ("an unreadable thread is read after a model review is admitted", "kernel/derive.py",
     *moved_after("kernel/derive.py", THREAD_GUARD, REVIEW_WAIT)),
    ("an unreadable thread is not the Maintainer's to see", "kernel/decide.py",
     '"review_unreadable", "thread_unreadable",', '"review_unreadable",'),
    ("a security finding gates by its severity", "kernel/derive.py",
     'th["category"] == t.SECURITY or ', ""),
    ("a security finding from a lens that is not required gates", "kernel/derive.py",
     'by["name"] in required and (', '(by["name"] in required or th["category"] == t.SECURITY) and ('),
    ("an empty diff converges", "kernel/derive.py",
     'if facts["diff"]["files"] == 0:', "if False:"),
    ("admission survives a push", "kernel/derive.py",
     'return placed["at"] > facts["last_push_at"]', "return True"),
    ("an admission anyone placed admits", "kernel/derive.py",
     '    if placed is None or not is_person(placed["by"]):\n', "    if placed is None:\n"),
    ("an unreadable label event is trusted", "kernel/derive.py", LABEL_GUARD, ""),
    ("an unreadable label event is read after a Hold", "kernel/derive.py",
     *moved_after("kernel/derive.py", LABEL_GUARD,
                  '        return {"state": t.HELD, "reason": "human_hold", "evidence": stops}\n')),
    ("an unreadable label event is not the Maintainer's to see", "kernel/decide.py",
     '"thread_unreadable", "label_unreadable",', '"thread_unreadable",'),
    ("an event whose label cannot be read is passed over", "kernel/derive.py",
     '        if not isinstance(ev, dict) or not isinstance(ev.get("label"), str):\n            return True\n',
     '        if not isinstance(ev, dict) or not isinstance(ev.get("label"), str):\n            continue\n'),
    ("what was done to a label is not read", "kernel/derive.py",
     '        if ev.get("action") not in t.LABEL_ACTIONS:\n            return True\n', ""),
    ("when a label event happened is not read", "kernel/derive.py",
     '        if not is_time(ev.get("at")):\n            return True\n', ""),
    ("who added or removed a label is not read", "kernel/derive.py",
     '        if not readable_actor(ev.get("by"), facts, config):\n            return True\n', ""),
    ("a label anyone removes is released", "kernel/derive.py",
     '        elif is_person(ev["by"]):\n', "        else:\n"),
    ("label events are read in the order given", "kernel/derive.py",
     'sorted([ev for ev in facts["label_events"] if ev["label"] in t.CONTROL_LABELS], key=label_order)',
     '[ev for ev in facts["label_events"] if ev["label"] in t.CONTROL_LABELS]'),
    ("in the same second a label event is read in the order given", "kernel/derive.py",
     '    return ev["at"], ev["action"] == "labeled"\n', '    return ev["at"], False\n'),
    ("anyone placing a label again replaces a person's placement", "kernel/derive.py",
     '            if not (ev["label"] in out and is_person(out[ev["label"]]["by"]) and not is_person(ev["by"])):\n',
     "            if True:\n"),
    ("hands-off is read from a timeline read short", "kernel/derive.py",
     '    if "timeline" in incomplete(facts) or unreadable_labels(facts, config):\n',
     "    if unreadable_labels(facts, config):\n"),
    ("a person named like an App's bot is read", "kernel/derive.py",
     '    if actor["kind"] == "human" and actor["name"].endswith(t.BOT_SUFFIX):\n        return False\n', ""),
    ("the machine user's approval stands without write access", "kernel/derive.py",
     '            and rv["by"]["can_write"] is True\n', ""),
    ("hands-off anyone placed binds as hands-off", "kernel/derive.py",
     '    return placed is not None and is_person(placed["by"])\n', "    return placed is not None\n"),
    ("hands-off anyone else placed is ignored", "kernel/derive.py",
     STOPS, STOPS.replace("(t.LABEL_HOLD, t.LABEL_HANDS_OFF)", "(t.LABEL_HOLD,)")),
    ("hands-off with an unreadable event leaves a queued item alone", "kernel/derive.py",
     '    if "timeline" in incomplete(facts) or unreadable_labels(facts, config):\n',
     '    if "timeline" in incomplete(facts):\n'),
    # Not the old line, `rv["by"]["name"] == config["approver"]`: readable_actor holds that name to the machine user
    # and the machine user to it, so put back it would be an equivalent mutant, which no test can notice.
    ("an approval by anyone stands", "kernel/derive.py",
     '            rv["by"]["kind"] == t.MACHINE_USER\n', '            rv["by"]["kind"] in t.ACTOR_KINDS\n'),
    ("the approver read as a person is trusted", "kernel/derive.py",
     '(actor["kind"] == t.MACHINE_USER) != (actor["name"] == config["approver"])',
     'actor["kind"] == t.MACHINE_USER and actor["name"] != config["approver"]'),
    ("another name read as the machine user is trusted", "kernel/derive.py",
     '(actor["kind"] == t.MACHINE_USER) != (actor["name"] == config["approver"])',
     'actor["name"] == config["approver"] and actor["kind"] != t.MACHINE_USER'),
    ("an author bot read as a person is trusted", "kernel/derive.py",
     '    return not (facts["class"] in t.BOT_CLASSES and actor["name"] == facts["author"] and actor["kind"] != t.APP)\n',
     "    return True\n"),
    ("the author of a maintainer's pull request must be an App", "kernel/derive.py",
     'return not (facts["class"] in t.BOT_CLASSES and actor["name"]', 'return not (actor["name"]'),
    ("an approval of other content stands", "kernel/derive.py",
     'and rv["content_id"] == facts["content_id"]\n        ):', "):"),
    ("a review of other content counts", "kernel/derive.py",
     '        and r["content_id"] == facts["content_id"]\n        and r["status"] == "completed"',
     '        and r["status"] == "completed"'),
    ("the hold label is ignored", "kernel/derive.py",
     STOPS, STOPS.replace("(t.LABEL_HOLD, t.LABEL_HANDS_OFF)", "(t.LABEL_HANDS_OFF,)")),
    ("an unknown merge state is read as mergeable", "kernel/derive.py",
     '    if mergeable is not True and "mergeable_unreadable" not in past:\n', "    if False:\n"),
    ("only a null merge state is unknown", "kernel/derive.py",
     'if mergeable is not True and', "if mergeable is None and"),
    ("a conflict is not sent back to the author", "kernel/derive.py",
     "    if mergeable is False:\n", "    if False:\n"),
    ("the merge state is read before a merged, closed, held, draft or queued item", "kernel/derive.py",
     '    if facts["state"] == "merged":\n',
     '    if facts.get("mergeable") is not True and facts.get("mergeable") is not False:\n'
     '        return {"state": None, "reason": "mergeable_unreadable", "evidence": []}\n'
     '    if facts["state"] == "merged":\n'),
    ("a dependency update waits for a model review", "kernel/derive.py",
     "    for lens in required_model_lenses(facts, config):\n",
     '    for lens in config["required_lenses"]["model"]:\n'),
    ("a model Lens's thread does not gate a dependency update", "kernel/derive.py",
     '    required = set(config["required_lenses"]["model"])\n',
     "    required = set(required_model_lenses(facts, config))\n"),
    ("a neutral check is read as passing", "config/defaults.json",
     '"neutral": "unreadable"', '"neutral": "passing"'),
    ("a neutral check is read as failing", "config/defaults.json",
     '"neutral": "unreadable"', '"neutral": "failing"'),
    ("a timed-out check is read as no verdict", "config/defaults.json",
     '"timed_out": "failing"', '"timed_out": "unreadable"'),
    ("a running check is read as passing", "config/defaults.json",
     '"in_progress": "pending"', '"in_progress": "passing"'),
    ("a conclusion the map does not name is read as passing", "kernel/derive.py",
     'config["check_conclusions"].get(check["conclusion"], "unreadable")',
     'config["check_conclusions"].get(check["conclusion"], "passing")'),
    ("a reading the Kernel does not know is trusted", "kernel/derive.py",
     '    if readings - {"passing", "pending"}:\n', '    if "unreadable" in readings:\n'),
    ("an absent required check passes", "kernel/derive.py",
     '    if not mine:\n        return "pending"\n', '    if not mine:\n        return "passing"\n'),
    ("another App's check is read for a Lens", "kernel/derive.py",
     ' and type(app) is int and type(lens["app_id"]) is int and app == lens["app_id"]\n', "\n"),
    ("an App id in the facts that is not a whole number is read", "kernel/derive.py",
     ' and type(app) is int and type(lens["app_id"]) is int and', ' and type(lens["app_id"]) is int and'),
    ("an App id in the configuration that is not a whole number is read", "kernel/derive.py",
     ' and type(app) is int and type(lens["app_id"]) is int and', " and type(app) is int and"),
    ("a check is matched to a Lens by the Lens's own name", "kernel/derive.py",
     '    return check.get("name") == lens["check"]\n',
     '    return check.get("name") in (lens["check"], lens["lens"])\n'),
    ("a check's name is matched in any case and with space around it", "kernel/derive.py",
     '    return check.get("name") == lens["check"]\n',
     '    return str(check.get("name")).strip().casefold() == lens["check"].casefold()\n'),
    ("a check from another App is passed over", "kernel/derive.py",
     "    if foreign:\n", "    if False:\n"),
    ("another App's check is read after the failures of every Lens", "kernel/derive.py",
     *moved_after("kernel/derive.py",
                  '    foreign = foreign_checks(facts["checks"], config)\n    if foreign:\n'
                  '        return {"state": t.VERIFYING, "reason": "check_unreadable", "evidence": foreign}\n',
                  '        return {"state": t.ADDRESSING, "reason": "check_failed", "evidence": failed}\n')),
    ("another App's check is read after a conflict", "kernel/derive.py",
     *moved_after("kernel/derive.py",
                  '    foreign = foreign_checks(facts["checks"], config)\n    if foreign:\n'
                  '        return {"state": t.VERIFYING, "reason": "check_unreadable", "evidence": foreign}\n',
                  '        return {"state": t.ADDRESSING, "reason": "conflict", "evidence": []}\n')),
    ("another App's check is shown as its Lens alone", "kernel/derive.py",
     '                said = "%s:from_app:%s" % (lens["lens"], app if type(app) is int else "unreadable")\n',
     '                said = lens["lens"]\n'),
    ("an App id that is no whole number is shown as it is", "kernel/derive.py",
     'app if type(app) is int else "unreadable")', "app)"),
    ("the last check with a Lens's name wins", "kernel/derive.py",
     "    readings = {check_reading(c, config) for c in mine}\n",
     "    readings = {check_reading(c, config) for c in mine[-1:]}\n"),
    ("the first check with a Lens's name wins", "kernel/derive.py",
     "    readings = {check_reading(c, config) for c in mine}\n",
     "    readings = {check_reading(c, config) for c in mine[:1]}\n"),
    ("a failing check among passing ones is ignored", "kernel/derive.py",
     '    if "failing" in readings:\n', '    if readings == {"failing"}:\n'),
    ("a check with no verdict among passing ones is ignored", "kernel/derive.py",
     '    if readings - {"passing", "pending"}:\n', '    if not readings & {"passing", "pending"}:\n'),
    ("a running check among passing ones passes", "kernel/derive.py",
     '    if "pending" in readings:\n', '    if readings == {"pending"}:\n'),
    ("a check with no verdict is read before a failing one of the same Lens", "kernel/derive.py",
     '    if "failing" in readings:\n',
     '    if "failing" in readings and not readings - {"passing", "pending", "failing"}:\n'),
    ("the status on the item may carry a Lens's name", "tools/check_authority.py",
     '    if _folded(c["status_on_item"]) in {_folded(name) for name in names + checks}:\n', "    if False:\n"),
    ("a model Lens's name is compared with no other", "tools/check_authority.py",
     ' + list(lenses["model"])', ""),
    ("the status on the item may carry a Lens's check's name", "tools/check_authority.py",
     "for name in names + checks}", "for name in names}"),
    ("names are compared as written", "tools/check_authority.py",
     "    return name.strip().casefold()\n", "    return name\n"),
    ("a Lens named twice is accepted", "tools/check_authority.py",
     "            if _folded(name) in seen:\n", "            if False:\n"),
    ("a check named twice is accepted", "tools/check_authority.py",
     '(("Lens", names), ("check", checks))', '(("Lens", names),)'),
    ("a check with no verdict is ignored", "kernel/derive.py",
     "    if unreadable:\n", "    if False:\n"),
    ("a check with no verdict is read before a failed one", "kernel/derive.py",
     "    if failed:\n"
     '        return {"state": t.ADDRESSING, "reason": "check_failed", "evidence": failed}\n',
     "    if unreadable:\n"
     '        return {"state": t.VERIFYING, "reason": "check_unreadable", "evidence": unreadable}\n'
     "    if failed:\n"
     '        return {"state": t.ADDRESSING, "reason": "check_failed", "evidence": failed}\n'),
    ("a dependency bot's pull request someone else pushed to skips the model review", "kernel/derive.py",
     ' and facts["last_pusher"] == facts["author"]:', ":"),
    ("a class the configuration does not name skips the model review", "kernel/derive.py",
     'facts["class"] in lenses["model_not_required_for"]', "True"),
    ("a dependency update converges before its checks are read", "kernel/derive.py",
     "    # Deterministic Lenses first: a model's time is not spent on content they reject.\n",
     "    if not required_model_lenses(facts, config):\n"
     '        return {"state": t.CONVERGED, "reason": "approval_due", "evidence": []}\n'),
    ("a dependency update converges before its threads are read", "kernel/derive.py",
     "    open_gates = gates(facts, config)\n",
     "    open_gates = gates(facts, config) if required_model_lenses(facts, config) else []\n"),
    ("a writer's request for changes does not gate", "kernel/derive.py",
     "    return threads + standing_requests(facts)\n", "    return threads\n"),
    ("a stranger's request for changes gates", "kernel/derive.py",
     'if is_person(rv["by"]) and', 'if rv["by"]["kind"] == "human" and'),
    ("a Lens's request for changes gates", "kernel/derive.py",
     'if is_person(rv["by"]) and', 'if rv["by"]["can_write"] and'),
    ("new content clears a request for changes", "kernel/derive.py",
     'for rv in sorted(facts["reviews"], key=verdict_order):',
     'for rv in sorted([rv for rv in facts["reviews"] if rv["content_id"] == facts["content_id"]],'
     ' key=verdict_order):'),
    ("a review that only comments clears a request for changes", "kernel/derive.py",
     ' and rv["state"] != "commented":', ":"),
    ("another writer's approval clears a request for changes", "kernel/derive.py",
     '            latest[rv["by"]["name"]] = rv\n', '            latest["anyone"] = rv\n'),
    ("an earlier review is read as the latest", "kernel/derive.py",
     'sorted(facts["reviews"], key=verdict_order)', 'facts["reviews"]'),
    ("a tie between a request and an approval resolves to the approval", "kernel/derive.py",
     '"changes_requested" in (rv["state"], rv.get("dismissed_from"))',
     '"changes_requested" not in (rv["state"], rv.get("dismissed_from"))'),
    ("an App's dismissal clears a request for changes", "kernel/derive.py",
     '            if is_person(rv["dismissed_by"]):\n', '            if rv["dismissed_by"]["can_write"]:\n'),
    ("a stranger's dismissal clears a request for changes", "kernel/derive.py",
     '            if is_person(rv["dismissed_by"]):\n', '            if rv["dismissed_by"]["kind"] == "human":\n'),
    ("a standing approval is read before a request for changes", "kernel/derive.py",
     "    open_gates = gates(facts, config)\n",
     "    approval = standing_approval(facts, config)\n"
     "    if approval is not None:\n"
     '        return {"state": t.CONVERGED, "reason": "approved", "evidence": [approval["commit"]]}\n'
     "    open_gates = gates(facts, config)\n"),
    ("an unreadable review is trusted", "kernel/derive.py",
     "    if unreadable_reviews(facts, config):\n", "    if False:\n"),
    ("an unreadable review is read after the model review's wait", "kernel/derive.py",
     *moved_after("kernel/derive.py", REVIEW_GUARD, REVIEW_WAIT)),
    ("a queued pull request whose approval is lost stays in the queue", "kernel/derive.py",
     STAYS, '    if d["reason"] in ("approved", "approval_due"):\n'),
    ("a queued pull request with a gate open stays in the queue", "kernel/derive.py",
     STAYS, '    if d["reason"] == "approved" or d["reason"] in t.GATE_REASONS:\n'),
    ("a Hold leaves a queued pull request in the queue", "kernel/derive.py",
     STAYS, '    if d["reason"] == "approved" or d["state"] == t.HELD:\n'),
    ("a read that fails leaves a pull request in the queue", "kernel/derive.py",
     STAYS, '    if d["reason"] == "approved" or d["state"] is None:\n'),
    ("a check that no longer passes leaves a pull request in the queue", "kernel/derive.py",
     STAYS, '    if d["reason"] in ("approved", "check_failed", "check_unreadable", "conflict"):\n'),
    ("a merge state not worked out yet takes a queued pull request out", "kernel/derive.py",
     ' and "mergeable_unreadable" not in past', ""),
    ("a required check not reported yet takes a queued pull request out", "kernel/derive.py",
     ' and "awaiting_checks" not in past', ""),
    ("a required Lens that has not reported takes a queued pull request out", "kernel/derive.py",
     ' and "awaiting_review" not in past', ""),
    ("a wait is read past on a pull request that is not queued", "kernel/derive.py",
     "    d = reading(facts, runs, config, ())\n", "    d = reading(facts, runs, config, t.QUEUE_WAITS)\n"),
    ("a draft stays in the merge queue", "kernel/derive.py",
     STAYS, '    if d["reason"] == "approved" or d["state"] == t.DRAFT:\n'),
    ("hands-off takes a pull request out of the queue", "kernel/derive.py",
     LEFT_ALONE, LEFT_ALONE.replace(" or hands_off(facts, config)", "")),
    ("hands-off anyone placed leaves a queued pull request in the queue", "kernel/derive.py",
     LEFT_ALONE, LEFT_ALONE.replace("hands_off(facts, config)", 't.LABEL_HANDS_OFF in [ev.get("label") for ev in'
                                    ' facts["label_events"] if isinstance(ev, dict)]')),
    ("a pull request that is not queued is dequeued", "kernel/derive.py",
     LEFT_ALONE, LEFT_ALONE.replace(' or not facts["queue"]', "")),
    ("a pull request that is not served is dequeued", "kernel/derive.py",
     LEFT_ALONE, LEFT_ALONE.replace("d[\"state\"] in t.TERMINAL", "d[\"state\"] in (t.MERGED, t.CLOSED)")),
    ("a pause lets a dequeue through", "kernel/decide.py",
     "        if paused:\n", "        if False:\n"),
    ("a deferred dequeue is not the Maintainer's to see", "kernel/decide.py",
     ", attention=t.NEEDS_YOU)", ")"),
    ("a dequeue is held to the act ceiling", "kernel/decide.py",
     DEQUEUE,
     '        if facts.get("acts_since_writer") is None or facts["acts_since_writer"] >= config["limits"]["max_acts_per_item"]:\n'
     '            return _decision(facts, t.HELD, "act_ceiling", [], t.HOLD)\n' + DEQUEUE),
    ("a Run in progress keeps a pull request in the queue", "kernel/decide.py",
     DEQUEUE_IF,
     "    if in_progress(runs_on(runs, facts)):\n"
     "        return _decision(facts, state, reason, evidence, t.NOTHING, working=True)\n" + DEQUEUE_IF),
    ("a draft or a queued item is left alone before the dequeue is read", "kernel/decide.py",
     DEQUEUE_IF,
     "    if state in t.TERMINAL or state in (t.DRAFT, t.QUEUED):\n"
     "        return _decision(facts, state, reason, evidence, t.NOTHING)\n" + DEQUEUE_IF),
    ("a read that fails defers before the dequeue is read", "kernel/decide.py",
     DEQUEUE_IF,
     "    if state is None:\n"
     "        return _decision(facts, None, reason, evidence, t.DEFER)\n" + DEQUEUE_IF),
    ("an unreadable review is read before what needs no review", "kernel/derive.py",
     '    if facts["state"] == "merged":\n', REVIEW_GUARD + '    if facts["state"] == "merged":\n'),
    ("an unreadable dismissal is trusted", "kernel/derive.py",
     '        if rv["state"] == "dismissed" and not readable_actor(rv.get("dismissed_by"), facts, config):\n',
     "        if False:\n"),
    ("a dismissed approval is read as a request for changes", "kernel/derive.py",
     '            if rv["dismissed_from"] != "changes_requested":\n                continue\n', ""),
    ("a dismissed approval does not end an earlier request", "kernel/derive.py",
     'if rv["state"] == "dismissed" and rv["dismissed_from"] == "commented":',
     'if rv["state"] == "dismissed" and rv["dismissed_from"] != "changes_requested":'),
    ("a dismissed comment ends an earlier request", "kernel/derive.py",
     '        if rv["state"] == "dismissed" and rv["dismissed_from"] == "commented":\n            continue\n', ""),
    ("a review not dismissed that carries dismissal fields is trusted", "kernel/derive.py",
     '        if rv["state"] != "dismissed" and (rv.get("dismissed_by") is not None'
     ' or rv.get("dismissed_from") is not None):\n',
     "        if False:\n"),
    ("an unreadable dismissed_from is trusted", "kernel/derive.py",
     '        if rv["state"] == "dismissed" and rv.get("dismissed_from") not in t.DISMISSED_FROM:\n',
     "        if False:\n"),
    ("write access that is not exactly true or false is read", "kernel/derive.py",
     'and type(actor.get("can_write")) is bool', 'and "can_write" in actor'),
    ("a kind the Kernel does not know is read", "kernel/derive.py",
     'actor.get("kind") in t.ACTOR_KINDS', '"kind" in actor'),
    ("an empty name is read", "kernel/derive.py",
     ' and actor["name"] != ""', ""),
    ("a review state the Kernel does not know is read", "kernel/derive.py",
     'rv.get("state") not in t.REVIEW_STATES', '"state" not in rv'),
    ("a review with no time is read", "kernel/derive.py",
     '        if not is_time(rv.get("submitted_at")):\n            return True\n', ""),
    ("a review's time in another format is read", "kernel/derive.py",
     'if not is_time(rv.get("submitted_at")):', 'if not isinstance(rv.get("submitted_at"), str):'),
    ("an unreadable review is not the Maintainer's to see", "kernel/decide.py",
     '"check_unreadable", "review_unreadable",', '"check_unreadable",'),
    ("an item with no State is never the Maintainer's to see", "kernel/decide.py",
     "    if state is None and reason not in NEEDS_YOU_REASONS:\n", "    if state is None:\n"),
    ("a check with no verdict does not defer", "kernel/decide.py",
     '    if reason == "check_unreadable":\n', "    if False:\n"),
    ("two Runs on one item", "kernel/decide.py",
     "    if in_progress(mine):\n", "    if False:\n"),
    ("the approver may be the author", "kernel/derive.py",
     'if config["approver"] in (facts["author"], facts["last_pusher"]):', "if False:"),
    ("a pause admits a Run", "kernel/decide.py",
     "    pause = _pause(context)\n    if pause:\n", "    pause = _pause(context)\n    if False:\n"),
    ("a pause lets an approval or a merge through", "kernel/decide.py",
     "        pause = _pause(context)\n        if pause:\n", "        pause = _pause(context)\n        if False:\n"),
    ("a pause hides the approver Hold", "kernel/decide.py",
     "    if state == t.HELD:\n        return _decision(facts, state, reason, evidence, t.HOLD)\n",
     '    if state == t.HELD and reason == "approver_is_author_or_last_pusher" and _pause(context):\n'
     "        return _decision(facts, state, _pause(context), evidence, t.DEFER)\n"
     "    if state == t.HELD:\n        return _decision(facts, state, reason, evidence, t.HOLD)\n"),
    ("the approver is read before the gates", "kernel/derive.py",
     "    # Every gate before the approval: a standing approval never passes over a person's objection.\n",
     '    if config["approver"] in (facts["author"], facts["last_pusher"]):\n'
     '        return {"state": t.HELD, "reason": "approver_is_author_or_last_pusher", "evidence": []}\n'
     "    # Every gate before the approval: a standing approval never passes over a person's objection.\n"),
    ("an unreadable pause is read as no pause", "kernel/decide.py",
     'if context.get("paused") is False:', 'if not context.get("paused"):'),
    ("attempts are unlimited", "kernel/decide.py",
     '    if len(attempts) >= limits["max_attempts"]:\n', "    if False:\n"),
    ("capacity faults count as attempts", "kernel/decide.py",
     ' and r.get("outcome") == "item"]', "]"),
    ("rounds are unlimited", "kernel/decide.py",
     '        if len(rounds) >= limits["max_rounds"]:\n', "        if False:\n"),
    ("the run ceiling is ignored", "kernel/decide.py",
     '    if len(_spent(recent)) >= limits["max_runs_per_item"]:\n', "    if False:\n"),
    ("a landed approval counts toward the Run ceiling", "kernel/decide.py",
     '[r for r in recent if not (r["intent"] == t.ISSUE_APPROVAL and r["conclusion"] == "success")]',
     "list(recent)"),
    ("an approval that did not land is free of the Run ceiling", "kernel/decide.py",
     'not (r["intent"] == t.ISSUE_APPROVAL and r["conclusion"] == "success")', 'r["intent"] != t.ISSUE_APPROVAL'),
    ("an approval that keeps failing for the environment is issued for ever", "kernel/decide.py",
     '        if len(_spent(since)) >= limits["max_runs_per_item"]:\n', "        if False:\n"),
    ("an approval that does not land is issued for ever", "kernel/decide.py",
     '        if len(failed) >= limits["max_attempts"]:\n', "        if False:\n"),
    ("a writer's action does not renew an approval's allowance", "kernel/decide.py",
     "        since = since_writer(mine, facts)\n", "        since = mine\n"),
    ("a failed model Run counts as an approval attempt", "kernel/decide.py",
     "_attempts(since, t.ISSUE_APPROVAL)",
     '[r for r in since if r["status"] == "completed" and r["conclusion"] != "success" and r.get("outcome") == "item"]'),
    ("an approval's failed attempts stop an enqueue", "kernel/decide.py",
     '    if action == "issue_approval":\n', "    if True:\n"),
    ("acts are unlimited", "kernel/decide.py",
     '    if acts >= limits["max_acts_per_item"]:\n', "    if False:\n"),
    ("the act ceiling is reached one act late", "kernel/decide.py",
     'acts >= limits["max_acts_per_item"]', 'acts > limits["max_acts_per_item"]'),
    ("an enqueue is not held to the act ceiling", "kernel/decide.py",
     '    if acts >= limits["max_acts_per_item"]:\n',
     '    if acts >= limits["max_acts_per_item"] and action == "issue_approval":\n'),
    ("an unreadable count of acts is read as none", "kernel/decide.py",
     '    acts = facts.get("acts_since_writer")\n', '    acts = facts.get("acts_since_writer") or 0\n'),
    ("a count of acts that is not a whole number is trusted", "kernel/decide.py",
     "if type(acts) is not int or acts < 0:", "if not isinstance(acts, int) or acts < 0:"),
    ("a negative count of acts is trusted", "kernel/decide.py",
     "if type(acts) is not int or acts < 0:", "if type(acts) is not int:"),
    ("the act ceiling is not the Maintainer's to see", "kernel/decide.py",
     '"awaiting_human", "act_ceiling",', '"awaiting_human",'),
    ("an unreadable check is not the Maintainer's to see", "kernel/decide.py",
     '"act_ceiling", "check_unreadable",', '"act_ceiling",'),
    ("the act ceiling stops a Run", "kernel/decide.py",
     "    wanted = _wanted_run(state, reason, config)\n",
     '    if facts.get("acts_since_writer") is None or facts["acts_since_writer"] >= config["limits"]["max_acts_per_item"]:\n'
     '        return _decision(facts, t.HELD, "act_ceiling", [], t.HOLD)\n'
     "    wanted = _wanted_run(state, reason, config)\n"),
    ("a capacity fault does not defer", "kernel/decide.py",
     "    if until is not None and until > now:\n", "    if False:\n"),
    ("an unreadable count of active Runs is trusted", "kernel/decide.py",
     "    if active is None:\n", "    if active is None and False:\n"),
    ("the org limit is ignored", "kernel/decide.py",
     '    if active >= limits["org_max_active_runs"]:\n', "    if False:\n"),
    ("a wait is stale at its limit, not past it", "kernel/derive.py",
     "    return waited > lifecycle", "    return waited >= lifecycle"),
    ("a wait counts while no passes ran", "kernel/derive.py",
     "    starts = [x for x in (moved, passes_since) if is_time(x) and x <= now]\n",
     "    starts = [x for x in (moved,) if is_time(x) and x <= now]\n"),
    ("an unreadable start of the passes is trusted", "kernel/derive.py",
     "    starts = [x for x in (moved, passes_since) if is_time(x) and x <= now]\n",
     "    starts = [x for x in (moved, passes_since) if x is not None]\n"),
    ("a start of the passes still to come is trusted", "kernel/derive.py",
     "    starts = [x for x in (moved, passes_since) if is_time(x) and x <= now]\n",
     "    starts = [x for x in (moved, passes_since) if is_time(x)]\n"),
    ("a wait counts from the item's first movement", "kernel/derive.py",
     "    return max(readable) if readable else None\n", "    return min(readable) if readable else None\n"),
    ("a time still to come moves an item", "kernel/derive.py",
     "    readable = [x for x in times if is_time(x) and x <= now]\n", "    readable = [x for x in times if is_time(x)]\n"),
    ("a time that is no moment moves an item", "kernel/derive.py",
     "    readable = [x for x in times if is_time(x) and x <= now]\n",
     "    readable = [x for x in times if isinstance(x, str) and x <= now]\n"),
    ("a required check that reports does not move an item", "kernel/derive.py",
     '    times += [c.get("completed_at") for c in facts["checks"]'
     " if any(reports_for(c, lens) for lens in required)]\n", ""),
    ("a check that is not required moves an item", "kernel/derive.py",
     ' for c in facts["checks"] if any(reports_for(c, lens) for lens in required)]', ' for c in facts["checks"]]'),
    ("a check from another App moves an item", "kernel/derive.py",
     " if any(reports_for(c, lens) for lens in required)]",
     " if any(named_for(c, lens) for lens in required)]"),
    ("an App that is no Lens's moves an item", "kernel/derive.py",
     'actor.get("kind") in ("lens", t.MACHINE_USER)', 'actor.get("kind") in ("lens", t.MACHINE_USER, t.APP)'),
    ("the machine user's approval does not move an item", "kernel/derive.py",
     'actor.get("kind") in ("lens", t.MACHINE_USER)', 'actor.get("kind") == "lens"'),
    ("a writer's or a Lens's review does not move an item", "kernel/derive.py",
     '    times += [rv.get("submitted_at") for rv in facts["reviews"] if moves(rv.get("by"))]\n', ""),
    ("a writer's or a Lens's thread does not move an item", "kernel/derive.py",
     '    times += [th.get("opened_at") for th in facts["threads"] if moves(th.get("opened_by"))]\n', ""),
    ("a Run on another item moves this one", "kernel/derive.py",
     '    times += [r["started_at"] for r in runs_on(runs, facts)]\n', '    times += [r["started_at"] for r in runs]\n'),
    ("a day its month does not have is a moment", "kernel/derive.py",
     "1 <= day <= days_in(year, month)", "1 <= day"),
    ("an hour past the day is a moment", "kernel/derive.py",
     "            and hour < t.HOURS_PER_DAY and minute", "            and minute"),
    ("a deferral of the whole scope goes stale", "kernel/decide.py",
     ' and d["reason"] not in t.SCOPE_DEFERRALS', ""),
    ("the model provider's deferral goes stale", "kernel/terms.py",
     '"pause_unreadable", "capacity", "capacity_unreadable"', '"pause_unreadable", "capacity_unreadable"'),
    ("a stale wait changes what happens", "kernel/decide.py",
     "        return dict(d, attention=t.STALE)\n", "        return dict(d, attention=t.STALE, outcome=t.NOTHING)\n"),
    ("an item that needs the Maintainer goes stale", "kernel/terms.py",
     "MAY_GO_STALE = frozenset({REVIEW, READY})", "MAY_GO_STALE = frozenset({REVIEW, READY, NEEDS_YOU})"),
    ("a working item goes stale", "kernel/terms.py",
     "MAY_GO_STALE = frozenset({REVIEW, READY})", "MAY_GO_STALE = frozenset({REVIEW, READY, WORKING})"),
    ("a failed item goes stale", "kernel/terms.py",
     "MAY_GO_STALE = frozenset({REVIEW, READY})", "MAY_GO_STALE = frozenset({REVIEW, READY, FAILED})"),
    ("every hundredth year is a leap year", "kernel/derive.py",
     "(year % unless != 0 or year % still == 0)", "True"),
]


TIMEOUT = 600      # seconds for one run of the suite. A run that takes longer is an ERROR, never a kill
# What unittest prints last when a test failed or raised. Without it, the run broke some other way.
FAILED = re.compile(r"^FAILED \((?:failures|errors)=", re.M)
# unittest's stand-in for a test module that would not import: the copy is broken, not the rule.
UNIMPORTABLE = "unittest.loader._FailedTest"
# How every ERROR's reason ends. An ERROR says nothing of the rule, so the run is mended and made again.
AGAIN = "; fix the copy or run named here, then run python3 -m tools.mutants again"


def suite(cwd: pathlib.Path, timeout: float = TIMEOUT) -> tuple:
    """Run the tests in `cwd` to the first failure: (exit status, output), the status None if it timed out."""
    env = dict(os.environ, SIM_SEEDS="40", MUTATING="1")
    with subprocess.Popen([sys.executable, "-m", "unittest", "discover", "-q", "-f", "tests"], cwd=str(cwd),
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


def attempt(mutant: tuple, root: pathlib.Path, run) -> tuple:
    """Break one rule in a fresh copy of `root` and run the tests there: (outcome, why)."""
    name, rel, old, new = mutant
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp) / "repo"
        walk.copy(root, work)
        target = work / rel
        text = target.read_text()
        if text.count(old) != 1:
            return "STALE", "the code it mutates has changed"
        target.write_text(text.replace(old, new))
        return verdict(*run(work))


def guarded(mutant: tuple, root: pathlib.Path, run) -> tuple:
    """`attempt`, with anything it raises made an ERROR for this mutant, so that the others still report."""
    try:
        return attempt(mutant, root, run)
    except Exception as err:    # a failed copy, read or run; never a kill
        return "ERROR", "the run failed with %s: %s%s" % (type(err).__name__, err, AGAIN)


def main(mutants: list = None, root: pathlib.Path = ROOT, run=suite, workers: int = None) -> int:
    mutants = MUTANTS if mutants is None else mutants
    outcome, why = verdict(*run(root))
    if outcome != "SURVIVED":
        print("the tests fail before anything is broken; a mutant cannot be told from that%s"
              % (" (%s)" % why if why else ""))
        return 1
    killed = 0
    # One run to a CPU. map() hands the results back in the order of `mutants`, however the runs finish.
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers or os.cpu_count() or 1) as pool:
        results = pool.map(lambda mutant: guarded(mutant, root, run), mutants)
        for mutant, (outcome, why) in zip(mutants, results):
            print("%-9s %s%s" % (outcome, mutant[0], " (%s)" % why if why else ""), flush=True)
            killed += outcome == "killed"
    print("%d of %d mutants killed" % (killed, len(mutants)))
    return 0 if killed == len(mutants) else 1


if __name__ == "__main__":
    sys.exit(main())
