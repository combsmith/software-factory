"""The pass's entry, `python3 -m controller [OUT]`: one pass, read through the ports, decided by `controller/pass_.py`,
and written to the folder `OUT` for the pass job's next steps (#193's ruling 10 for PR 2; #196's PR 2; design sections
2.3 and 7.3). It is the one place in `controller/` that reads the clock or the environment.

1. It mints the Controller App's installation token for the home repo, from `CONTROLLER_APP_KEY`, with the reads its
   grant in `config/apps.json` allows and no write, and revokes it when the pass ends, whatever happened.
2. It reads the last two passes' records (`adapters/passes.py`) and waits out the read gap after the last one's read
   began (decision 0043).
3. It reads what started the pass from its own run, `GITHUB_RUN_ID`; `FACTORY_PAUSED` on the org and the repo; the
   run records, with the outcomes the records before it read (`records.known`) and when their Runs began
   (`records.begun`), the jobs of the rest asked for the open pull requests' Runs alone, 50 at most (decisions 0193
   and 0196); the facts of each open pull request; the open issues updated since `issues.served_from`, none while it is
   null, and each one's own facts by `adapters/issues.py`, with the accounts and the dating the pull requests' have;
   and, for reconciliation, what each Factory identity wrote and what the Factory recorded (decision 0112). The issues
   are listed and read after the pull requests and the records, without the tracking issue, by the number the passes
   recorded (issue 901). Not read: an issue's Runs' jobs, since no issue rule reads when a Run began (decision 0231).
   A served issue's writes are reconciled while it is open (decision 0230), and one that left between two passes is
   read with its close (decision 0235). Each issue's linked pull requests are read with their keyword spans from the
   pass records before this pass, the two the entry already read, and with those not read each issue defers (decision
   0186).
4. It gives the pass what it read and the time after the reads, and writes `pass.json`, `writes.json`, the plan the
   effects step holds to it, and the view's three files under `view/`.

The Release is the one tag `factory/vX.Y.Z` on the commit the pass checked out (`harness/steps.release`), read before any key. A snapshot that cannot be read leaves its pull
request out of the pass, by its item and the code of why, as one alert; one that moved while it was read, and had not in
the last pass, is deferred with no alert and its writes are owed to the next pass (#658). An issue that cannot be read
is left out so too, and one that moved is graced as a pull request is, with nothing owed for it (decision 0229). A list of issues not read whole
reads no issue, and the pass says so, naming no item; so does each issue the pass's budget of issue requests left unread,
by its item (decision 0234). A list of open pull requests not read whole, a Release, a key or
a run id that cannot be read, or a pass `pass_.py` refuses, writes nothing, so that nothing is dispatched; the step
prints one code and exits 1, and nothing it prints is GitHub's text."""
from __future__ import annotations

import concurrent.futures
import contextlib
import datetime
import json
import os
import pathlib
import re
import sys
import time

from adapters import applied, facts as facts_, identity, issues as issues_, items, passes, pause as pause_, records, \
    seen as seen_, timeline
from adapters.facts import accounts_of as accounts, app_names_of, dispatcher_of as dispatcher, opener_of as opener, queue_of, \
    roles_of
from adapters.github import Live, Unanswered
from controller import configuration as configured, issue_holds, pass_, reads as reads_, reconcile, writes as writes_
from controller.shared import Refused, key as page
from harness import steps
from kernel.terms import BOT_SUFFIX

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = "controller"
KEY = "CONTROLLER_APP_KEY"
RUN_ID = re.compile(r"[1-9][0-9]{0,18}")
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
VIEW = ("meta", "items", "health")
FOLDER = "pass"     # what the workflow's form writes into, for the upload and the effects step
# The open pull requests' snapshots read at once, each serial inside, the rest of the pass serial (decision 1138).
POOL = 4
WINDOW = 24 * 60 * 60   # reconciliation's window, with `not_run_seconds`, so a pass after a gap still covers it (decision 0061)


class Stop(Exception):
    """The pass cannot go on, by its code alone."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def configuration(root: pathlib.Path, release: str) -> dict:
    """What `pass_.run` is told, with the Controller's App and the needs it is read under (`controller/configuration.py`)."""
    return configured.load(root, release, APP)


def wanted(config: dict) -> dict:
    """The permissions the pass's token is minted with: every read the Controller's App is granted, and no write."""
    names = [n for grant in config["app"]["permissions"].values() for n in grant["needs"] if n.startswith("read:")]
    return identity.granted(config["app"], config["needs"], names, "read")


