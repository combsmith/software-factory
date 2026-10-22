"""The checks on a pull request's head and its place in the merge queue, in one GraphQL read of the head's status
rollup (design section 3.3; P-32's read gives the shape).

Every check run the head's rollup lists is given with its name exactly as GitHub gives it, the id of the App that
reported it, the path of the workflow file that ran it, null where GitHub names none, its conclusion, or its status
while it has not concluded, in GitHub's own word, lower-cased, and when it completed; the port drops, merges and renames
none (decisions 0015, 0018, 0022, 0026). Whether the rollup itself keeps every check suite's run, and a re-run's alone
replaces an earlier one, is GitHub's, which P-42 asks. A status context, which is not a check run and names no App, is no
check. The list is whole only when its last page says there is no next one and every context it counts was read; read
over more than one page, only when every context carries its own id and none was read twice, since a rollup that moves
between pages can repeat one context and leave out another. A cursor that repeats, or pages past the count, end the read
short. Whether the pull request is in the merge queue is its entry, an object, or null: any other shape is refused. A
rollup of another commit than the head is refused, and so is one read while the pull request's head moved.

"""
from __future__ import annotations

import re

from adapters.github import Unanswered, request

PAGE = 100
TIME = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z")
WORD = re.compile(r"[A-Z_]+")
QUERY = """query FactsChecks($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      headRefOid
      mergeQueueEntry { position }
      commits(last: 1) {
        nodes {
          commit {
            oid
            statusCheckRollup {
              contexts(first: %d, after: $after) {
                totalCount
                pageInfo { hasNextPage endCursor }
                nodes {
                  __typename
                  ... on StatusContext { id }
                  ... on CheckRun {
                    id name conclusion status startedAt completedAt
                    checkSuite { app { databaseId } workflowRun { file { path } } }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}""" % PAGE


def check(node: dict) -> dict:
    """One check run as `facts/1` holds it; refused when any part GitHub gives cannot be read."""
    suite = node.get("checkSuite") if isinstance(node.get("checkSuite"), dict) else {}
    app = (suite.get("app") or {}).get("databaseId") if isinstance(suite.get("app"), dict) else None
    run = suite.get("workflowRun")
    file = run.get("file") if isinstance(run, dict) else None
    if not (run is None or isinstance(run, dict)) or not (file is None or isinstance(file, dict)):
        raise Unanswered("a check run's workflow run cannot be read")
    path = file.get("path") if isinstance(file, dict) else None
    name, status, conclusion, done = node.get("name"), node.get("status"), node.get("conclusion"), node.get("completedAt")
    if not isinstance(name, str) or not name or not isinstance(app, int) or isinstance(app, bool) or app < 1:
        raise Unanswered("a check run's name or App cannot be read")
    if path is not None and (not isinstance(path, str) or not path):
        raise Unanswered("a check run's workflow file cannot be read")
    word = conclusion if conclusion is not None else status
    if not isinstance(word, str) or not WORD.fullmatch(word):
        raise Unanswered("a check run's conclusion and status cannot be read")
    if done is not None and not (isinstance(done, str) and TIME.fullmatch(done)):
        raise Unanswered("a check run's completion time cannot be read")
    if (conclusion is None) != (done is None):
        raise Unanswered("a check run that concluded with no time, or has a time and no conclusion")
    return {"name": name, "app_id": app, "workflow": path, "conclusion": word.lower(), "completed_at": done}


def read(transport, pull: dict, kept=None) -> dict:
    """The head's check runs and whether they were read whole, whether the pull request is in the merge queue, and
    every page is of the head the pull request's first read named. `kept`, where given, keeps each check run's node as
    GitHub gave it, and the same whole, for reconciliation (`adapters/seen.py`)."""
    runs = []
    found = _read(transport, pull, runs)
    if kept is not None:
        kept["check_runs"] = (runs, found["complete"])
    return found


def _read(transport, pull: dict, runs: list) -> dict:
    owner, name = pull["base"]["repo"]["full_name"].split("/")
    found, after, queue, seen, total, ids, cursors = [], None, None, 0, None, [], set()
    while True:
        variables = {"owner": owner, "name": name, "number": pull["number"], "after": after}
        answer = transport.send(request("POST", "/graphql", body={"query": QUERY, "variables": variables}))
        if answer["status"] != 200 or not isinstance(answer["body"], dict) or answer["body"].get("errors"):
            raise Unanswered("the checks' read answered %d" % answer["status"])
        pr = (((answer["body"].get("data") or {}).get("repository") or {}).get("pullRequest")) or {}
        nodes = ((pr.get("commits") or {}).get("nodes")) or []
        commit = (nodes[0] or {}).get("commit") if len(nodes) == 1 and isinstance(nodes[0], dict) else None
        if not isinstance(commit, dict) or commit.get("oid") != pull["head"]["sha"]:
            raise Unanswered("the checks were read of another commit than the head")
        if pr.get("headRefOid") != pull["head"]["sha"]:
            raise Unanswered("the pull request's head moved while its checks were read")
        entry = pr.get("mergeQueueEntry", False)
        if not (entry is None or isinstance(entry, dict)):
            raise Unanswered("the pull request's place in the merge queue cannot be read")
        queue = entry is not None
        rollup = commit.get("statusCheckRollup")
        if rollup is None:
            return {"checks": found, "complete": after is None, "queue": queue}
        contexts = rollup.get("contexts") if isinstance(rollup, dict) else None
        page = (contexts or {}).get("pageInfo") if isinstance(contexts, dict) else None
        if not isinstance(contexts, dict) or not isinstance(contexts.get("nodes"), list) or not isinstance(page, dict):
            return {"checks": found, "complete": False, "queue": queue}
        counted = contexts.get("totalCount")
        total = counted if total is None else total
        for node in contexts["nodes"]:
            if not isinstance(node, dict):
                raise Unanswered("a check of the rollup is not one GitHub gives")
            seen += 1
            ids.append(node.get("id"))
            if node.get("__typename") == "CheckRun":
                found.append(check(node))
                runs.append(node)
            elif node.get("__typename") != "StatusContext":
                raise Unanswered("a context GitHub does not give: %r" % (node.get("__typename"),))
        if page.get("hasNextPage") is False:
            whole = isinstance(total, int) and not isinstance(total, bool) and counted == total and seen == total
            if after is not None:
                whole = whole and all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(ids)
            return {"checks": found, "complete": whole, "queue": queue}
        if page.get("hasNextPage") is not True or not isinstance(page.get("endCursor"), str) or not page["endCursor"]:
            return {"checks": found, "complete": False, "queue": queue}
        if page["endCursor"] in cursors or not isinstance(total, int) or isinstance(total, bool) or seen >= total:
            return {"checks": found, "complete": False, "queue": queue}
        cursors.add(page["endCursor"])
        after = page["endCursor"]
