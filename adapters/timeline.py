"""The facts a pull request's timeline and reviews give: who acted, of what kind and with what access, every label
event, every review with who dismissed it and what it was before, when a person with write access last acted, and how
many acts the Factory has made since (design section 3.3, decision 0003).

An actor's kind comes from GitHub's account type and the configuration the caller gives, by account id, never from a
name's spelling (decision 0005, L-57): `machine_user` is the User the caller names as the approver and no other; `lens`
is a Bot the caller names as a Lens's App, read as that Lens's name; any other Bot is `app`; any other User is `human`.
An event a User made through an App, one that names `performed_via_github_app`, is the App's act, made with that
person's token, and no person's: its label event or its dismissal is read as `app`, named by the User's login, and
writes nothing (issue 368). A User's write access is read from the repository's collaborator permission, `admin`,
`maintain` or `write`, never `triage`, once a login for the snapshot and never from an association (the Maintainer's
ruling on #222); the machine user's too, since its approval stands only while it can write. An App's write access is
never asked; the same read types a thread's resolver by its id where its comments cannot (decision 0067). A User whose
login ends `[bot]`, or is no login GitHub gives, is refused: the read was wrong.

The timeline and the reviews are read page by page, following the `link` header's next page, and are whole only when
the last page names no next one, never by a page's length (section 3.3). An item that is not an object is refused,
never skipped. No text of GitHub's reaches a part: a review's body, a dismissal's message and a comment are never read.
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
LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
NEXT = re.compile(r'<[^>]*>;\s*rel="next"')
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


def _object(item, what: str) -> dict:
    if not isinstance(item, dict):
        raise Unanswered("an item of %s is not one GitHub gives" % what)
    return item


class Accounts:
    """Who an actor is, read once a login for one snapshot: its kind, its name and whether it can write.

    `approver` is the machine user, `(id, "User")`; `lenses` maps each Lens's App, `(id, "Bot")`, to the Lens's name;
    `factory` is every App account of the Factory's, `(id, "Bot")`, whose acts the act ceiling counts."""

    def __init__(self, transport, repo: str, approver: tuple, lenses: dict, factory=()):
        self.transport, self.repo, self.approver = transport, repo, tuple(approver)
        self.lenses, self.factory, self.answers = dict(lenses), set(factory), {}

    def _permission(self, login: str) -> dict:
        """The repo's permission answer for `login`, read once a login for all the reader serves."""
        if login not in self.answers:
            path = "/repos/%s/collaborators/%s/permission" % (self.repo, urllib.parse.quote(login, safe=""))
            # An answer that failed is kept too, one that never came among them, so a login is asked once however
            # often it appears.
            try:
                answer = self.transport.send(request("GET", path))
            except Unanswered:
                answer = {"status": "no answer", "body": None}
            ok = answer["status"] == 200 and isinstance(answer["body"], dict)
            self.answers[login] = answer["body"] if ok else answer["status"]
        if not isinstance(self.answers[login], dict):
            raise Unanswered("the permission of %s answered %s" % (login, self.answers[login]))
        return self.answers[login]

    def _can_write(self, login: str) -> bool:
        level = self._permission(login).get("permission")
        if level not in PERMISSIONS:
            raise Unanswered("a permission GitHub does not give: %r" % (level,))
        return level in WRITE

    def typed(self, login, ident):
        """The type, a User or a Bot, of the account `ident` by the repo's permission read of `login`, which answers
        the account with its id and type (trials/P-53.json); None where that read fails, or answers another id, or no
        type GitHub gives. The login only asks: what answers is held to the id."""
        if not (isinstance(login, str) and login and isinstance(ident, int) and not isinstance(ident, bool)
                and ident >= 1):
            return None
        try:
            user = self._permission(login).get("user")
        except Unanswered:
            return None
        if not isinstance(user, dict) or type(user.get("id")) is not int or user.get("id") != ident \
                or user.get("type") not in ("User", "Bot"):
            return None
        return user["type"]

    @staticmethod
    def account(raw_actor) -> tuple:
        """`(login, id, type)` of a GitHub user object; refused when it cannot be read."""
        if not isinstance(raw_actor, dict):
            raise Unanswered("an actor cannot be read")
        login, ident, kind = raw_actor.get("login"), raw_actor.get("id"), raw_actor.get("type")
        if not isinstance(login, str) or not login or not isinstance(ident, int) or isinstance(ident, bool) \
                or kind not in ("User", "Bot"):
            raise Unanswered("an actor cannot be read")
        return login, ident, kind

    def actor(self, raw_actor) -> dict:
        """`{kind, name, can_write}` for a GitHub user object; refused when it cannot be read or contradicts itself."""
        login, ident, kind = self.account(raw_actor)
        if kind == "Bot":
            if (ident, kind) in self.lenses:
                return {"kind": "lens", "name": self.lenses[(ident, kind)], "can_write": False}
            return {"kind": "app", "name": login, "can_write": False}
        if login.endswith("[bot]") or not LOGIN.match(login):
            raise Unanswered("a User whose login is none GitHub gives: the read was wrong")
        if (ident, kind) == self.approver:
            return {"kind": "machine_user", "name": login, "can_write": self._can_write(login)}
        return {"kind": "human", "name": login, "can_write": self._can_write(login)}

    def acted(self, event: dict) -> dict:
        """Who made a timeline event, as `actor` reads its account. An App acting with a person's token, which the
        event's `performed_via_github_app` names, is an App, never that person: it cannot write (issue 368)."""
        actor = self.actor(event.get("actor"))
        if actor["kind"] == "human" and event.get("performed_via_github_app"):
            return {"kind": "app", "name": actor["name"], "can_write": False}
        return actor

    def factory_made(self, raw_actor) -> bool:
        """Whether an act was the Factory's: the machine user's, or one of the Factory's Apps'."""
        _, ident, kind = self.account(raw_actor)
        return (ident, kind) == self.approver or (ident, kind) in self.factory