def mint_id(prefix: str) -> str:
    """A new id in the schemas' form, from the system's own randomness: twenty letters of 32, a hundred bits."""
    return "%s_%s" % (prefix, "".join(ALPHABET[b % 32] for b in os.urandom(20)))


def utc(clock=time.time) -> str:
    return datetime.datetime.fromtimestamp(int(clock()), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Stages:
    """How long each stage of a pass took, and how many it read, one JSON line each on standard error as the stage ends,
    so that the next slowdown names its cost (issue 1025). The Solution Architect's ruling: the job's log alone, never
    the pass record, which later passes read and a replay repeats. A line holds the stage's name, its seconds and its
    counts, each a whole number, and nothing from outside: no title, body, login or token. A timer or a stream that
    fails says less, and never fails the pass; with no timer nothing is timed or said. Timing changes no read."""

    # What the carry's line counts of it, by these names alone.
    COUNTED = ("hand", "taken",
               "runs", "passes", "keys", "items", "dispatched", "owed", "left", "owed_issues", "left_issues", "hands")
    FARTHEST = 1e300      # a reading no clock gives: two inside it differ by a finite number

    def __init__(self, timer=None, out=None):
        self.timer, self.out = timer, out

    def now(self):
        if self.timer is None:
            return None
        try:
            value = self.timer()
            value = float(value) if type(value) in (int, float) else None
        except Exception:
            return None
        # A reading past any clock's, infinite or no number at all, is none: NaN compares false with every bound.
        return value if value is not None and -self.FARTHEST < value < self.FARTHEST else None

    def since(self, began):
        ended = self.now()
        return None if began is None or ended is None else max(0.0, ended - began)

    def say(self, stage: str, seconds, counts=None) -> None:
        if self.timer is None or self.out is None:
            return
        try:
            line = {"stage": stage, "seconds": None if seconds is None else round(seconds, 3)}
            line.update({k: v for k, v in (counts or {}).items() if type(k) is str and type(v) is int})
            print(json.dumps(line, sort_keys=True), file=self.out, flush=True)
        except Exception:
            pass

    @contextlib.contextmanager
    def stage(self, name: str):
        """Times the block, and says it with the counts set on what it yields, even where the block raised."""
        began, counts = self.now(), {}
        try:
            yield counts
        finally:
            self.say(name, self.since(began), counts)

    def add(self, tally: dict, name: str, began) -> None:
        """Adds one read begun at `began` to `tally`'s `name`: its seconds and its count."""
        self.count(tally, name, self.since(began))

    def count(self, tally: dict, name: str, seconds) -> None:
        """Adds one read that took `seconds`, None where they could not be told, to `tally`'s `name`."""
        held = tally.setdefault(name, [0.0, 0])
        held[0] = None if held[0] is None or seconds is None else held[0] + seconds
        held[1] += 1

    def tell(self, tally: dict) -> None:
        for name, (seconds, count) in tally.items():
            self.say(name, seconds, {"count": count})

    def carried(self, record) -> dict:
        """What the record carries for reconciliation, counted by the carry's own names: what the pass rebuilt and
        checked, which grows with the window (issue 1025)."""
        held = record.get("reconciled") if isinstance(record, dict) else None
        return {k: len(held[k]) for k in self.COUNTED if isinstance(held, dict) and isinstance(held.get(k), (list, dict))}


QUIET = Stages()


class Timed:
    """The transport, timing each request by its kind for `Stages`: each is handed on as it came, and each answer back
    as it came. `kind` names a request by its path, from this module's own names."""

    def __init__(self, transport, stages: Stages, kind):
        self.transport, self.stages, self.kind, self.tally = transport, stages, kind, {}

    def send(self, req):
        began = self.stages.now()
        try:
            return self.transport.send(req)
        finally:
            try:
                self.stages.add(self.tally, self.kind(req["path"]), began)
            except Exception:
                pass


def rate_limited(answer) -> bool:
    """Whether GitHub's answer is a rate limit's: a 429, or a 403 with no request left or a time to wait, as
    `adapters/pause.py` tells one from a refusal."""
    headers = answer.get("headers") if isinstance(answer, dict) and isinstance(answer.get("headers"), dict) else {}
    status = answer.get("status") if isinstance(answer, dict) else None
    return status == 429 or (status == 403 and (str(headers.get("x-ratelimit-remaining")) == "0" or "retry-after" in headers))


class Limited:
    """One snapshot's transport, its account reader's too: a rate limit is no answer, never retried, `hit` and told
    to the pass's `seen` (decision 1138)."""

    def __init__(self, transport, seen: list):
        self.transport, self.seen, self.hit = transport, seen, False

    def send(self, req):
        answer = self.transport.send(req)
        if rate_limited(answer):
            self.hit = True
            self.seen.append(True)
            raise Unanswered("GitHub answered a rate limit")
        return answer


NOT_BEGUN = object()


def snapshots(numbers: list, one, pool: int, seen: list) -> list:
    """`one(number)` for each of `numbers`, in their order: up to `pool` at once, each in a thread, begun only while no
    rate limit is `seen`; the rest after, one at a time, in this thread (decision 1138)."""
    def begun(number):
        return NOT_BEGUN if seen else one(number)
    out = [NOT_BEGUN] * len(numbers)
    if pool > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=pool) as running:
            out = list(running.map(begun, numbers))
    return [one(number) if got is NOT_BEGUN else got for number, got in zip(numbers, out)]


