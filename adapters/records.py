"""The records port: the Factory's own run records, as the Kernel reads them (design section 3.10, decision 0036).

A record counts only if it is a run of one of the Factory's own Role workflow files, in the Factory repo, from its
default branch, started by a dispatch the pass job's own token made (P-9; decision 0051): a Role's Runs are
dispatched, never scheduled, and a run of any other workflow, branch, repo, event or dispatcher, a fork's pull
request and a person's dispatch among them, is never a Run (decision 0003, I-34). Which item a counted Run is on, its Intent, its Role, its content and its id come
from its run-name alone, `run-name/1`, and the item's type from the Intent. A counted record whose name is not yet a
run-name is unidentified: it is reported by its GitHub id, never dropped, and the list is read once more 5 s later, so
that only what is still unnamed then is reported (decision 0036, rulings 1 and 3).

Every read of the list asks GitHub for the default branch's dispatches alone and sends `Cache-Control: no-cache`, and
keeps the answer's `date` and `age` for the pass record, which never reach the Kernel (ruling 4). The list is whole
only when every page was read, each run once, as many as the count GitHub gives, with every row readable and every
counted run's outcome read (L-53). A Run that did not succeed has its outcome read from its artifact by
`adapters/artifacts.py`, once the list is final, and for no other Run (decisions 0039 and 0049): one it cannot read
leaves the list not whole, so that no failed Run is ever read as no attempt.
"""
from __future__ import annotations

import datetime
import re
import time

from adapters import artifacts
from adapters.github import Unanswered, request
from kernel import issue
from kernel import terms

PAGE = 100           # runs on one page of a workflow's list
SERVED = 1000        # the most of a list's runs GitHub serves, however many it counts (L-53)
WAIT = 5             # seconds before the one second read of a list holding an unidentified Run (decision 0036)
NAME = re.compile(r"sf ([A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100})#([1-9][0-9]{0,8}) ([a-z][a-z-]{0,60}[a-z]) "
                  r"([a-z][a-z-]{0,60}[a-z]) (sha256:[0-9a-f]{4,64}) (r_[0-9A-Z]{6,26})")
# The Intents a pull request's Runs carry, as kernel/decide.py admits them, and an issue's, as kernel/issue.py does.
# A name with any other Intent cannot be placed on an item: its row cannot be read.
ON_PULL_REQUEST = {"review-change", "fix-findings", "adjudicate-findings", terms.ISSUE_APPROVAL}
# GitHub's words for a run that has not started, and how each ends, as the run record holds them. A Run whose job never
# started, `startup_failure`, ran no Role and left no outcome: it is read as `cancelled`, no attempt, and the Run ceiling
# bounds it (decision 0049, issue 286), never as `failure`, which with no outcome is an attempt.
NOT_STARTED = {"queued", "waiting", "requested", "pending"}
CONCLUSIONS = {"success": "success", "failure": "failure", "startup_failure": "cancelled", "cancelled": "cancelled",
               "timed_out": "timed_out"}
FRESH = {"Cache-Control": "no-cache"}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
HTTP_DATE = re.compile(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun), ([0-9]{2}) ([A-Z][a-z]{2}) ([0-9]{4}) "
                       r"([0-9]{2}:[0-9]{2}:[0-9]{2}) GMT")


def named(name: str):
    """A run-name read into the run record's item, Intent, Role, content id and Run id, or None if it is not one, or
    names an Intent no Lifecycle runs. An issue's Intents run on an issue, a pull request's on a pull request."""
    found = NAME.fullmatch(name) if isinstance(name, str) else None
    if not found:
        return None
    repo, number, intent, role, content, run = found.groups()
    if any(part in (".", "..") for part in repo.split("/")):
        return None
    kind = "issue" if intent in issue.INTENTS else "pull_request" if intent in ON_PULL_REQUEST else None
    if kind is None:
        return None
    return {"run": run, "item": {"repo": repo, "type": kind, "number": int(number)}, "intent": intent, "role": role,
            "content_id": content}


def _http_date(text: str) -> str:
    """An HTTP date, as RFC 1123 writes it, in the pass record's form; read by hand, so no locale can change it."""
    found = HTTP_DATE.fullmatch(text) if isinstance(text, str) else None
    if not found or found.group(3) not in MONTHS:
        raise Unanswered("a read of the run records has no date that can be read")
    _, day, month, year, clock = found.groups()
    when = "%s-%02d-%sT%sZ" % (year, MONTHS.index(month) + 1, day, clock)
    try:
        datetime.datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise Unanswered("a read of the run records has no date that can be read") from None
    return when


