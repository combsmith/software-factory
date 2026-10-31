"""What the release workflow reads of a commit a Channel may move to, through the one transport (decision 0044; #197's
rulings 4, 4″ and 4′): whether it is on `main`, whether `verify` concluded success on it, and the eval gate's word on it
for the Release asked. It hands `release/cut.py` its facts, `{commit, on_main, verified, gate, release}`, and decides
nothing: the rules are the cut's, and the verdict the eval job's own, `harness.eval.verdict`.

Each fact fails closed. A comparison that cannot be read is not on `main`, read by its branch's ref; a `verify` that cannot be read, or that more
than one App reports, did not pass. A `verify` counts only as the Kernel's `verify` Lens is read: its check, from
GitHub Actions, run by the workflow file `.github/workflows/verify.yml` (`config/defaults.json`, P-35), read here by
the check run's suite's one workflow run; any other workflow's job of that name is no `verify` (decision 0080). The gate reads the eval job's one successful dispatch on the commit, its
`eval-report` artifact, and the set's manifest at that commit, through the transport, never a file of the checkout. Any
of them not read whole, and any verdict but `pass`, closes the gate with its code, which `cut.plan` reads as
`eval_gate_closed`. Nothing here executes a file of the commit."""
from __future__ import annotations

import base64
import json
import re

from adapters import artifacts
from adapters.checks import ACTIONS_APP, own_job      # GitHub Actions, the one App whose `verify` counts
from adapters.github import STORED, Unanswered, request
from harness import eval as eval_gate
from release import cut

VERIFY = "verify"                   # the check run `verify.yml`'s job reports, on the merge group main took
VERIFY_WORKFLOW = ".github/workflows/verify.yml"    # the one workflow whose `verify` counts, as the Kernel's Lens reads it
EVAL_WORKFLOW = "eval.yml"
REPORT, MEMBER = "eval-report", "eval-report.json"
SET = "evals/pr-review/cases.json"
SET_MOST = 1024 * 1024              # bytes the manifest may be; GitHub inlines a file's content to 1 MiB
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}")
UNREAD = "report_unreadable"        # the gate's word for what was not read whole
ON_MAIN = ("ahead", "identical")    # the commit compared with main: main is it, or is after it


def _repo(repo) -> bool:
    return isinstance(repo, str) and REPO.fullmatch(repo) is not None and repo.split("/")[1] not in (".", "..")


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def on_main(transport, repo: str, commit: str, branch: str = "main") -> bool:
    """Whether `commit` is the head of `branch` or one of its ancestors: the branch's head read by its ref, never a name
    a tag could share, then GitHub's comparison of the commit with that head."""
    try:
        answer = transport.send(request("GET", "/repos/%s/git/ref/heads/%s" % (repo, branch)))
        head = _dict(_dict(answer["body"]).get("object")) if answer["status"] == 200 else {}
        if _dict(answer["body"]).get("ref") != "refs/heads/" + branch or head.get("type") != "commit" \
                or not cut.sha(head.get("sha")):
            return False
        answer = transport.send(request("GET", "/repos/%s/compare/%s...%s?per_page=1" % (repo, commit, head["sha"])))
    except Unanswered:
        return False
    body = _dict(answer["body"])
    return answer["status"] == 200 and body.get("status") in ON_MAIN \
        and _dict(body.get("merge_base_commit")).get("sha") == commit