def poller_kind(path) -> str:
    """A pass's or a Run's list of runs, or an artifact's: the two reads of the window that grow apart (issue 1025)."""
    return "list" if isinstance(path, str) and "/actions/workflows/" in path else "artifacts"


class Dated:
    """The transport, keeping the first answer through it, whose date and age are a facts read's."""

    def __init__(self, transport):
        self.transport, self.first = transport, None

    def send(self, req):
        answer = self.transport.send(req)
        self.first = answer if self.first is None else self.first
        return answer


class Kept:
    """The transport, keeping every answer through it: a read of more than one request is dated by each answer."""

    def __init__(self, transport):
        self.transport, self.answers = transport, []

    def send(self, req):
        self.answers.append(self.transport.send(req))
        return self.answers[-1]


class Counted:
    """The transport, counting each request sent through it, whatever it answered or if it failed: the issue reads'
    budget is spent as they are sent (decision 0234)."""

    def __init__(self, transport):
        self.transport, self.sent = transport, 0

    def send(self, req):
        self.sent += 1
        return self.transport.send(req)


def dated(answer) -> list:
    """A facts read's `{"date", "age"}`, or nothing where its answer says neither."""
    try:
        at = records.read_at(answer) if isinstance(answer, dict) else None
    except Unanswered:
        return []
    return [{"date": at["date"], "age": at["age"]}] if at else []