def _pages(transport, path: str) -> tuple:
    """Every item of a list, page by page, each page the one the last named as next; whole only when the last page
    names no next one."""
    items, page = [], 1
    while True:
        answer = transport.send(request("GET", path if page == 1 else "%s&page=%d" % (path, page)))
        if answer["status"] != 200:
            raise Unanswered("%s answered %d" % (path.split("?")[0], answer["status"]))
        if not isinstance(answer["body"], list):
            return items, False
        items += answer["body"]
        if not NEXT.search(str((answer.get("headers") or {}).get("link", ""))):
            return items, True
        page += 1


def events(transport, pull: dict) -> tuple:
    """The pull request's timeline, as GitHub lists it, oldest first, and whether it was read whole."""
    repo = pull["base"]["repo"]["full_name"]
    return _pages(transport, "/repos/%s/issues/%d/timeline?per_page=%d" % (repo, pull["number"], PAGE))


def reopened_at(timeline: list):
    """When the pull request was last reopened, from its timeline's `reopened` events, or None if it never was
    (trials/P-7.reopened.json). A reopening whose time cannot be read refuses the read."""
    found = None
    for event in timeline:
        event = _object(event, "the timeline")
        if event.get("event") == "reopened":
            at = _time(event.get("created_at"))
            found = at if found is None or at > found else found
    return found


def label_events(timeline: list, accounts: Accounts) -> list:
    """Every labeled and unlabeled event, with its label, who made it and when, as the timeline lists them. One an App
    made with a person's token is the App's: it ends no Hold, hands-off or admission of a person's (L-02, issue 368)."""
    found = []
    for event in timeline:
        event = _object(event, "the timeline")
        if event.get("event") not in LABELS:
            continue
        name = (event.get("label") or {}).get("name") if isinstance(event.get("label"), dict) else None
        if not isinstance(name, str) or not name:
            raise Unanswered("a label event names no label")
        found.append({"label": name, "action": event["event"], "by": accounts.acted(event),
                      "at": _time(event.get("created_at"))})
    return found