def _read_at(answer: dict) -> dict:
    """The answer's date and age, as the pass record keeps them; one that cannot be read is refused."""
    headers = answer.get("headers") or {}
    age = str(headers.get("age", "0"))
    if not age.isdigit() or not age.isascii():
        raise Unanswered("a read of the run records has an age that is not a count of seconds")
    return {"read": "runs", "date": _http_date(headers.get("date")), "age": int(age)}


def _list(transport, repo: str, workflow: str, branch: str, per_page: int) -> tuple:
    """Every dispatch of one workflow file from the default branch, page by page, each read uncached; whole only if
    every run counted was read, once each, and the count did not change while the pages were read."""
    base = "/repos/%s/actions/workflows/%s/runs?branch=%s&event=workflow_dispatch&per_page=%d" % (
        repo, workflow, branch, per_page)
    rows, reads, page, count, whole = [], [], 1, None, True
    while True:
        answer = transport.send(request("GET", base if page == 1 else "%s&page=%d" % (base, page), headers=FRESH))
        if answer["status"] != 200 or not isinstance(answer["body"], dict):
            raise Unanswered("the runs of %s answered %d" % (workflow, answer["status"]))
        reads.append(_read_at(answer))
        listed, total = answer["body"].get("workflow_runs"), answer["body"].get("total_count")
        if not isinstance(listed, list) or not isinstance(total, int) or isinstance(total, bool) or total < 0:
            return rows, reads, False
        count = total if count is None else count
        whole = whole and total == count
        rows += listed
        if not listed or len(rows) >= count or len(listed) < per_page or len(rows) >= SERVED:
            break
        page += 1
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    whole = whole and len(rows) == count and len(set(ids)) == len(rows)
    return rows, reads, whole


def _record(row: dict, repo: str, branch: str, roles: set, dispatcher: tuple):
    """`(record, unidentified)` for one listed run: a record for a counted run its name names, its id, its record's
    creation and its status for a counted run its name does not yet, and neither for a run that does not count. None
    for a row that cannot be read."""
    if not isinstance(row, dict) or not isinstance(row.get("id"), int) or isinstance(row.get("id"), bool):
        return None
    path, _, ref = str(row.get("path", "")).partition("@")
    actor = row.get("actor") if isinstance(row.get("actor"), dict) else {}
    counted = (path in roles and ref in ("", "refs/heads/" + branch) and row.get("event") == "workflow_dispatch"
               and row.get("head_branch") == branch
               and (row.get("repository") or {}).get("full_name") == repo
               and (row.get("head_repository") or {}).get("full_name") == repo
               and (actor.get("id"), actor.get("type")) == dispatcher)
    if not counted:
        return (None, None)
    status = row.get("status")
    status = "queued" if status in NOT_STARTED else status
    if status not in ("queued", "in_progress", "completed"):
        return None
    parts = named(row.get("name"))
    if parts is None:
        # Its record's creation and its status, from which the Kernel reads how long it has gone unnamed and whether
        # it may be running on an item now (issue 270).
        created = row.get("created_at")
        try:
            datetime.datetime.strptime(str(created), "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None
        return (None, {"run": str(row["id"]), "created_at": created, "status": status})
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


def runs(transport, repo: str, branch: str, workflows: list, dispatcher: tuple, per_page: int = PAGE,
         sleep=time.sleep) -> dict:
    """The run records of the Factory's Role workflows, the ids of counted Runs not yet named, whether the list was
    read whole, and each read's date and age for the pass record. `dispatcher` is the pass job's own token's account,
    by its id and type, `(id, "Bot")`: only a run it dispatched is a Run.

    `outcome` is the fault a completed Run that did not succeed names in its artifact, and null on every other record
    and on one that left none."""
    roles = {".github/workflows/%s" % name for name in workflows}

    def read() -> tuple:
        records, unnamed, reads, whole, failed = [], [], [], True, []
        for workflow in workflows:
            rows, got, complete = _list(transport, repo, workflow, branch, per_page)
            reads += got
            whole = whole and complete
            for row in rows:
                found = _record(row, repo, branch, roles, dispatcher)
                if found is None:
                    whole = False
                    continue
                record, unidentified = found
                if record is not None:
                    records.append(record)
                    if record["status"] == "completed" and record["conclusion"] != "success":
                        failed.append((record, row["id"]))
                if unidentified is not None:
                    unnamed.append(unidentified)
        return records, unnamed, reads, whole, failed

    records, unnamed, reads, whole, failed = read()
    if unnamed:
        sleep(WAIT)
        records, unnamed, again, whole, failed = read()
        reads += again
    for record, github_id in failed:
        record["outcome"], read_whole = artifacts.outcome(transport, repo, github_id, record["run"])
        whole = whole and read_whole
    return {"runs": records, "unidentified": unnamed, "complete": whole, "reads": reads}