def writes_seen(transport, config: dict, numbers: list, kept: dict, before, since: str, clock, owed=(),
                stages=QUIET, issues=(), listed=True, tracking=()) -> tuple:
    """`(seen/1, the pull requests read short, those read as left for the first time, the issues read short or owed,
    those read as left for the first time)`: what each Factory identity wrote
    on what this pass served, on what the pass before served or could not read and has left (decision 0061), and on what
    a pass before read as left inside the window, so that a write nobody matched keeps its alert until the window passes
    it (issue 787). What a snapshot could not read is short, and one that
    is short is read again by the next pass, so that nothing leaves unread. So is a pass with no records before it to say
    what has left. Nothing is guessed. One `owed`, a pull request that moved for the first time, is not read: it is owed
    to the next pass, as one read short is, and leaves this reconciliation whole (#658). Each of `issues`, the served
    open issues, is read too, with nothing kept of it. One read short leaves what was seen short and is not owed: what
    is owed is read as a pull request that left, and an open issue is read again by the next pass as it is (issue 837).
    An issue the pass before served, or owed, that is not among `issues` has left: it is read as a pull request that left
    is, with its close, and one a pass before read as left inside the window as gone; one read short is owed to the next
    pass. Where the issues were not `listed`, read whole of the served ones, none has left that can be told: those owed
    and those the pass before served are owed again, and what was seen is short. `tracking` is the numbers the passes
    recorded the tracking issue under, which is never an issue that left (issue 916). `stages` times what it read of the
    open pull requests, of those newly left, of those gone and of the issues, apart, and the pushes (issue 1025)."""
    controller = config["controller"]
    home, accounts_held = controller["home"]["repo"], controller["accounts"]
    identities, _ = seen_.identities(accounts_held)
    apps = seen_.apps_of(accounts_held, config["apps"])
    last = before[-1]["pull_requests"] if before else []
    # One owed that a record before read as left is read as gone, and keeps its stamp; past the window it is read no
    # more (issue 787). Any other no longer open has left since the last pass, one it left out too (issue 1194).
    held = set(reconcile.left(before))
    left_out = {e["item"]["number"] for e in ((before[-1].get("left_out") or []) if before else [])
                if isinstance(e.get("item"), dict) and e["item"].get("type") == "pull_request"}
    newly = (({e["facts"]["item"]["number"] for e in last} | left_out) - set(numbers)) \
        | (set(reconcile.owed(before)) - set(numbers) - held)
    gone = set(reconcile.left(before, since)) - set(numbers) - newly
    parts, unread, tally, served = [], [], {}, set(numbers)
    for number, held in ([(n, kept.get(n)) for n in numbers] + [(n, seen_.LEFT) for n in sorted(newly)]
                         + [(n, seen_.GONE) for n in sorted(gone)]):
        if number in owed:
            unread.append(number)
            continue
        began = stages.now()
        try:
            part = seen_.read(transport, {"repo": home, "type": "pull_request", "number": number}, held, identities, apps,
                              since)
        except Unanswered:
            part = ([], [], False)
        stages.add(tally, "seen_open" if number in served else "seen_left" if number in newly else "seen_gone", began)
        parts.append(part)
        if part[-1] is not True:
            unread.append(number)
    was_served = {e["facts"]["item"]["number"] for e in (before[-1].get("issues") or [])} if before else set()
    was_served |= {e["item"]["number"] for e in ((before[-1].get("left_out") or []) if before else [])
               if isinstance(e.get("item"), dict) and e["item"].get("type") == "issue"}
    # The tracking issue is never one that left, though a pass that could not tell it left it out as unread (Claude).
    was_served -= set(tracking)
    owing = set(reconcile.owed_issues(before)) - set(tracking)
    kept_left = set(reconcile.left_issues(before, since)) - set(tracking)
    unread_issues, newly_issues = [], []
    if listed:
        # One served before is read as left whatever an older stamp says, so a second close is read with its own; one
        # owed is read as gone while its stamp is in the window, else as left again, never dropped unread (security, Kimi).
        newly_issues = sorted((was_served - set(issues)) | (owing - set(issues) - kept_left))
        gone_issues = sorted(kept_left - set(issues) - set(newly_issues))
    else:
        # With nothing served before and nothing owed, there is nothing left unread to tell.
        unread_issues, gone_issues = sorted(was_served | owing | kept_left), []
        if unread_issues:
            parts.append(([], [], False))
    # An issue that left and is not found or deleted ends only where the same token read the repo in this pass, read
    # once for them all before their reads, and once more after them where one ended, so that access lost between the
    # two is short, its issues owed (decision 1145).
    told, ended = [], {"repo_read": seen_.repo_read(transport, home)} if newly_issues or gone_issues else {}
    for number, held in ([(n, None) for n in issues] + [(n, seen_.LEFT) for n in newly_issues]
                         + [(n, seen_.GONE) for n in gone_issues]):
        began = stages.now()
        try:
            parts.append(seen_.read(transport, {"repo": home, "type": "issue", "number": number}, held, identities, apps,
                                    since, **(dict(ended, told=told) if held is not None else {})))
        except Unanswered:
            parts.append(([], [], False))
        if parts[-1][-1] is not True and held is not None:
            unread_issues.append(number)
        stages.add(tally, "seen_issues", began)
    if told and not seen_.repo_read(transport, home):
        unread_issues += [g["item"]["number"] for g in told]
        parts.append(([], [], False))
        told = []
    stages.tell(tally)
    with stages.stage("seen_pushes"):
        try:
            parts.append(seen_.pushes(transport, home, accounts_held["approver"], since, clock=lambda: utc(clock)))
        except Unanswered:
            parts.append(([], False))
    if before is None:
        parts.append(([], False))
    return seen_.seen(parts, since, told), unread, sorted(newly), sorted(set(unread_issues)), newly_issues


def recorded_passes(transport, config: dict, own: int, before, since: str, sleep=time.sleep, stages=QUIET) -> dict:
    """Each pass's `written/1` that no record before this pass read, read once, and all of them again where the last
    record holds none (decision 0112): `adapters/passes.written`'s answer. It is read before the issues are listed, for
    the numbers the passes recorded the tracking issue under (issue 901). Passes run one at a time, in the poller's one
    concurrency group, so none records a write while this one reads. `stages` times the read whole, its one wait
    included, and its list's requests apart from its artifacts' (issue 1025)."""
    controller = config["controller"]
    home = controller["home"]["repo"]
    _, known_passes = reconcile.known(before)
    timed = stages.timer is not None
    of_passes = Timed(transport, stages, poller_kind)
    with stages.stage("poller"):
        from_passes = passes.written(of_passes if timed else transport, home, controller["home"]["branch"],
                                     controller["workflows"]["poller"], own, since, known_passes, sleep=sleep)
    stages.tell({"poller_" + kind: held for kind, held in of_passes.tally.items()})
    return from_passes


