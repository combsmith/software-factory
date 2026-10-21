"""The records port: the Factory's own run records, as the Kernel reads them (design section 3.10, decision 0036).

A record counts only if it is a run of one of the Factory's own Role workflow files, in the Factory repo, from its
default branch, started by a dispatch: a Role's Runs are dispatched, never scheduled, and a run of any other workflow,
another branch, another repo or another event, a fork's pull request among them, is never a Run (decision 0003, I-34).
Which item a counted Run is on, its Intent, its Role, its content and its id come from its run-name alone, `run-name/1`.
A counted record whose name is not yet a run-name is unidentified: it is reported by its GitHub id, never dropped, and
the list is read once more 5 s later, so that only what is still unnamed then is reported (decision 0036, rulings 1, 3).

Every read of the list sends `Cache-Control: no-cache`, and keeps the answer's `date` and `age` for the pass record,
which never reach the Kernel (ruling 4). A list read short is unreadable: `complete` is false when the pages end short
of the count GitHub gives, or when the count is more than GitHub will serve (L-53).
"""
from __future__ import annotations

import datetime
import re
import time

from adapters.github import Unanswered, request
from kernel import issue

PAGE = 100           # runs on one page of a workflow's list
SERVED = 1000        # the most of a list's runs GitHub serves, however many it counts (L-53)
WAIT = 5             # seconds before the one second read of a list holding an unidentified Run (decision 0036)
NAME = re.compile(r"^sf ([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([1-9][0-9]*) ([a-z][a-z-]*[a-z]) ([a-z][a-z-]*[a-z]) "
                  r"(sha256:[0-9a-f]{4,64}) (r_[0-9A-Z]{6,26})$")
# GitHub's words for a run that has not started, and how each ends, as the run record holds them.
NOT_STARTED = {"queued", "waiting", "requested", "pending"}
CONCLUSIONS = {"success": "success", "failure": "failure", "startup_failure": "failure", "cancelled": "cancelled",
               "timed_out": "timed_out"}
FRESH = {"Cache-Control": "no-cache"}
WHEN = "%a, %d %b %Y %H:%M:%S GMT"


def named(name: str):
    """A run-name read into the run record's item, Intent, Role, content id and Run id, or None if it is not one.
    The item's type is the Intent's: the issue Lifecycle's Intents run on an issue, every other on a pull request."""
    found = NAME.match(name) if isinstance(name, str) else None
    if not found:
        return None
    repo, number, intent, role, content, run = found.groups()
    kind = "issue" if intent in issue.INTENTS else "pull_request"
    return {"run": run, "item": {"repo": repo, "type": kind, "number": int(number)}, "intent": intent, "role": role,
            "content_id": content}


def _read_at(answer: dict) -> dict:
    """The answer's date and age, as the pass record keeps them; one that cannot be read is refused."""
    headers = answer.get("headers") or {}
    try:
        date = datetime.datetime.strptime(str(headers.get("date", "")), WHEN).strftime("%Y-%m-%dT%H:%M:%SZ")
        age = int(str(headers.get("age", "0")))
    except ValueError:
        raise Unanswered("a read of the run records has no date or age that can be read") from None
    if age < 0:
        raise Unanswered("a read of the run records has an age below zero")
    return {"read": "runs", "date": date, "age": age}


def _list(transport, repo: str, workflow: str, per_page: int) -> tuple:
    """Every run of one workflow file, page by page, each read uncached; whole only if every run counted was read."""
    base = "/repos/%s/actions/workflows/%s/runs?per_page=%d" % (repo, workflow, per_page)
    rows, reads, page, count = [], [], 1, None
    while True:
        answer = transport.send(request("GET", base if page == 1 else "%s&page=%d" % (base, page), headers=FRESH))
        if answer["status"] != 200 or not isinstance(answer["body"], dict):
            raise Unanswered("the runs of %s answered %d" % (workflow, answer["status"]))
        reads.append(_read_at(answer))
        listed, total = answer["body"].get("workflow_runs"), answer["body"].get("total_count")
        if not isinstance(listed, list) or not isinstance(total, int) or isinstance(total, bool) or total < 0:
            return rows, reads, False
        count = total if count is None else count
        rows += listed
        if not listed or len(rows) >= count or len(listed) < per_page or len(rows) >= SERVED:
            break
        page += 1
    whole = total == count and len(rows) == count
    return rows, reads, whole


def _record(row: dict, repo: str, branch: str, roles: set):
    """`(record, unidentified id)` for one listed run: a record for a counted run its name names, its id for a counted
    run its name does not yet, and neither for a run that does not count. None for a row that cannot be read."""
    if not isinstance(row, dict) or not isinstance(row.get("id"), int):
        return None
    path = str(row.get("path", "")).split("@")[0]
    counted = (path in roles and row.get("event") == "workflow_dispatch" and row.get("head_branch") == branch
               and (row.get("repository") or {}).get("full_name") == repo
               and (row.get("head_repository") or {}).get("full_name") == repo)
    if not counted:
        return (None, None)
    parts = named(row.get("name"))
    if parts is None:
        return (None, row["id"])
    status = row.get("status")
    status = "queued" if status in NOT_STARTED else status
    if status not in ("queued", "in_progress", "completed"):
        return None
    conclusion = row.get("conclusion")
    if status == "completed":
        if conclusion not in CONCLUSIONS:
            return None
        conclusion = CONCLUSIONS[conclusion]
    elif conclusion is not None:
        return None
    started = row.get("run_started_at") or row.get("created_at")
    try:
        datetime.datetime.strptime(str(started), "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return (dict(parts, status=status, conclusion=conclusion, outcome=None, started_at=started), None)


def runs(transport, repo: str, branch: str, workflows: list, per_page: int = PAGE, sleep=time.sleep) -> dict:
    """The run records of the Factory's Role workflows, the ids of counted Runs not yet named, whether the list was
    read whole, and each read's date and age for the pass record.

    `outcome` is null on every record: reading `outcome.json` for a Run that did not succeed needs the artifact's
    download, which GitHub serves by a redirect off its API, and the transport follows none (decision 0044); it waits
    on `adapters/artifacts.py`."""
    roles = {".github/workflows/%s" % name for name in workflows}

    def read() -> tuple:
        records, unnamed, reads, whole = [], [], [], True
        for workflow in workflows:
            rows, got, complete = _list(transport, repo, workflow, per_page)
            reads += got
            whole = whole and complete
            for row in rows:
                found = _record(row, repo, branch, roles)
                if found is None:
                    whole = False
                    continue
                record, unidentified = found
                if record is not None:
                    records.append(record)
                if unidentified is not None:
                    unnamed.append(unidentified)
        return records, unnamed, reads, whole

    records, unnamed, reads, whole = read()
    if unnamed:
        sleep(WAIT)
        records, unnamed, again, whole = read()
        reads += again
    return {"runs": records, "unidentified": [str(i) for i in unnamed], "complete": whole, "reads": reads}