def _content(transport, repo: str, base_head: str, commit: str) -> str:
    """The content id of a commit, as the pull request's own is: the sha256 of the bytes of its diff against its merge
    base. A diff GitHub will not serve, `too_large`, or one of a commit no longer there, is the commit's own id hashed,
    as `adapters/pull.py` does for the head: never the same as a served diff's, so never read as unchanged."""
    if not SHA.match(str(commit)) or not SHA.match(str(base_head)):
        raise Unanswered("a review's commit or the base's head cannot be read")
    answer = transport.send(request("GET", "/repos/%s/compare/%s...%s" % (repo, base_head, commit), accept=DIFF))
    if answer["status"] == 404 or (answer["status"] == 406 and isinstance(answer["body"], dict) and any(
            isinstance(e, dict) and e.get("code") == "too_large" for e in answer["body"].get("errors") or ())):
        return "sha256:" + hashlib.sha256(commit.encode()).hexdigest()
    if answer["status"] != 200 or not isinstance(answer["body"], str):
        raise Unanswered("the content of %s answered %d" % (commit, answer["status"]))
    return "sha256:" + hashlib.sha256(raw(answer["body"])).hexdigest()


def _dismissals(timeline: list) -> dict:
    """Each dismissed review's id, with the event that dismissed it and what it was before, from the timeline."""
    found = {}
    for event in timeline:
        event = _object(event, "the timeline")
        if event.get("event") == "review_dismissed":
            what = event.get("dismissed_review") if isinstance(event.get("dismissed_review"), dict) else {}
            found[what.get("review_id")] = (event, what.get("state"))
    return found


def reviews(transport, pull: dict, timeline: list, accounts: Accounts, base_head: str, kept=None) -> tuple:
    """Every submitted review, with who submitted it, its state as GitHub holds it now, its commit and that commit's
    content id, and, from the timeline, who dismissed it and what it was before. Whether the list was read whole.
    `kept`, where given, keeps the list as GitHub gave it, for reconciliation (`adapters/seen.py`)."""
    repo = pull["base"]["repo"]["full_name"]
    listed, whole = _pages(transport, "/repos/%s/pulls/%d/reviews?per_page=%d" % (repo, pull["number"], PAGE))
    if kept is not None:
        kept["reviews"] = (listed, whole)
    dismissals = _dismissals(timeline)
    contents, found = {}, []
    for review in listed:
        review = _object(review, "the reviews")
        if review.get("state") == "PENDING":
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
            dismissal, before = dismissals[review["id"]]
            if before not in BEFORE:
                raise Unanswered("a dismissed review whose state before cannot be read")
            dismissed_by, dismissed_from = accounts.acted(dismissal), before
        found.append({"by": accounts.actor(review.get("user")), "state": state, "commit": commit,
                      "content_id": contents[commit], "submitted_at": _time(review.get("submitted_at")),
                      "dismissed_by": dismissed_by, "dismissed_from": dismissed_from})
    return found, whole


def since_writer(timeline: list, accounts: Accounts) -> dict:
    """When a person with write access last acted on the timeline, and how many acts the Factory made since: each
    approval by the machine user, a dismissed one among them, since a dismissal takes nothing back of the act; each
    label and each entry to or exit from the merge queue the machine user or a Factory App made (decision 0003). An
    act in the same second as a writer's action is counted, the reading that stops work. An action an App took with a
    person's token is no action of that person's."""
    dismissals = _dismissals(timeline)
    last, acts = None, []
    for event in timeline:
        event = _object(event, "the timeline")
        kind = event.get("event")
        if kind not in ACTIONS:
            continue
        who = event.get("actor") or event.get("user")
        at = _time(event.get("created_at") or event.get("submitted_at"))
        actor = accounts.actor(who)
        if actor["kind"] == "human" and actor["can_write"] and not event.get("performed_via_github_app"):
            last = at if last is None or at > last else last
            continue
        if not accounts.factory_made(who):
            continue
        state = str(event.get("state")).lower()
        approval = kind == "reviewed" and actor["kind"] == "machine_user" and (
            state == "approved" or (state == "dismissed" and (dismissals.get(event.get("id")) or (None, None))[1] == "approved"))
        if approval or kind in LABELS | QUEUE:
            acts.append(at)
    return {"last_writer_action_at": last, "acts_since_writer": sum(1 for at in acts if last is None or at >= last)}