def recorded_effects(transport, config: dict, runs, before, since: str, from_passes: dict, sleep=time.sleep,
                     stages=QUIET) -> dict:
    """The Effects the Factory recorded and no record before this pass read: each Run's `applied/1`, read once, and all
    of them again where the last record holds none, beside the passes' `from_passes` (decision 0112). The Runs' are read
    after the writes are seen, as a Run still running may record what it wrote in between: read first, its write would
    be short (issue 837). `sleep` is the entry's, for each port's one wait before its second look (issue 709). `stages`
    times the Runs' reads whole, its one wait included, and its list's requests apart from its artifacts' (issue 1025)."""
    home = config["controller"]["home"]["repo"]
    known_runs, _ = reconcile.known(before)
    timed = stages.timer is not None
    of_runs = Timed(transport, stages, poller_kind)
    with stages.stage("applied"):
        from_runs = applied.effects(of_runs if timed else transport, home, runs, since, known_runs, sleep=sleep)
    stages.tell({"applied_" + kind: held for kind, held in of_runs.tally.items()})
    return {"applied": from_runs["applied"], "written": from_passes["written"],
            "read": {"runs": from_runs["read"], "passes": from_passes["read"]},
            "at": dict(from_runs["at"], **from_passes["at"]),
            "whole": from_runs["whole"] and from_passes["whole"]}


def run_files(controller: dict) -> list:
    """The workflow files whose runs are the item's Runs: the run and approval files, and the queue App's once it is
    named, so each resolution it lands is counted from its Run (issue 381)."""
    return facts_.run_files_of(controller)


def reader(transport, config: dict) -> tuple:
    """`(identities, who, refused)`: the class's accounts and the account reader every item of a pass is read with, from
    the configuration alone. Each name the issues' Kernel is told is an App's is reserved: only that App, by the id
    held, may show it (Carbon). One of them that is the queue App's or a Lens's App's refuses the issues,
    `issue_apps_unreadable`: the reader tells those two by their ids as a queue and a Lens, never as an App by its name,
    so no act of theirs could be read as the App's the issues name. The pull requests are read on, by a reader that does
    not reserve that name, as if the issues had never declared it: no snapshot is refused for it (issue 901)."""
    controller = config["controller"]
    identities, approver, lenses, factory = accounts(controller)
    declared = pass_.issue_config(config["kernel"])["issues"]
    reserved = [name for name in declared["label_apps"].values() if name] \
        + [intent["app"] for intent in declared["intents"].values() if isinstance(intent, dict)]
    names, queue = app_names_of(controller, config["apps"]), queue_of(controller)
    held = [a for a in controller["accounts"]["lenses"] + [controller["accounts"]["queue"]] if a]
    # Each is told too by the name config/apps.json gives its code, the queue's and each Lens's, though the login held
    # for it is another: the App the issues name could be it renamed.
    def app_name(code):
        app = config["apps"].get(code)
        return app["name"] + BOT_SUFFIX if isinstance(app, dict) and app.get("name") else None

    taken = {a["login"] for a in held} | {names.get((a["id"], "Bot")) for a in held} \
        | {app_name(a["lens"]) for a in controller["accounts"]["lenses"]} \
        | {app_name("queue") if controller["accounts"]["queue"] else None}
    refused = bool(taken & set(reserved))
    reserved = [name for name in reserved if name not in taken]
    return identities, timeline.Accounts(transport, controller["home"]["repo"], approver, lenses, factory, queue,
                                         names, reserved, roles_of(controller)), refused


