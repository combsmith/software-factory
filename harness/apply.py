"""What `apply` does with one Result: whether it may write at all, what it writes, and what it records (design sections
2.3, 3.6 to 3.8 and 3.10, issue 194's rulings 5 and 7, decision 0050).

`refusal(...)` reads the item again and the Result, and gives the one reason, a code, why nothing may be written, or
None. In this order, so that each has its own code: the item closed, its content moved, the Factory paused, the item
held, or the Kernel, asked again with this Run left out, not admitting this Run's Intent on this content, all a change
under the Run (`superseded`); then the Result: not this Run's or this Release's, not completed, uncovered (decision
0049), asking for an Effect the Task does not permit or naming one twice, posting a raised Finding other than once, a
Finding that does not gate on a thread or one that gates on an annotation, or a Finding where it has no place; a
Disposition that gives neither half or both, or the half this Run's Role may not make; a `security` thread resolved
on a proposal of declined or deferred. Each is the Role's (`item`), but an uncovered Result whose rubric cannot be read
is the Factory's (`environment`).

`requests(...)` is what is written, in `effect/1`'s order, each with what `apply`, never the Result, decides: a review
is a comment on the commit the Decision admitted, so a Role's review never approves; a check run's name, conclusion
and `external_id` are the Task's Role's and the Run's. `applied(...)` and `outcome(...)` record what was read back,
and only that: an Effect is `applied` only with the key its surface was read back by, and a posted Finding is written
whole as `finding/1` from its read-back surface (decision 0038, L-41).

Nothing here reads a clock, a file or the network: the job hands in the item read again, the run records and the
context, and the effects port's read-backs.
"""
from __future__ import annotations

import hashlib
import json
import re

from adapters import github, identity
from adapters.rules import UNREADABLE as LIST_UNREADABLE
from harness import shared
from harness import task as task_
from kernel import derive
from kernel import terms as t
from kernel.coverage import covered
from kernel.decide import decide
from tools.hooks import protected

# The order `apply` writes in: effect/1's, one list for each type (section 3.6).
ORDER = ("submit_review", "create_check_run", "resolve_thread", "comment")
# The halves of a Disposition, and the kind of Role that may make each (section 3.8).
PROPOSES = "author"
DECIDES = "owner"
# Proposals a security Finding's thread is never resolved on (section 3.8).
NOT_ON_SECURITY = ("declined", "deferred")
# What `apply` reads again with the Role App's own token (the Maintainer, 2026-10-22): every fact the Kernel is asked
# on, and the run records with each failed Run's outcome. Its grants for them wait on the App's registration.
READS = ("read:facts.item", "read:facts.state", "read:facts.is_draft", "read:facts.class", "read:facts.author",
         "read:facts.mergeable", "read:facts.targets_protected", "read:facts.actor.can_write", "read:facts.content_id",
         "read:facts.diff", "read:facts.last_pusher", "read:facts.label_events", "read:facts.last_push_at",
         "read:facts.last_writer_action_at", "read:facts.reviews", "read:facts.threads", "read:facts.checks",
         "read:facts.acceptance", "read:records.runs", "read:records.artifacts")
THREAD = re.compile(r"PRRT_[A-Za-z0-9_-]+")
# A character no path from the top of the repo holds: a control character, which a layer below could cut it at, and a
# backslash, which another reading takes for `/` (issue 139).
UNREADABLE_PATH = re.compile(r"[\x00-\x1f\x7f\\]")
# How a Result that did not complete ends, by its reason: the Role's fault, or the Factory's.
THE_ROLES = ("result_invalid", "task_too_large")


