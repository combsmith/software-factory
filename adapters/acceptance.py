"""Whether the issues a pull request closes ask for an acceptance contract, and the contract where one is asked
(design sections 3.13 and 4.8; decision 0047, the Maintainer's rule of 2026-10-21).

An issue asks for a contract only when its item's Intent is one that asks, `fix` or `implement`, or when a person adds
the `factory:contract` label to it. No Lifecycle runs an Intent that asks yet, so in slice 1 only the label asks. The
label is read as the Kernel reads a control label (`kernel/derive.py`'s `standing_labels`): it binds from when it is
added until a person removes it, so what a person placed only a person ends (L-17), and anyone else placing it again
changes nothing; a removal in the same second is read the way that asks. It asks only when a person, an account with
write access and no App acting for it, placed it (decision 0005). The issue's labels as GitHub lists them must agree
with its timeline: a label the timeline does not account for, renamed into the name or placed out of sight, is not read
whole.

A pull request to a base other than the repo's default branch carries no closing reference at all (P-33), so whether
its issue asks cannot be read: it is not whole. The closing references are read in one GraphQL read, `totalCount` and
each issue's number as P-33 and P-46 recorded them, with each issue's repo and labels, which no trial has recorded yet;
each closing issue's label events from its REST timeline, whole by its `link` header, as `adapters/timeline.py` reads a
pull request's. The list is whole only when it holds every reference it counts, once each, every one an issue of the
pull request's own repo.

Where no issue asks, `acceptance` is null and read whole. Where one asks, the contract is to be read, which
`adapters/contract.py`, not built, holds: until then the read is not whole, and the Kernel defers.

A pull request the Factory opens is bound to the issue it serves by its branch, `kernel/terms.py`'s `WORK_BRANCH`, never
by its body (issue 295): its author is the App of the Role that opens pull requests, and the ask is read from the issue
its branch names. Its closing references may leave that issue out, but they may name no other: one that does, a
branch of another shape or another repo, or an issue that is a pull request, is not read whole. A pull request a person
opens keeps the closing references' reading, which its author writes, so an author who removes "Closes" before a pass
removes the ask (decision 0047). Where the Role that opens pull requests is named but its App's account is not known, a
pull request on a branch of that shape cannot be told for a person's, and is not read whole. No Role opens one in slice 1,
so none is bound yet.

It is bound by the Run that opened it as well (issue 342): the opening Run's own `applied/1` names the pull request in
its `open_pull_request` Effect (`adapters/applied.opened`). Where a Run names it, the Run's issue and the branch's must
agree; two Runs that name it, a Run of another issue that names it, or any opening Run that cannot be read or has not
finished, of whatever issue, leave it not read whole. Where none names it, the branch alone binds it: the writer,
`apply`'s open Effect, lands in slice 2 with push, and once it does a pull request no Run names is not whole
(decision 0097).
"""
from __future__ import annotations

import re

from adapters import timeline
from adapters.github import Unanswered, request
from kernel import gate, terms

# The opener's account when the Role that opens pull requests is named but its App's account is not known.
UNTOLD = (0, "untold")
BRANCH = re.compile(terms.WORK_BRANCH)
PAGE = 10      # closing references on one page, as P-33 and P-46 asked them; more than one page is not read whole
LABELS = 50    # an issue's labels on one page; more is not read whole
QUERY = """query FactsClosing($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      closingIssuesReferences(first: %d) {
        totalCount
        nodes { number repository { nameWithOwner } labels(first: %d) { totalCount nodes { name } } }
      }
    }
  }
}""" % (PAGE, LABELS)


def closing(transport, pull: dict) -> tuple:
    """`{number: whether GitHub lists the label on it}` for each issue the pull request closes, and whether that list
    was read whole."""
    repo = pull["base"]["repo"]["full_name"]
    owner, name = repo.split("/")
    variables = {"owner": owner, "name": name, "number": pull["number"]}
    answer = transport.send(request("POST", "/graphql", body={"query": QUERY, "variables": variables}))
    if answer["status"] != 200 or not isinstance(answer["body"], dict) or answer["body"].get("errors"):
        raise Unanswered("the closing references' read answered %d" % answer["status"])
    pr = answer["body"]
    for key in ("data", "repository", "pullRequest"):
        pr = pr.get(key) if isinstance(pr, dict) else None
    if not isinstance(pr, dict):
        raise Unanswered("the closing references' read gave no pull request")
    refs = pr.get("closingIssuesReferences")
    nodes = refs.get("nodes") if isinstance(refs, dict) else None
    total = refs.get("totalCount") if isinstance(refs, dict) else None
    if not isinstance(nodes, list) or not isinstance(total, int) or isinstance(total, bool) or total != len(nodes):
        return {}, False
    found, whole = {}, True
    for node in nodes:
        number = node.get("number") if isinstance(node, dict) else None
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise Unanswered("a closing reference names no issue GitHub gives")
        owned = node["repository"].get("nameWithOwner") if isinstance(node.get("repository"), dict) else None
        labels = node.get("labels") if isinstance(node.get("labels"), dict) else {}
        names = labels.get("nodes") if isinstance(labels.get("nodes"), list) else None
        counted = labels.get("totalCount")
        if owned != repo or number in found or names is None or not isinstance(counted, int) \
                or isinstance(counted, bool) or counted != len(names) \
                or not all(isinstance(n, dict) and isinstance(n.get("name"), str) for n in names):
            whole = False
            continue
        found[number] = any(n["name"] == terms.LABEL_CONTRACT for n in names)
    return found, whole


