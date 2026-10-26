"""The pass records before this one, and the pass's own run (#193's ruling 10 for PR 2; #196's PR 2; decisions 0043
and 0045).

A pass is a run of the poller's workflow file in the Factory's repo, from its default branch, started by one of the
events that start a pass: the schedule, a dispatch or the end of a run. Its record is the one artifact named `pass` it
lists, a zip of one file, `pass.json`, read through `adapters/artifacts.py` in bounds of its own: 1 MiB zipped, as
listed and as downloaded, the one download the transport bounds wider than 64 KiB (decision 0045's row of #196), and
8 MiB read out of the zip. The pass reads the last two passes' records alone, which is all the read gap,
`passes_since`, the not-run alert and the successor read.

The runs are read newest first, one page of them, completed ones alone, the pass's own run passed over, until two
records are found. A pass that uploaded none, as one that failed before its upload, is no record and is passed over.
One whose artifact is past its retention ends the reading, since every run before it is older still. What cannot be
read makes the records None, never fewer, and so does a page read through with fewer than two found while GitHub
counts more: the pass then waits the whole read gap and knows no chain (`controller/pass_.py`). Each record is handed
back as its JSON, oldest first; whether it is a `pass/1` is `controller/reads.previous_records`'s to say.

What started the pass is read from its own run, by its id, never from anything a dispatch carries (decision 0043): its
event, its actor by id and type, and its attempt.
"""
from __future__ import annotations

import json
import re

from adapters import artifacts
from adapters.github import PASSED, Unanswered, request

NAME = "pass"                 # the artifact the pass job uploads
MEMBER = "pass.json"          # its one file
HELD = 8 * 1024 * 1024        # bytes the file may be, as the zip says and as read out of it
WANTED = 2                    # the records read: the last two passes'
PAGE = 20                     # the runs read, newest first, to find them
EVENTS = {"schedule", "workflow_dispatch", "workflow_run"}
RUN_ID = re.compile(r"[1-9][0-9]{0,18}")


def _id(value) -> bool:
    return type(value) is int and value >= 1


def _repo(value):
    """The full name a run's repository object gives, or None for anything that is not one."""
    return value.get("full_name") if isinstance(value, dict) else None


def _is_pass(row, repo: str, branch: str, poller: str, own: int) -> bool:
    """Whether a listed run is a completed pass of this repo's poller from its default branch, other than this one."""
    path, _, ref = str(row.get("path", "")).partition("@")
    return (path == ".github/workflows/%s" % poller and ref in ("", "refs/heads/" + branch)
            and row.get("event") in EVENTS and row.get("head_branch") == branch and row.get("status") == "completed"
            and _repo(row.get("repository")) == repo
            and _repo(row.get("head_repository")) == repo and row.get("id") != own)


def _expired(seen: list) -> bool:
    """Whether the artifact list read, whole, lists the record past its retention."""
    listed = seen[-1]["body"].get("artifacts") if seen and isinstance(seen[-1].get("body"), dict) else None
    return isinstance(listed, list) and any(isinstance(a, dict) and a.get("expired") is True for a in listed)


def records(transport, repo: str, branch: str, poller: str, own: int):
    """The last two passes' records before the pass whose run GitHub numbers `own`, oldest first, as their JSON; None
    if they cannot be read."""
    try:
        answer = transport.send(request(
            "GET", "/repos/%s/actions/workflows/%s/runs?branch=%s&status=completed&per_page=%d"
            % (repo, poller, branch, PAGE), headers={"Cache-Control": "no-cache"}))
    except Unanswered:
        return None
    body = answer["body"] if answer["status"] == 200 and isinstance(answer["body"], dict) else {}
    listed, total = body.get("workflow_runs"), body.get("total_count")
    if not isinstance(listed, list) or type(total) is not int or total < len(listed):
        return None
    found = []
    for row in listed:
        if not isinstance(row, dict) or not _id(row.get("id")):
            return None
        if not _is_pass(row, repo, branch, poller, own):
            continue
        seen = []
        try:
            held, whole = artifacts.read(transport, repo, row["id"], seen.append, name=NAME, member=MEMBER,
                                         zipped_most=PASSED, held_most=HELD)
        except Unanswered:
            return None
        if not whole:
            return None
        if held is None:
            if _expired(seen):      # past its retention: every run before it is older still
                break
            continue
        try:
            record = json.loads(held.decode("utf-8"))
        except ValueError:
            return None
        found.append(record)
        if len(found) == WANTED:
            break
    else:
        if len(found) < WANTED and total > len(listed):
            return None
    return list(reversed(found))


def started(transport, repo: str, run_id):
    """The pass's own run, as `controller/pass_.started_by` reads it: `{"event", "actor": {"id", "type"} or None,
    "attempt"}`; None if it cannot be read, which `started_by` reads as a dispatch."""
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        return None
    try:
        answer = transport.send(request("GET", "/repos/%s/actions/runs/%s" % (repo, run_id)))
    except Unanswered:
        return None
    body = answer["body"] if answer["status"] == 200 and isinstance(answer["body"], dict) else {}
    actor = body.get("actor")
    if body.get("id") != int(run_id) or _repo(body.get("repository")) != repo \
            or not isinstance(body.get("event"), str) or not _id(body.get("run_attempt")):
        return None
    who = None
    if isinstance(actor, dict) and _id(actor.get("id")) and actor.get("type") in ("User", "Bot"):
        who = {"id": actor["id"], "type": actor["type"]}
    return {"event": body["event"], "actor": who, "attempt": body["run_attempt"]}