def push_refusal(paths, previous_paths, protected_list):
    """Why a Role's push may not land, or None (issue 139): `push_protected` where a path it changes, or one a path of
    it was renamed or copied from, is on the base's list (`adapters/rules.py`), every protected path and every Lens's
    input, matched as `tools/hooks/protected.py` matches them. A push lands content no model Lens has reviewed, so one
    that touches the list is always refused, and a person pushes such a change (decisions 0020 and 0052). A path that
    cannot be read as one from the top of the repo (an empty name, `.` or `..`, a control character or a backslash), or
    paths that are no list, could be any, and are refused too. A list that is none, or empty, or holds what the Kernel
    reads as no pattern (`kernel/derive.py`'s `readable_pattern`), or a pattern with a control character or a backslash,
    which no path it is matched against may hold and so protects nothing, is `push_list_unreadable`, never nothing to
    touch. No Effect pushes yet: slice 2's push Effect calls this."""
    if not isinstance(protected_list, list) or not protected_list \
            or not all(derive.readable_pattern(p) and not UNREADABLE_PATH.search(p) for p in protected_list):
        return LIST_UNREADABLE
    if not isinstance(paths, (list, tuple)) or not isinstance(previous_paths, (list, tuple)):
        return "push_protected"
    every = protected.entries([(pattern, "") for pattern in protected_list])
    for path in list(paths) + [p for p in previous_paths if p is not None]:
        names = path.split("/") if isinstance(path, str) else None
        if names is None or not all(names) or any(n in (".", "..") for n in names) or UNREADABLE_PATH.search(path) \
                or any(whole.match(path.casefold()) for _, _, _, whole in every):
            return "push_protected"
    return None


def gates(finding: dict) -> bool:
    """Whether a raised Finding gates: a `security` one at any severity, any other when blocking or major (section 4.2)."""
    return finding["category"] == "security" or finding["severity"] in ("blocking", "major")


def finding_id(lens: str, surface: dict) -> str:
    """A Finding's id, from its source and its surface's key, never from its text (section 3.7)."""
    said = "%s %s %s" % (lens, surface["type"], surface["key"])
    return "f_" + hashlib.sha256(said.encode()).hexdigest()[:16]


def posts(effects: dict) -> list:
    """`(effect id, type, finding ref)` for each place the Result posts a raised Finding."""
    out = []
    for review in effects.get("submit_review", ()):
        out += [(review["id"], "submit_review", c["finding"]) for c in review["comments"]]
    for check in effects.get("create_check_run", ()):
        out += [(check["id"], "create_check_run", a["finding"]) for a in check["annotations"]]
    return out


def _this_run(listed, github_run) -> bool:
    """Whether a Run listed before its name is this job's own: its GitHub id, which the records port gives as digits,
    is this job's `GITHUB_RUN_ID`, compared as the same text whatever type either was given as."""
    return isinstance(listed, dict) and str(listed.get("run")) == str(github_run)


def _superseded(task: dict, facts: dict, runs: list, context: dict, kernel: dict, now: str, github_run):
    """The code of a change under the Run, or None. The Kernel is asked again with this Run left out: a Run in
    progress admits nothing, and this one is; nor does a Run listed before its name, and this one may be, so its own
    `GITHUB_RUN_ID` is dropped from those (decision 0036). Any other unidentified Run defers it."""
    if facts["state"] != "open":
        return "item_closed"
    if facts["content_id"] != task["content_id"]:
        return "content_moved"
    if context.get("paused") is not False:
        return "paused" if context.get("paused") else "pause_unreadable"
    others = [r for r in runs if r["run"] != task["run"]]
    if derive.derive(facts, others, kernel)["state"] == t.HELD:
        return "item_held"
    # This Run is left out of the Runs counted active too, as it is left out of the list.
    mine = [r for r in runs if r["run"] == task["run"] and r["status"] != "completed"]
    # A count that cannot be this Run's, a flag or one under this Run's own, is left as read: the Kernel defers on it.
    active = context.get("active_runs")
    if mine and type(active) is int and active >= len(mine):
        context = dict(context, active_runs=active - len(mine))
    if isinstance(context.get("unidentified_runs"), list):
        context = dict(context, unidentified_runs=[u for u in context["unidentified_runs"]
                                                   if not _this_run(u, github_run)])
    again = decide(facts, others, context, kernel, now)
    if again["outcome"] != t.ADMIT or again["admit"] != {"role": task["role"], "intent": task["intent"],
                                                          "content_id": task["content_id"]}:
        return "not_admitted"
    return None