def placed(events: list, accounts: timeline.Accounts):
    """Who placed the `factory:contract` label as it stands after the issue's timeline, as `standing_labels` reads a
    control label, or None where it does not stand. An act an App took with a person's token is no person's."""
    standing = None
    found = []
    for event in events:
        event = timeline._object(event, "the timeline")
        if event.get("event") not in timeline.LABELS:
            continue
        label = event.get("label") if isinstance(event.get("label"), dict) else {}
        if not isinstance(label.get("name"), str) or not label["name"]:
            raise Unanswered("a label event names no label")
        if label["name"] != terms.LABEL_CONTRACT:
            continue
        by = accounts.actor(event.get("actor"))
        person = gate.is_person(by) and not timeline.via_app(event)
        found.append((timeline._time(event.get("created_at")), event["event"] == "labeled", person))
    # In the order they happened; of two in the same second, the removal first, so the label is read as placed.
    for _, labeled, person in sorted(found, key=lambda f: (f[0], f[1])):
        if labeled:
            if not (standing is not None and standing and not person):
                standing = person
        elif person:
            standing = None
    return standing


def asks(transport, repo: str, number: int, listed: bool, accounts: timeline.Accounts) -> tuple:
    """Whether the issue asks for a contract by its label, a person's placement that stands; and whether that was read
    whole: its timeline read whole, and agreeing with whether GitHub lists the label on it."""
    events, whole = timeline.events(transport, {"number": number, "base": {"repo": {"full_name": repo}}})
    standing = placed(events, accounts)
    return standing is True, whole and (standing is not None) == listed


def labelled(transport, repo: str, number: int) -> bool:
    """Whether GitHub lists the `factory:contract` label on issue `number`; refused where it is no issue."""
    answer = transport.send(request("GET", "/repos/%s/issues/%d" % (repo, number)))
    body = answer["body"]
    if answer["status"] != 200 or not isinstance(body, dict) or body.get("number") != number:
        raise Unanswered("the bound issue answered %d" % answer["status"])
    labels = body.get("labels")
    if "pull_request" in body or not isinstance(labels, list) \
            or not all(isinstance(n, dict) and isinstance(n.get("name"), str) for n in labels):
        raise Unanswered("the bound issue is no issue whose labels can be read")
    return any(n["name"] == terms.LABEL_CONTRACT for n in labels)


def bound(pull: dict, opener, opened=None):
    """The issue a pull request is bound to by its branch and its opening Run: its number where `opener`, the account of
    the App that opens the Factory's pull requests, authored it; None where another account did, or no Role opens one;
    False where it cannot be read whole: the opener's on a branch of another shape or another repo, or, with the opener
    untold, any pull request on a branch of the Factory's shape, or where `opened`, what the opening Runs recorded, is
    not whole for it or names it for another issue, or twice."""
    if opener is None:
        return None
    head = pull.get("head") if isinstance(pull.get("head"), dict) else {}
    ref = head.get("ref")
    shaped = BRANCH.fullmatch(ref) if isinstance(ref, str) else None
    if opener == UNTOLD:
        return False if shaped else None
    user = pull.get("user") if isinstance(pull.get("user"), dict) else {}
    if (user.get("id"), user.get("type")) != tuple(opener):
        return None
    same = (head.get("repo") or {}).get("full_name") == pull["base"]["repo"]["full_name"]
    if not (shaped and same):
        return False
    issue = int(shaped.group(1))
    # An opening Run that cannot be read, of any issue, may be the one that opened this pull request on another issue's
    # branch: nothing the opener opened is read whole while one is.
    if not isinstance(opened, dict) or opened.get("whole") is not True or opened.get("unreadable"):
        return False
    named = opened.get("named", {}).get(pull.get("number"), [])
    if len(named) > 1 or any(served != issue for _, served in named):
        return False
    return issue


def _serving(transport, pull: dict, opener, opened) -> tuple:
    """`(found, issue, whole)`: what `closing` found, the issue the branch binds the pull request to or None, and whether
    those were read whole, which they are not where the base is not the default branch, whose pull requests carry no
    closing reference, or where the closing references name another issue than the bound one."""
    base = pull["base"]
    if not base.get("ref") or base.get("ref") != (base.get("repo") or {}).get("default_branch"):
        return {}, None, False
    issue = bound(pull, opener, opened)
    if issue is False:
        return {}, None, False
    found, whole = closing(transport, pull)
    if issue is not None and (not whole or any(number != issue for number in found)):
        return {}, None, False
    return found, issue, whole


def served(transport, pull: dict, opener=None, opened=None) -> tuple:
    """`(numbers, whole)`: the issues the pull request serves, in order, by the rule `read` holds it to."""
    found, issue, whole = _serving(transport, pull, opener, opened)
    return ([issue] if issue is not None else sorted(found)), whole


def read(transport, pull: dict, accounts: timeline.Accounts, opener=None, opened=None) -> tuple:
    """`(acceptance, whole)`: null and whole where no issue the pull request serves asks for a contract; null and not
    whole where one asks, where the issues cannot be read whole, or where the base is not the default branch, whose
    pull requests carry no closing reference to read. The issue it serves is the one its branch binds it to, where the
    opener's App opened it, and else the issues it closes."""
    repo = pull["base"]["repo"]["full_name"]
    found, issue, whole = _serving(transport, pull, opener, opened)
    if issue is not None:
        found = {issue: found[issue] if issue in found else labelled(transport, repo, issue)}
    for number, listed in found.items():
        asked, read_whole = asks(transport, repo, number, listed, accounts)
        if asked or not read_whole:
            return None, False
    return None, whole
