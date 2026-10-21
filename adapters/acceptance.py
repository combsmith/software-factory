"""Whether the issues a pull request closes ask for an acceptance contract, and the contract where one is asked
(design sections 3.13 and 4.8; decision 0046, the Maintainer's rule of 2026-10-21).

An issue asks for a contract only when its item's Intent is one `kernel/terms.py` names in `CONTRACT_INTENTS`, or when a
person adds the `factory:contract` label to it. No Lifecycle runs those Intents yet, so in slice 1 only the label asks:
the label as it stands after the issue's last event for it, a `labeled` by a person (decision 0005), never one an App or
the machine user added. A pull request that closes no issue asks for none.

The closing references are read in one GraphQL read, as P-33 and P-46 recorded them, and each closing issue's label
events from its REST timeline, whole by its `link` header, as `adapters/timeline.py` reads a pull request's. The list
is whole only when it holds every reference it counts, each an issue of the pull request's own repo: one in another repo
is read by no Factory App, and is not whole. Where no issue asks, `acceptance` is null and read whole. Where one asks,
the contract is to be read, which `adapters/contract.py`, not built, holds: until then the read is not whole, and the
Kernel defers.
"""
from __future__ import annotations

from adapters import timeline
from adapters.github import Unanswered, request
from kernel import terms

PAGE = 10    # closing references on one page, as P-33 and P-46 asked them; more than one page is not read whole
QUERY = """query FactsClosing($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      closingIssuesReferences(first: %d) { totalCount nodes { number repository { nameWithOwner } } }
    }
  }
}""" % PAGE


def closing(transport, pull: dict) -> tuple:
    """The numbers of the issues the pull request closes, and whether that list was read whole."""
    repo = pull["base"]["repo"]["full_name"]
    owner, name = repo.split("/")
    variables = {"owner": owner, "name": name, "number": pull["number"]}
    answer = transport.send(request("POST", "/graphql", body={"query": QUERY, "variables": variables}))
    if answer["status"] != 200 or not isinstance(answer["body"], dict) or answer["body"].get("errors"):
        raise Unanswered("the closing references' read answered %d" % answer["status"])
    pr = (((answer["body"].get("data") or {}).get("repository") or {}).get("pullRequest")) or {}
    refs = pr.get("closingIssuesReferences")
    nodes = refs.get("nodes") if isinstance(refs, dict) else None
    total = refs.get("totalCount") if isinstance(refs, dict) else None
    if not isinstance(nodes, list) or not isinstance(total, int) or isinstance(total, bool) or total != len(nodes):
        return [], False
    numbers, whole = [], True
    for node in nodes:
        number = node.get("number") if isinstance(node, dict) else None
        owned = ((node.get("repository") or {}).get("nameWithOwner") if isinstance(node, dict) else None)
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise Unanswered("a closing reference names no issue GitHub gives")
        if owned != repo:
            whole = False
            continue
        numbers.append(number)
    return numbers, whole and len(set(numbers)) == len(numbers)


def asks(transport, repo: str, number: int, accounts: timeline.Accounts) -> tuple:
    """Whether the issue asks for a contract by its label, as it stands after its last event for it, added by a person;
    and whether its timeline was read whole."""
    events, whole = timeline.events(transport, {"number": number, "base": {"repo": {"full_name": repo}}})
    labeled = [e for e in timeline.label_events(events, accounts) if e["label"] == terms.LABEL_CONTRACT]
    if not labeled:
        return False, whole
    last = labeled[-1]
    return last["action"] == "labeled" and last["by"]["kind"] == "human", whole


def read(transport, pull: dict, accounts: timeline.Accounts) -> tuple:
    """`(acceptance, whole)`: null and whole where no issue the pull request closes asks for a contract; null and not
    whole where one asks, or where the closing issues cannot be read whole."""
    numbers, whole = closing(transport, pull)
    repo = pull["base"]["repo"]["full_name"]
    for number in numbers:
        asked, read_whole = asks(transport, repo, number, accounts)
        if asked or not read_whole:
            return None, False
    return None, whole