def _effects(task: dict, result: dict, facts: dict):
    effects = result["effects"]
    if any(kind not in task["permitted_effects"] for kind in effects if effects[kind]):
        return "effect_not_permitted"
    ids = [e["id"] for kind in ORDER for e in effects.get(kind, ())]
    if len(ids) != len(set(ids)):
        return "effect_named_twice"
    # A review is recovered as this App's one on this commit (section 3.6): a second would be read back as the first.
    if len(effects.get("submit_review", ())) > 1:
        return "review_twice"
    # A thread's id is global, and the App's token reaches every item it is installed on: an Effect on a thread is
    # on one of this item's (decision 0038).
    threads = {th["id"] for th in facts["threads"]}
    on = [e["thread"] for e in effects.get("resolve_thread", ())] + [
        e["on"] for e in effects.get("comment", ()) if e["on"] != "item"]
    if any(thread not in threads for thread in on):
        return "thread_not_on_item"
    raised = {f["ref"]: f for f in result["findings"]}
    if len(raised) != len(result["findings"]):
        return "finding_named_twice"
    posted = posts(effects)
    refs = [ref for _, _, ref in posted]
    if any(ref not in raised for ref in refs):
        return "finding_not_raised"
    if any(refs.count(ref) != 1 for ref in raised):
        return "finding_not_posted_once"
    for _, kind, ref in posted:
        finding = raised[ref]
        # A Finding that gates is a review comment, one that does not an annotation, never a thread (section 3.7).
        if kind == "submit_review" and not gates(finding):
            return "finding_does_not_gate"
        if kind == "create_check_run" and gates(finding):
            return "finding_gates"
        # A posted Finding is placed on lines: a whole file is no place a review comment or an annotation can be.
        # A range is read from its first line to its last: one that ends before it starts has no place.
        where = finding.get("location", {})
        if "start_line" not in where or where.get("end_line", where["start_line"]) < where["start_line"]:
            return "finding_has_no_place"
    return None


def _dispositions(task: dict, result: dict, facts: dict, role: dict, authority: dict):
    """A Disposition gives one half, the one this Run's Role may make: a proposal is the author's, and a decision the
    owner's of the Finding's category, read from its thread in the facts (section 3.8)."""
    threads = {fid: th for th in facts["threads"] for fid in _findings_of(facts, th["id"])}
    named = [d["finding"] for d in result["dispositions"]]
    if len(named) != len(set(named)):
        return "disposition_given_twice"
    for d in result["dispositions"]:
        halves = [h for h in ("proposal", "decision") if h in d]
        if len(halves) != 1:
            return "disposition_halves"
        # A Disposition is on a Finding the Task lists, whose thread is on this item.
        if d["finding"] not in task["findings"] or d["finding"] not in threads:
            return "disposition_of_no_finding"
        if halves[0] == "proposal":
            if role["kind"] != PROPOSES or role["name"] != authority["author_role"]:
                return "disposition_not_yours"
        else:
            owner = authority["categories"].get(threads[d["finding"]]["category"], {}).get("owner")
            if role["kind"] != DECIDES or role["name"] != owner:
                return "disposition_not_yours"
    # A security Finding's thread is never resolved on a proposal of declined or deferred, whichever Role asks.
    security = {th["id"] for th in facts["threads"] if th["category"] == "security"}
    declined = {d["finding"] for d in result["dispositions"]
                if d.get("proposal", {}).get("outcome") in NOT_ON_SECURITY}
    for resolve in result["effects"].get("resolve_thread", ()):
        if resolve["thread"] in security and declined & set(_findings_of(facts, resolve["thread"])):
            return "security_finding_declined"
    # A resolved thread is an accepted Disposition (section 3.8): only the owner of the thread's category resolves it,
    # and only on its own decision, in this Result, to accept it.
    accepted = {d["finding"] for d in result["dispositions"] if d.get("decision", {}).get("result") == "accepted"}
    for resolve in result["effects"].get("resolve_thread", ()):
        th = next(th for th in facts["threads"] if th["id"] == resolve["thread"])
        owner = authority["categories"].get(th["category"], {}).get("owner")
        if role["kind"] != DECIDES or role["name"] != owner:
            return "resolve_not_yours"
        if not accepted & set(_findings_of(facts, resolve["thread"])):
            return "resolve_not_accepted"
        # The owner may accept a security Finding only on a proposal of fixed or not applicable, and that proposal is
        # in the author's Run, which `apply` cannot read yet: a security thread is not resolved by any Role (Muse's
        # read). It waits on the fix Intent, which brings the author's proposal to the owner's Task.
        if resolve["thread"] in security:
            return "security_proposal_unread"
    return None