def verified(transport, repo: str, commit: str) -> bool:
    """Whether GitHub Actions' one `verify` check run on `commit`, the latest of its name, concluded success, and was run
    by `verify.yml`: its check suite's one workflow run, read by the suite's id, is of that file and that commit, and its
    details are that run's own job's (decision 0104)."""
    try:
        answer = transport.send(request("GET", "/repos/%s/commits/%s/check-runs?check_name=%s&filter=latest&per_page=100"
                                        % (repo, commit, VERIFY)))
    except Unanswered:
        return False
    body = answer["body"]
    runs = body.get("check_runs") if answer["status"] == 200 and isinstance(body, dict) else None
    if not isinstance(runs, list) or body.get("total_count") != len(runs):
        return False
    ours = [r for r in runs if isinstance(r, dict) and r.get("name") == VERIFY]
    if len(ours) != 1 or len(runs) != 1 or _dict(ours[0].get("app")).get("id") != ACTIONS_APP:
        return False
    if not (ours[0].get("head_sha") == commit and ours[0].get("status") == "completed"
            and ours[0].get("conclusion") == "success"):
        return False
    suite = _dict(ours[0].get("check_suite")).get("id")
    if type(suite) is not int or suite < 1:
        return False
    try:
        answer = transport.send(request("GET", "/repos/%s/actions/runs?check_suite_id=%d&per_page=100" % (repo, suite)))
    except Unanswered:
        return False
    body = answer["body"]
    runs = body.get("workflow_runs") if answer["status"] == 200 and isinstance(body, dict) else None
    if not isinstance(runs, list) or body.get("total_count") != len(runs) or len(runs) != 1 \
            or not isinstance(runs[0], dict):
        return False
    return runs[0].get("path") == VERIFY_WORKFLOW and runs[0].get("head_sha") == commit \
        and runs[0].get("check_suite_id") == suite \
        and own_job(ours[0].get("details_url"), ours[0].get("id"), runs[0].get("id"))


def _manifest(transport, repo: str, commit: str):
    """The set's manifest at `commit`, as `harness.eval.held` reads it, or None."""
    try:
        answer = transport.send(request("GET", "/repos/%s/contents/%s?ref=%s" % (repo, SET, commit)))
    except Unanswered:
        return None
    body = answer["body"]
    if answer["status"] != 200 or not isinstance(body, dict) or body.get("type") != "file" or body.get("path") != SET \
            or body.get("encoding") != "base64" or not isinstance(body.get("content"), str) \
            or type(body.get("size")) is not int or not 0 <= body["size"] <= SET_MOST:
        return None
    try:
        data = base64.b64decode(body["content"].replace("\n", ""), validate=True)
        return eval_gate.held(data) if len(data) == body["size"] else None
    except (ValueError, eval_gate.Stop):
        return None


def _run(transport, repo: str, commit: str):
    """The GitHub id of the eval job's one successful dispatch on `commit`, or None."""
    try:
        answer = transport.send(request("GET", "/repos/%s/actions/workflows/%s/runs?head_sha=%s&event=workflow_dispatch"
                                               "&status=success&per_page=100" % (repo, EVAL_WORKFLOW, commit)))
    except Unanswered:
        return None
    body = answer["body"]
    runs = body.get("workflow_runs") if answer["status"] == 200 and isinstance(body, dict) else None
    if not isinstance(runs, list) or body.get("total_count") != len(runs):
        return None
    done = [r for r in runs if isinstance(r, dict) and r.get("head_sha") == commit and r.get("conclusion") == "success"
            and r.get("event") == "workflow_dispatch" and r.get("path") == ".github/workflows/%s" % EVAL_WORKFLOW]
    if len(done) != len(runs) or not done:
        return None
    ident = max(done, key=lambda r: r.get("run_number") if type(r.get("run_number")) is int else -1).get("id")
    return ident if type(ident) is int and ident > 0 else None


def gate(transport, repo: str, commit: str, release: str) -> str:
    """The eval gate's word on `commit` for `release`: `pass`, or the code that keeps it closed."""
    found = _manifest(transport, repo, commit)
    if found is None:
        return "eval_set_unreadable"
    ident = _run(transport, repo, commit)
    if ident is None:
        return "eval_not_run"
    try:
        data, whole = artifacts.read(transport, repo, ident, name=REPORT, member=MEMBER, zipped_most=STORED,
                                     held_most=STORED)
        document = json.loads(data.decode("utf-8")) if whole and data is not None else None
        if document is None:
            return UNREAD
        return eval_gate.verdict(document, found[0], found[1], commit, release)
    except (Unanswered, ValueError, RecursionError):
        return UNREAD


def facts(transport, repo: str, commit, release, branch: str = "main") -> dict:
    """The facts `cut.plan` reads of the commit asked about. Nothing is asked of a commit or repo that is not one."""
    if not (cut.sha(commit) and _repo(repo)):
        return {"commit": commit, "on_main": False, "verified": False, "gate": UNREAD, "release": release}
    return {"commit": commit, "on_main": on_main(transport, repo, commit, branch),
            "verified": verified(transport, repo, commit),
            "gate": gate(transport, repo, commit, release), "release": release}
