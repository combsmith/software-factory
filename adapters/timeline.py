"""The facts a pull request's timeline and reviews give: who acted, of what kind and with what access, every label
event, every review with who dismissed it and what it was before, when a person with write access last acted, and how
many acts the Factory has made since (design section 3.3, decision 0003).

An actor's kind comes from GitHub's account type and the configuration the caller gives, never from a name's spelling
(decision 0005, L-57): `machine_user` is the User named as the approver and no other; `lens` is a Bot the caller names
as a Lens's App, read as that Lens's name; any other Bot is `app`; any other User is `human`. Write access is a
person's alone, read from the repository's collaborator permission, `admin`, `maintain` or `write`, never `triage`,
once a login for the snapshot and never from an association (the Maintainer's ruling on #222). A User whose login ends
`[bot]`, or a kind that contradicts the configuration, is refused: the read was wrong.

The timeline and the reviews are read page by page, and each says whether it was read whole. No text of GitHub's
reaches a part: a review's body, a dismissal's message and a comment are never read into one.
"""
from __future__ import annotations

import datetime
import hashlib
import re
import urllib.parse

from adapters.github import DIFF, Unanswered, raw, request

PAGE = 100
WRITE = {"admin", "maintain", "write"}
PERMISSIONS = WRITE | {"triage", "read", "none"}
STATES = {"APPROVED": "approved", "CHANGES_REQUESTED": "changes_requested", "COMMENTED": "commented",
          "DISMISSED": "dismissed"}
BEFORE = {"approved", "changes_requested", "commented"}
SHA = re.compile(r"^[0-9a-f]{40}$")
# The acts that move work on, which the act ceiling counts when a Factory identity made them (decision 0003).
QUEUE = {"added_to_merge_queue", "removed_from_merge_queue"}
LABELS = {"labeled", "unlabeled"}
# What an actor on the timeline did themselves. `mentioned` and `subscribed` name whom an act touched, not who acted,
# and `committed` names a commit's author, which whoever makes the commit writes: none is anyone's action.
ACTIONS = LABELS | QUEUE | {"commented", "reviewed", "review_dismissed", "review_requested", "review_request_removed",
                            "head_ref_force_pushed", "head_ref_restored", "ready_for_review", "convert_to_draft",
                            "closed", "reopened", "merged", "renamed", "assigned", "unassigned", "locked", "unlocked"}


def _time(value) -> str:
    try:
        datetime.datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise Unanswered("a time on the timeline cannot be read") from None
    return value


class Accounts:
    """Who an actor is, read once a login for one snapshot: its kind, its name and whether it can write."""

    def __init__(self, transport, repo: str, approver: str, lenses: dict):
        self.transport, self.repo, self.approver, self.lenses = transport, repo, approver, dict(lenses)
        self.access = {}

    def _can_write(self, login: str) -> bool:
        if login not in self.access:
            path = "/repos/%s/collaborators/%s/permission" % (self.repo, urllib.parse.quote(login, safe=""))
            answer = self.transport.send(request("GET", path))
            if answer["status"] == 404:
                level = "none"
            elif answer["status"] == 200 and isinstance(answer["body"], dict):
                level = answer["body"].get("permission")
            else:
                raise Unanswered("the permission of %s answered %d" % (login, answer["status"]))
            if level not in PERMISSIONS:
                raise Unanswered("a permission GitHub does not give: %r" % (level,))
            self.access[login] = level in WRITE
        return self.access[login]

    def actor(self, raw_actor) -> dict:
        """`{kind, name, can_write}` for a GitHub user object; refused when it cannot be read or contradicts itself."""
        if not isinstance(raw_actor, dict):
            raise Unanswered("an actor cannot be read")
        login, ident, kind = raw_actor.get("login"), raw_actor.get("id"), raw_actor.get("type")
        if not isinstance(login, str) or not login or not isinstance(ident, int) or isinstance(ident, bool) \
                or kind not in ("User", "Bot"):
            raise Unanswered("an actor cannot be read")
        if kind == "Bot":
            if (ident, kind) in self.lenses:
                return {"kind": "lens", "name": self.lenses[(ident, kind)], "can_write": False}
            return {"kind": "app", "name": login, "can_write": False}
        if login.endswith("[bot]"):
            raise Unanswered("a User whose login ends [bot]: GitHub gives no User a bracket, so the read was wrong")
        if login == self.approver:
            return {"kind": "machine_user", "name": login, "can_write": False}
        return {"kind": "human", "name": login, "can_write": self._can_write(login)}


def _pages(transport, path: str) -> tuple:
    """Every item of a list read page by page; whole only when a page came back short of a full one."""
    items, page = [], 1
    while True:
        answer = transport.send(request("GET", path if page == 1 else "%s&page=%d" % (path, page)))
        if answer["status"] != 200:
            raise Unanswered("%s answered %d" % (path.split("?")[0], answer["status"]))
        if not isinstance(answer["body"], list):
            return items, False
        items += answer["body"]
        if len(answer["body"]) < PAGE:
            return items, True
        page += 1