def _findings_of(facts: dict, thread: str) -> list:
    """The ids a thread's Finding may have, from every Lens that could have opened it."""
    return [finding_id(th["opened_by"]["name"], {"type": "thread", "key": th["id"]})
            for th in facts["threads"] if th["id"] == thread and isinstance(th.get("opened_by"), dict)]


def refusal(task: dict, result: dict, facts: dict, runs: list, context: dict, kernel: dict, now: str, role: dict,
            rubric, authority: dict, github_run=None) -> tuple:
    """`(fault, reason)` why nothing may be written, or None. `rubric` is the Intent's when it reviews, else None;
    `github_run` is this job's own `GITHUB_RUN_ID`."""
    moved = _superseded(task, facts, runs, context, kernel, now, github_run)
    if moved:
        return "superseded", moved
    if (result["run"], result["release"]) != (task["run"], task["release"]):
        return "item", "result_not_the_runs"
    if result["status"] != "completed":
        reason = result["reason"] or result["status"]
        return ("item" if reason in THE_ROLES or result["status"] != "failed" else "environment"), reason
    if rubric is not None:
        said, _ = covered(rubric, result["coverage"], result["findings"], facts["changed_paths"])
        if said != "covered":
            return ("item", "uncovered") if said == "uncovered" else ("environment", "coverage_unreadable")
    why = _effects(task, result, facts) or _dispositions(task, result, facts, role, authority)
    return ("item", why) if why else None


def requests(task: dict, result: dict, head: str, role: dict, since: str = None) -> list:
    """`(effect id, type, request)` for each Effect, in the order written. What each request carries beyond the
    Result's own words is `apply`'s: the commit, the event, the check run's name and conclusion and its key, and for a
    comment, which has no key, when the Run began and its place among the Run's comments, by which it is recovered."""
    raised = {f["ref"]: f for f in result["findings"]}
    out = []
    for review in result["effects"].get("submit_review", ()):
        out.append((review["id"], "submit_review", {
            "commit": head, "event": "COMMENT", "body": review["body"] or "",
            "comments": [dict(_place(raised[c["finding"]]), finding=c["finding"], body=c["body"])
                         for c in review["comments"]]}))
    for check in result["effects"].get("create_check_run", ()):
        out.append((check["id"], "create_check_run", {
            "commit": head, "name": "factory / %s" % role["name"], "conclusion": "success",
            "external_id": "%s:%s" % (task["run"], check["id"]),
            "annotations": [dict(_place(raised[a["finding"]]), finding=a["finding"], body=a["body"],
                                 severity=raised[a["finding"]]["severity"]) for a in check["annotations"]]}))
    for resolve in result["effects"].get("resolve_thread", ()):
        out.append((resolve["id"], "resolve_thread", {"thread": resolve["thread"]}))
    # A comment on the item is recovered by its place among the Run's comments on the item, and no other's.
    index = 0
    for comment in result["effects"].get("comment", ()):
        out.append((comment["id"], "comment", {"on": comment["on"], "body": comment["body"], "since": since,
                                                "index": index}))
        index += comment["on"] == "item"
    return out


def _place(finding: dict) -> dict:
    where = finding["location"]
    start = where["start_line"]
    return {"path": where["path"], "start_line": start, "end_line": where.get("end_line", start)}