def read(transport, config: dict, run_id: str, previous, now: str, clock, started, sleep=time.sleep,
         stages=QUIET, pool: int = 1) -> dict:
    """Everything the pass reads after the wait, as `pass_.run` takes it. Each port that waits waits by `sleep`, the
    entry's (issue 709). `stages` times each stage of it (issue 1025). `pool` open pull requests are read at once, one
    to a recorded exchange, whose answers come in order (decision 1138)."""
    controller = config["controller"]
    home, branch = controller["home"]["repo"], controller["home"]["branch"]
    with stages.stage("accounts"):
        identities, who, refused = reader(transport, config)
    # The open pull requests are listed first: the records port asks when a Run began only of theirs (decision 0196),
    # and of no issue's, whose rules read no beginning (decision 0231).
    with stages.stage("pull_request_list") as counts:
        try:
            numbers, whole = items.open_pull_requests(transport, home)
        except Unanswered:
            numbers, whole = [], False
        counts["count"] = len(numbers)
    if not whole:
        raise Stop("pull_requests_unreadable")
    earlier = pass_.earlier(reads_.previous_records(previous), now) or []
    with stages.stage("runs") as counts:
        try:
            runs = records.runs(transport, home, branch, run_files(controller), dispatcher(controller),
                                kept=records.known(earlier), began=records.begun(earlier),
                                engines=records.engines(earlier), sleep=sleep,
                                advised=records.advised(earlier), day=now[:len("2026-01-01")],
                                of=[{"repo": home, "type": "pull_request", "number": number} for number in numbers])
        except Unanswered:
            runs = None
        if isinstance(runs, dict) and isinstance(runs.get("runs"), list):
            counts["count"] = len(runs["runs"])
    opens = opener(controller, config["kernel"], config["apps"])
    runs_whole = isinstance(runs, dict) and runs.get("complete") is True
    # What each Lens recorded on each open pull request, in its Runs' applied/1, which the threads are held to.
    with stages.stage("lens_records"):
        found = applied.recorded(transport, home, runs, numbers, set(config["kernel"]["required_lenses"]["model"]),
                                 config["authority"])
        # What each opening Run recorded of the pull request it opened, which binds it to its issue (issue 342).
        made = applied.opened(transport, home, runs, facts_.opener_role(config["kernel"]))
    seen = []

    def one(number: int) -> tuple:
        """`(entry, kept, facts reads, seconds)` of one open pull request's snapshot, read whole in its own thread."""
        began = stages.now()
        held, own = {}, Limited(transport, seen)
        through = Dated(own)
        try:
            facts, title, head = facts_.snapshot(through, home, number, identities, who.through(own), runs_whole,
                                                 lambda: utc(clock), kept=held, with_head=True,
                                                 opener=opens, recorded=found[number], opened=made)
            if own.hit:
                # A part that read on past a rate limit leaves it out too.
                raise Unanswered("GitHub answered a rate limit")
            return {"facts": facts, "title": title, "head": head}, held, dated(through.first), stages.since(began)
        except Unanswered as err:
            # Its code goes in the record: one that moved while it was read is not one GitHub did not answer (#658).
            return ({"facts": {"item": {"repo": home, "type": "pull_request", "number": number}}, "title": None,
                     "unread": reads_.MOVED if isinstance(err, facts_.Moved) else reads_.UNANSWERED},
                    None, [], stages.since(began))
    pulls, kept, facts_reads, tally = [], {}, [], {}
    # Each thread timed its own reads; added up here in the listed order.
    for number, (pull, held, dates, seconds) in zip(numbers, snapshots(numbers, one, pool, seen)):
        pulls.append(pull)
        if held is not None:
            kept[number] = held
        facts_reads += dates
        stages.count(tally, "open_pull_requests", seconds)
    stages.tell(tally)
    before = pass_.earlier(reads_.previous_records(previous), now)
    since = utc(lambda: clock() - WINDOW - controller["not_run_seconds"])
    # A pull request that moved for the first time is owed to the next pass's reconciliation, not read short here.
    left = [e for e in pulls if "unread" in e]
    graced = pass_.moved_once([e["facts"]["item"] for e in left], [e["unread"] for e in left], before)
    owed = {e["facts"]["item"]["number"] for e in left if page(e["facts"]["item"]) in graced}
    from_passes = recorded_passes(transport, config, int(run_id), before, since, sleep, stages)
    # The open issues the Kernel could serve, none while `issues.served_from` is null, without the tracking issue, by
    # the number the passes recorded. A list read short is never the whole: no issue is read, and one entry naming no
    # item says so, which the keyword spans' chain passes over; the pull requests are decided as ever (decision 0252).
    # Issues whose Apps cannot be told are not listed, as with no date: none is read or decided, and the pass says so.
    apart = reconcile.tracking(from_passes, before)
    served = None if refused else config["kernel"]["issues"]["served_from"]
    with stages.stage("issue_list") as counts:
        try:
            listed, listed_whole = items.open_issues(transport, home, served, apart=apart or ())
        except Unanswered:
            listed, listed_whole = [], False
        counts["count"] = len(listed)
    issues = [] if listed_whole else [{"facts": {"item": None}, "title": None, "unread": reads_.UNLISTED}]
    # Each issue's own facts, read and dated as a pull request's are; its title beside them. While the tracking
    # issue's number is not read, none is: each is left out as unread, so that one is never served as a Work item. One
    # no record numbers is told at its own read, by its opener and its body, and is no Work item, nor left out: it was
    # never one, as one the listing left out was not (decision 0233). Once the pass's budget of issue requests is spent
    # no further read starts, and each issue not read is left out by it; those the last record left out so are read
    # first (decision 0234).
    tally, own_app = {}, controller["accounts"]["controller"]
    counted = Counted(transport)
    # The account reader's permission reads for the issues are counted too, its answers shared with the pull requests'.
    asking = who.through(counted)
    # The default branch's head, read once a pass where an issue is to be read, and handed to each as its `base_head`,
    # left out where it cannot be read; each answer dated as a facts read where it is (decisions 0226 and 0242). Its two requests
    # are fixed, and spend none of the budget, which bounds the reads each issue costs: one issue is read at least.
    asked = Kept(transport)
    head = issues_.default_head(asked, home) if listed_whole and listed and apart is not None else None
    facts_reads += [read for answer in asked.answers for read in dated(answer)] if head is not None else []
    for number in pass_.issue_order(listed if listed_whole else [], before):
        began, through = stages.now(), Dated(counted)
        try:
            if apart is None:
                raise Unanswered("the tracking issue's number was not read")
            if counted.sent >= controller["max_issue_requests"]:
                issues.append({"facts": {"item": {"repo": home, "type": "issue", "number": number}}, "title": None,
                               "unread": reads_.BUDGET})
                continue
            facts, title = issues_.read(through, home, number, asking, lambda: utc(clock), identities=identities,
                                        earlier=before, kernel=config["kernel"], base_head=head, opener=opens,
                                        runs=runs, role=facts_.opener_role(config["kernel"]),
                                        controller=(own_app["id"], own_app["type"]) if own_app else None)
            issues.append({"facts": facts, "title": title})
            facts_reads += dated(through.first)
        except Unanswered as err:
            issues.append({"facts": {"item": {"repo": home, "type": "issue", "number": number}}, "title": None,
                           "unread": reads_.MOVED if isinstance(err, facts_.Moved) else reads_.UNANSWERED})
        except issues_.Tracking:
            pass
        stages.add(tally, "issues", began)
    stages.tell(tally)
    # How the issue each pull request the Factory opened stands with: one read of each, open or closed, served or not;
    # one that cannot be read leaves the fact unread, and the pull request defers (decision 0232). While the issues'
    # Apps cannot be told, or the tracking issue's number was not read, none is read: each is unread, as the issues are.
    stood, tally = {}, {}
    for number in issue_holds.wanted(pulls):
        began = stages.now()
        try:
            if refused or apart is None:
                raise Unanswered("the issues cannot be read")
            stood[number] = issues_.stood(transport, home, number, who)
        except Unanswered:
            stood[number] = None
        stages.add(tally, "issues_stood", began)
    stages.tell(tally)
    pulls = issue_holds.join(pulls, stood, pass_.issue_config(config["kernel"]))
    # The served issues' writes are read beside the pull requests' (issue 837): those of each issue the pass serves,
    # decided or left out unread, never the tracking issue, which the listing leaves out by its number or its own read
    # tells (decision 0233). While that number is not read, no issue's writes are: the tracking issue could be among
    # those listed, and the passes' records read short leave reconciliation short already.
    # A list read short serves none: its one entry names no item, and no issue that left can be told (decision 0252).
    served_issues = [e["facts"]["item"]["number"] for e in issues if e["facts"]["item"] is not None] \
        if apart is not None else ()
    # One listed that is neither served nor left out was told as the tracking issue at its own read: it never left (codex).
    told = set(listed) - set(served_issues) if apart is not None and listed_whole else set()
    seen, unread, gone, unread_issues, gone_issues = writes_seen(
        transport, config, numbers, kept, before, since, clock, owed, stages, served_issues,
        listed=apart is not None and served is not None and listed_whole, tracking=set(apart or ()) | told)
    effects = recorded_effects(transport, config, runs, before, since, from_passes, sleep, stages)
    with stages.stage("pause"):
        pause = pause_.read(transport, home.split("/")[0], [home])
    return {"started": started, "pause": pause,
            "records": runs, "pull_requests": pulls, "issues": issues, pass_.ISSUE_APPS: refused,
            "facts_reads": facts_reads, "usage": {}, "seen": seen, "unread": unread, "gone": gone,
            "unread_issues": unread_issues, "gone_issues": gone_issues, "effects": effects}


