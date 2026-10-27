"""The pass's entry, `python3 -m controller [OUT]`: one pass, read through the ports, decided by `controller/pass_.py`,
and written to the folder `OUT` for the pass job's next steps (#193's ruling 10 for PR 2; #196's PR 2; design sections
2.3 and 7.3). It is the one place in `controller/` that reads the clock or the environment.

1. It mints the Controller App's installation token for the home repo, from `CONTROLLER_APP_KEY`, with the reads its
   grant in `config/apps.json` allows and no write, and revokes it when the pass ends, whatever happened.
2. It reads the last two passes' records (`adapters/passes.py`) and waits out the read gap after the last one's read
   began (decision 0043).
3. It reads what started the pass from its own run, `GITHUB_RUN_ID`; `FACTORY_PAUSED` on the org and the repo; the
   run records, with the outcomes the records before it read (`records.known`); and the facts of each open pull
   request. The issues' reads are the issue Lifecycle's port's, not built yet: none is read, and no issue is decided.
4. It gives the pass what it read and the time after the reads, and writes `pass.json`, `writes.json`, the plan the
   effects step holds to it, and the view's three files under `view/`.

The Release is the one tag `factory/vX.Y.Z` on the commit the pass checked out (`harness/steps.release`), read before any key. A snapshot that cannot be read leaves its pull
request out of the pass, by its item, as one alert. A list of open pull requests not read whole, a Release, a key or
a run id that cannot be read, or a pass `pass_.py` refuses, writes nothing, so that nothing is dispatched; the step
prints one code and exits 1, and nothing it prints is GitHub's text."""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import sys
import time

from adapters import facts as facts_, identity, items, passes, pause as pause_, records, timeline
from adapters.facts import accounts_of as accounts, dispatcher_of as dispatcher, opener_of as opener
from adapters.github import Live, Unanswered
from controller import configuration as configured, pass_, reads as reads_, writes as writes_
from controller.shared import Refused
from harness import steps

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = "controller"
KEY = "CONTROLLER_APP_KEY"
RUN_ID = re.compile(r"[1-9][0-9]{0,18}")
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
VIEW = ("meta", "items", "health")
FOLDER = "pass"     # what the workflow's form writes into, for the upload and the effects step


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


def read(transport, config: dict, run_id: str, previous, now: str, clock) -> dict:
    """Everything the pass reads after the wait, as `pass_.run` takes it."""
    controller = config["controller"]
    home, branch = controller["home"]["repo"], controller["home"]["branch"]
    kept = records.known(pass_.earlier(reads_.previous_records(previous), now) or [])
    try:
        runs = records.runs(transport, home, branch, [controller["workflows"]["run"], controller["workflows"]["approval"]],
                            dispatcher(controller), kept=kept)
    except Unanswered:
        runs = None
    try:
        numbers, whole = items.open_pull_requests(transport, home)
    except Unanswered:
        numbers, whole = [], False
    if not whole:
        raise Stop("pull_requests_unreadable")
    identities, approver, lenses, factory = accounts(controller)
    who = timeline.Accounts(transport, home, approver, lenses, factory)
    opens = opener(controller, config["kernel"], config["apps"])
    runs_whole = isinstance(runs, dict) and runs.get("complete") is True
    pulls = []
    for number in numbers:
        try:
            facts, title = facts_.snapshot(transport, home, number, identities, who, runs_whole, lambda: utc(clock),
                                           opener=opens)
            pulls.append({"facts": facts, "title": title})
        except Unanswered:
            pulls.append({"facts": {"item": {"repo": home, "type": "pull_request", "number": number}}, "title": None})
    return {"started": passes.started(transport, home, run_id), "pause": pause_.read(transport, home.split("/")[0], [home]),
            "records": runs, "pull_requests": pulls, "issues": [], "facts_reads": [], "usage": {}}


def one_pass(transport, config: dict, run_id: str, clock=time.time, sleep=time.sleep) -> dict:
    """One pass, through `transport`: the records before it, the wait, the reads, and what `pass_.run` returned."""
    controller = config["controller"]
    previous = passes.records(transport, controller["home"]["repo"], controller["home"]["branch"],
                              controller["workflows"]["poller"], int(run_id))
    sleep(pass_.wait_before_reading(previous, utc(clock), config))
    reads = read(transport, config, run_id, previous, utc(clock), clock)
    return pass_.run(reads, config, utc(clock), previous, mint_id)


def write(out: dict, directory: str) -> None:
    """`pass.json`, `writes.json` and `view/`, in the folder given, which was empty: each file is made new, and none is
    written through a link that was already there."""
    files = {"pass.json": out["record"], "writes.json": writes_.plan(out)}
    files.update({os.path.join("view", "%s.json" % name): out["view"][name] for name in VIEW})
    os.mkdir(os.path.join(directory, "view"))
    for name, document in files.items():
        made = os.open(os.path.join(directory, name), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with open(made, "w", encoding="utf-8") as f:
            f.write(json.dumps(document, indent=2, sort_keys=True) + "\n")


def main(argv=None, environ=None, base=None, clock=time.time, sleep=time.sleep, connect=Live) -> int:
    """The step. It writes only into an empty folder inside the directory it runs in, `base`, by default the working
    directory, and names no path, key or token in what it prints. The token is revoked whatever happened, and one GitHub
    did not revoke fails the step, `token_not_revoked`."""
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
        write(one_pass(transport, config, run_id, clock, sleep), out)
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