def applied(task: dict, result: dict, written: list, role: dict, refused=None) -> dict:
    """`applied/1`. `written` is `(effect id, type, read-back)` for each Effect the port was asked to write, its
    read-back `{state, key, surfaces, reason}`. An Effect is `applied` or `already_applied` only with the key it was
    read back by, and each Finding it posted only with the surface it was read back on; anything less is `failed`,
    `not_read_back`. A refused Result lists each Effect it asked for `refused`, with the reason, and posts nothing."""
    effects, findings = [], []
    if refused is not None:
        for kind in ORDER:
            for e in result["effects"].get(kind, ()):
                effects.append({"id": e["id"], "type": kind, "state": "refused", "key": None, "reason": refused})
        return {"schema": "applied/1", "run": task["run"], "release": task["release"], "effects": effects,
                "findings": []}
    raised = {f["ref"]: f for f in result["findings"]}
    for effect_id, kind, back in written:
        state, key, surfaces = back.get("state"), back.get("key"), back.get("surfaces") or {}
        refs = [ref for e, _, ref in posts(result["effects"]) if e == effect_id]
        if state in ("applied", "already_applied") and isinstance(key, str) and key and all(
                _surface(kind, key, ref, surfaces.get(ref)) for ref in refs):
            effects.append({"id": effect_id, "type": kind, "state": state, "key": key, "reason": None})
            for ref in refs:
                findings.append(_finding(task, role, raised[ref], kind, key, surfaces[ref]))
        elif state in ("failed", "refused") and back.get("reason"):
            effects.append({"id": effect_id, "type": kind, "state": state, "key": None, "reason": back["reason"]})
        else:
            effects.append({"id": effect_id, "type": kind, "state": "failed", "key": None, "reason": "not_read_back"})
    return {"schema": "applied/1", "run": task["run"], "release": task["release"], "effects": effects,
            "findings": findings}


def _surface(kind: str, key: str, ref: str, at) -> bool:
    """Whether a posted Finding's surface was read back: a review comment's thread, or an annotation on the check run
    read back, keyed by that check run and the Finding's ref."""
    if kind == "create_check_run":
        return at == "%s:%s" % (key, ref)
    return isinstance(at, str) and THREAD.fullmatch(at) is not None


def _finding(task: dict, role: dict, raised: dict, kind: str, key: str, at: str) -> dict:
    """`finding/1`, written whole from the surface read back: a review comment's thread, or an annotation on the
    check run read back, keyed by the check run and the Finding's ref."""
    surface = {"type": "thread", "key": at} if kind == "submit_review" else {"type": "annotation", "key": at}
    out = {"schema": "finding/1", "id": finding_id(role["name"], surface),
           "source": {"lens": role["name"], "kind": "role", "actor": role["app"] + "[bot]"}, "surface": surface,
           "location": dict(raised["location"]), "category": raised["category"], "severity": raised["severity"],
           "criterion": raised["criterion"], "content_id": task["content_id"]}
    if "adopted_from" in raised:
        out["adopted_from"] = {"lens": raised["adopted_from"]["lens"], "surface": dict(raised["adopted_from"]["surface"])}
    return out


def outcome(task: dict, record: dict, refused=None) -> dict:
    """`outcome/1`: null for a Run whose every Effect was read back; the refusal's fault and code; or `environment`,
    `effect_failed`, when an Effect was not."""
    if refused is not None:
        fault, reason = refused
    elif any(e["state"] in ("failed", "refused") for e in record["effects"]):
        fault, reason = "environment", "effect_failed"
    else:
        fault, reason = None, None
    return {"schema": "outcome/1", "run": task["run"], "release": task["release"], "outcome": fault, "reason": reason}


def admitted(record: dict, run: str, role: dict, findings: list) -> dict:
    """What `apply` holds a Result to, from the Decision that admitted Run `run` in the pass record and the Role's
    manifest, as the Task was built: or Refused, as a Run no Decision admitted finds none (section 3.5)."""
    if shared.errors(record, "pass") or shared.errors(role, "role") or not isinstance(findings, list):
        raise task_.Refused("the pass record, the manifest or the findings cannot be read")
    entry = task_.decision_of(record, run)
    if entry is None:
        raise task_.Refused("no Decision admitted Run %s" % run)
    admit = entry["decision"]["admit"]
    intents = [i for i in role["intents"] if i["name"] == admit["intent"]]
    if role["name"] != admit["role"] or len(intents) != 1:
        raise task_.Refused("the manifest is not the admitted Role's, or does not declare its Intent")
    return {"run": run, "release": record["release"], "role": admit["role"], "intent": admit["intent"],
            "content_id": admit["content_id"], "item": dict(entry["decision"]["item"]),
            "permitted_effects": list(intents[0]["permitted_effects"]), "findings": list(findings)}