def one_pass(transport, config: dict, run_id: str, clock=time.time, sleep=time.sleep, stages=QUIET, pool: int = 1) -> dict:
    """One pass, through `transport`: the records before it, the wait, the reads, and what `pass_.run` returned.
    `stages` times each, the wait apart from the reads; `pool` open pull requests are read at once."""
    controller = config["controller"]
    with stages.stage("records_before"):
        previous = passes.records(transport, controller["home"]["repo"], controller["home"]["branch"],
                                  controller["workflows"]["poller"], int(run_id))
        started = passes.started(transport, controller["home"]["repo"], run_id)
    with stages.stage("wait"):
        sleep(pass_.wait_before_reading(previous, utc(clock), config, started))
    reads = read(transport, config, run_id, previous, utc(clock), clock, started, sleep, stages, pool)
    # The pass is pure and times nothing itself: its carry's rebuild and its record's check are timed with it, and the
    # carry's size is said beside them.
    with stages.stage("decide") as counts:
        out = pass_.run(reads, config, utc(clock), previous, mint_id)
        counts.update(stages.carried(out.get("record")))
    return out


def write(out: dict, directory: str) -> None:
    """`pass.json`, `writes.json` and `view/`, in the folder given, which was empty: each file is made new, and none is
    written through a link that was already there."""
    files = {"pass.json": out["record"], "writes.json": writes_.plan(out)}
    files.update({os.path.join("view", "%s.json" % name): out["view"][name] for name in VIEW})
    # Each is made text before any file is made, so a number that is not finite leaves no file at all (issue 922).
    texts = {name: json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n" for name, document in files.items()}
    os.mkdir(os.path.join(directory, "view"))
    for name, text in texts.items():
        made = os.open(os.path.join(directory, name), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with open(made, "w", encoding="utf-8") as f:
            f.write(text)


def main(argv=None, environ=None, base=None, clock=time.time, sleep=time.sleep, connect=Live, timer=time.monotonic,
         err=None, pool=POOL) -> int:
    """The step. It writes only into an empty folder inside the directory it runs in, `base`, by default the working
    directory, and names no path, key or token in what it prints. The token is revoked whatever happened, and one GitHub
    did not revoke fails the step, `token_not_revoked`. Each stage's seconds go to `err`, standard error by default,
    timed by `timer` (issue 1025). `pool` open pull requests are read at once (decision 1138)."""
    argv = sys.argv[1:] if argv is None else argv
    environ = os.environ if environ is None else environ
    inside = os.path.realpath(str(pathlib.Path.cwd() if base is None else base))
    if not argv and not os.path.lexists(os.path.join(inside, FOLDER)):
        # The workflow's form: the folder `pass.yml` uploads, made here, new and the step's own.
        os.mkdir(os.path.join(inside, FOLDER), 0o700)
        argv = [FOLDER]
    out = os.path.realpath(os.path.join(inside, argv[0])) if len(argv) == 1 else None
    if out is None or not (out == inside or out.startswith(inside + os.sep)) or not os.path.isdir(out) \
            or os.listdir(out):
        print("usage: python3 -m controller OUT, OUT an empty folder inside the directory it runs in; nothing was read")
        return 2
    revoke, code = None, None
    try:
        try:
            release = steps.release()
        except steps.Stop as stop:
            raise Stop(stop.code) from None
        run_id, key = environ.get("GITHUB_RUN_ID"), environ.get(KEY)
        if not (isinstance(run_id, str) and RUN_ID.fullmatch(run_id)):
            raise Stop("run_unreadable")
        if not isinstance(key, str) or not key:
            raise Stop("key_unreadable")
        config = configuration(ROOT, release)
        home = config["controller"]["home"]["repo"]
        try:
            as_app = connect(identity.jwt(config["app"]["app_id"], key.encode(), int(clock())))
            token = identity.mint(as_app, config["app"], home, wanted(config), lambda value: connect(value))
        except (identity.Refused, Unanswered) as err:
            raise Stop(str(err) if isinstance(err, identity.Refused) else "token_unreadable") from None
        transport = connect(token.reveal())
        revoke = lambda: identity.revoke(transport)
        stages = Stages(timer, sys.stderr if err is None else err)
        decided = one_pass(transport, config, run_id, clock, sleep, stages, pool)
        with stages.stage("write"):
            write(decided, out)
    except Stop as stop:
        code = stop.code
    except Refused:
        code = "pass_refused"
    except Exception:       # a message could quote what GitHub answered: a code alone
        code = "pass_failed"
    finally:
        if revoke is not None:
            try:
                revoked = revoke()
            except Exception:
                revoked = False
            code = code or (None if revoked else "token_not_revoked")
    print(code or "passed")
    return 1 if code else 0


if __name__ == "__main__":
    sys.exit(main())