def events(transport, pull: dict) -> tuple:
    """The pull request's timeline, as GitHub lists it, oldest first, and whether it was read whole."""
    repo = pull["base"]["repo"]["full_name"]
    return _pages(transport, "/repos/%s/issues/%d/timeline?per_page=%d" % (repo, pull["number"], PAGE))


def label_events(timeline: list, accounts: Accounts) -> list:
    """Every labeled and unlabeled event, with its label, who made it and when, as the timeline lists them."""
    found = []
    for event in timeline:
        if not isinstance(event, dict) or event.get("event") not in LABELS:
            continue
        name = (event.get("label") or {}).get("name") if isinstance(event.get("label"), dict) else None
        if not isinstance(name, str) or not name:
            raise Unanswered("a label event names no label")
        found.append({"label": name, "action": event["event"], "by": accounts.actor(event.get("actor")),
                      "at": _time(event.get("created_at"))})
    return found


def _content(transport, repo: str, base_head: str, commit: str) -> str:
    """The content id of a commit, as the pull request's own is: the sha256 of the diff against its merge base."""
    if not SHA.match(str(commit)) or not SHA.match(str(base_head)):
        raise Unanswered("a review's commit or the base's head cannot be read")
    answer = transport.send(request("GET", "/repos/%s/compare/%s...%s" % (repo, base_head, commit), accept=DIFF))
    if answer["status"] != 200 or not isinstance(answer["body"], str):
        raise Unanswered("the content of %s answered %d" % (commit, answer["status"]))
    return "sha256:" + hashlib.sha256(raw(answer["body"])).hexdigest()


def reviews(transport, pull: dict, timeline: list, accounts: Accounts, base_head: str) -> tuple:
    """Every submitted review, with who submitted it, its state as GitHub holds it now, its commit and that commit's
    content id, and, from the timeline, who dismissed it and what it was before. Whether the list was read whole."""
    repo = pull["base"]["repo"]["full_name"]
    listed, whole = _pages(transport, "/repos/%s/pulls/%d/reviews?per_page=%d" % (repo, pull["number"], PAGE))
    dismissals = {}
    for event in timeline:
        if isinstance(event, dict) and event.get("event") == "review_dismissed":
            what = event.get("dismissed_review") if isinstance(event.get("dismissed_review"), dict) else {}
            dismissals[what.get("review_id")] = (event.get("actor"), what.get("state"))
    contents, found = {}, []
    for review in listed:
        if not isinstance(review, dict) or review.get("state") == "PENDING":
            continue
        state = STATES.get(review.get("state"))
        if state is None:
            raise Unanswered("a review state GitHub does not give: %r" % (review.get("state"),))
        commit = review.get("commit_id")
        if commit not in contents:
            contents[commit] = _content(transport, repo, base_head, commit)
        dismissed_by = dismissed_from = None
        if state == "dismissed":
            if review.get("id") not in dismissals:
                raise Unanswered("a dismissed review whose dismissal the timeline does not hold")
            who, before = dismissals[review["id"]]
            if before not in BEFORE:
                raise Unanswered("a dismissed review whose state before cannot be read")
            dismissed_by, dismissed_from = accounts.actor(who), before
        found.append({"by": accounts.actor(review.get("user")), "state": state, "commit": commit,
                      "content_id": contents[commit], "submitted_at": _time(review.get("submitted_at")),
                      "dismissed_by": dismissed_by, "dismissed_from": dismissed_from})
    return found, whole


def _when(event: dict):
    return event.get("created_at") or event.get("submitted_at")


def since_writer(timeline: list, accounts: Accounts) -> dict:
    """When a person with write access last acted on the timeline, and how many acts the Factory made since: each
    approval by the machine user, each label an App or the machine user added or removed, and each entry to or exit
    from the merge queue none of them a person made (decision 0003)."""
    last, acts = None, []
    for event in timeline:
        if not isinstance(event, dict) or event.get("event") not in ACTIONS:
            continue
        who = event.get("actor") or event.get("user")
        at = _time(_when(event))
        actor = accounts.actor(who)
        if actor["kind"] == "human" and actor["can_write"]:
            last = at if last is None or at > last else last
            continue
        approval = event.get("event") == "reviewed" and str(event.get("state")).lower() == "approved" \
            and actor["kind"] == "machine_user"
        moved = event.get("event") in LABELS | QUEUE and actor["kind"] != "human"
        if approval or moved:
            acts.append(at)
    return {"last_writer_action_at": last, "acts_since_writer": sum(1 for at in acts if last is None or at > last)}