def taken(data: bytes, digest: str):
    """The Result `run` uploaded, taken by the digest `run` reported and never by name (section 3.6), or None."""
    if not isinstance(data, bytes) or digest != "sha256:" + hashlib.sha256(data).hexdigest():
        return None
    try:
        result = json.loads(data.decode("utf-8"))
    except ValueError:
        return None
    return result if not shared.errors(result, "result") else None


def job(admit: dict, result, read, write, mint, role: dict, config: dict, now: str) -> tuple:
    """`(applied/1, outcome/1)` for one Result. `read()` is the item read again, `(facts, head, runs, context)`;
    `mint(permissions)` a token for the item's repo with exactly those, as a transport, and `write(transport, type,
    request)` the effects port's read-back of one Effect. Nothing is minted for a Result that is refused, and the
    token is revoked when the Effects are written, whatever happened (`mint` returns `(transport, revoke)`)."""
    if result is None:
        record = {"schema": "applied/1", "run": admit["run"], "release": admit["release"], "effects": [],
                  "findings": []}
        return record, _ended(admit, ("environment", "result_unreadable"))
    facts, head, runs, context = read()
    # When the Run began: its record's start, or, while it is listed before its name, its run's creation (decision
    # 0036). Neither read, a comment on the item cannot be recovered, and is refused as unreadable.
    since = next((r["started_at"] for r in runs if r["run"] == admit["run"]), None)
    if since is None and isinstance(context.get("unidentified_runs"), list):
        since = next((u["created_at"] for u in context["unidentified_runs"] if _this_run(u, config["github_run"])),
                     None)
    why = refusal(admit, result, facts, runs, context, config["kernel"], now, role, config["rubric"],
                  config["authority"], config["github_run"])
    if why is not None:
        record = applied(admit, result, [], role, refused=why[1])
        return record, outcome(admit, record, why)
    asked = requests(admit, result, head, role, since)
    # A comment on the item is recovered by when the Run began: not read, nothing is minted and nothing written.
    if since is None and any(kind == "comment" and req["on"] == "item" for _, kind, req in asked):
        record = applied(admit, result, [], role, refused="run_start_unread")
        return record, outcome(admit, record, ("environment", "run_start_unread"))
    if not asked:
        record = applied(admit, result, [], role)
        return record, outcome(admit, record)
    try:
        wanted = identity.permissions(config["app"], config["needs"], [kind for _, kind, _ in asked])
        transport, revoke = mint(wanted)
    except identity.Refused as err:
        record = applied(admit, result, [], role, refused=str(err))
        return record, outcome(admit, record, ("environment", str(err)))
    written = []
    try:
        for effect_id, kind, req in asked:
            # A credential GitHub would not take ends every later write on it.
            if any(back.get("reason") == "token_refused" for _, _, back in written):
                written.append((effect_id, kind, {"state": "refused", "reason": "token_refused"}))
                continue
            # A comment on the item is recovered by its place, so none is sent after one that was not written.
            if kind == "comment" and req["on"] == "item" and any(
                    k == "comment" and r["on"] == "item" and back.get("state") not in ("applied", "already_applied")
                    for (e, k, back), (_, _, r) in zip(written, asked)):
                written.append((effect_id, kind, {"state": "failed", "reason": "earlier_comment_unwritten"}))
                continue
            try:
                written.append((effect_id, kind, write(transport, kind, req)))
            except (github.Unanswered, OSError, ValueError, KeyError, TypeError):
                # A write that raised is a failed Effect, never a claim.
                written.append((effect_id, kind, {"state": "failed", "reason": "effect_raised"}))
    finally:
        revoked = revoke()
    record = applied(admit, result, written, role)
    # A token GitHub did not confirm revoked may still write: the Run is the Factory's to look at.
    if revoked is not True:
        return record, outcome(admit, record, ("environment", "token_not_revoked"))
    return record, outcome(admit, record)


def _ended(admit: dict, why: tuple) -> dict:
    return {"schema": "outcome/1", "run": admit["run"], "release": admit["release"], "outcome": why[0],
            "reason": why[1]}
