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

The known limit: the closing references are the pull request's own, which its author writes, so an author who removes
"Closes" before a pass removes the ask (decision 0047).
"""
from __future__ import annotations

from adapters import timeline
from adapters.github import Unanswered, request
from kernel import gate, terms

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
        person = gate.is_person(by) and not event.get("performed_via_github_app")
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


def read(transport, pull: dict, accounts: timeline.Accounts) -> tuple:
    """`(acceptance, whole)`: null and whole where no issue the pull request closes asks for a contract; null and not
    whole where one asks, where the closing issues cannot be read whole, or where the base is not the default branch,
    whose pull requests carry no closing reference to read."""
    base = pull["base"]
    if not base.get("ref") or base.get("ref") != (base.get("repo") or {}).get("default_branch"):
        return None, False
    found, whole = closing(transport, pull)
    for number, listed in found.items():
        asked, read_whole = asks(transport, base["repo"]["full_name"], number, listed, accounts)
        if asked or not read_whole:
            return None, False
    return None, whole
