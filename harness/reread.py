"""The item read again by a Run's own credential, as the pass reads it, for `apply` and the approving act (decisions
0054 and 0055): the facts, the head commit the snapshot was held to, the run records and the context.

The run records are the records port's list of the Role workflow files, counted by the pass's own token's account;
the Pause is `FACTORY_PAUSED` on the org and on the item's repo; the facts are the facts port's snapshot of the pull
request, with the accounts `controller/1` holds, the App that opens pull requests (issue 295), whether the run
records were read whole and what the item's Lenses recorded in them (`adapters/applied.py`), and how the issue it was
opened for stands, as the pass joins it (decision 0232). The context is built from
them by `controller/pass_.context_of`, as one pass builds it, with no pass records before, so `passes_since` is
unreadable, which defers nothing. What cannot be read raises, named by its stage (`harness/shared.unread`), a fault of
a read's own code as a read GitHub did not answer, and the job that asked records whose fault it was. The Pause's port
raises nothing: a Pause it could not read is the context's, unless the job asks for it by name, and then it is raised
as a read of the `pause` stage, its part the port's (decision 0192)."""
from __future__ import annotations

from adapters import applied, facts as facts_, issues as issues_, pause as pause_, records, timeline
from adapters.github import Unanswered
from controller import issue_holds, pass_, reads as reads_
from harness import shared


def _parted(err: Exception, part: str) -> Exception:
    err.part = part
    return err


def issue_stood(transport, config: dict, home: str, facts: dict, who) -> dict:
    """`facts`, with how the issue the Factory opened the pull request for stands, as the pass joins it (decision 0232,
    issue 964): issue N read by the issues port's `stood`, its state and its own label events told by `who`, the account
    reader the pull request was read with, and `issue_stands` filled by `controller/issue_holds.join`, so by the Kernel's
    `stands`. One that cannot be read, or that moved while read, gives null, and the Kernel defers the act. A pull
    request opened for no issue asks nothing."""
    number = issue_holds.opened_for(facts)
    if number is None:
        return facts
    try:
        stood = {number: issues_.stood(transport, home, number, who)}
    except Unanswered:
        stood = {}
    return issue_holds.join([{"facts": facts}], stood, pass_.issue_config(config["kernel"]))[0]["facts"]


def held(record) -> dict:
    """What the pass record that admitted the Run already read of the Runs' outcomes, for the records port to keep and
    not read again: `kept` and `engines`, as a pass keeps them from the records before it (`records.known` and
    `records.engines`), from that one record; none from what is not a `pass/1` record. An outcome is written once, by
    its attempt's last step, so one the pass read stands for that attempt; a Run that ended after the pass, or whose
    outcome the pass read as none, is read as before. So a Run reads the outcomes of the Runs that failed since its
    pass, not of every Run that ever failed."""
    if not isinstance(record, dict) or shared.errors(record, "pass"):
        return {"kept": {}, "engines": {}}
    return {"kept": records.known([record]), "engines": records.engines([record])}


def item(transport, config: dict, number: int, now: str, clock, name_pause: bool = False, record=None) -> tuple:
    """`(facts, head, runs, context)` of pull request `number` of the home repo, read through `transport`. `config` is
    `controller/configuration.load`'s; `clock` gives the facts' `read_at`, `now` the time the context is built at. With
    `name_pause`, a Pause that is unreadable because the port could not read a scope is raised, named by that scope's
    part, the org's before the repo's; a scope that pauses, or a value that is no Pause, is the context's as before.
    `record`, the pass record that admitted the Run, gives the outcomes it read, which are not read again (`held`)."""
    controller = config["controller"]
    home, branch = controller["home"]["repo"], controller["home"]["branch"]
    with shared.staged("run_records"):
        listed = records.runs(transport, home, branch, facts_.run_files_of(controller), facts_.dispatcher_of(controller),
                              began={}, on={"repo": home, "type": "pull_request", "number": number}, **held(record))
    identities, approver, lenses, factory = facts_.accounts_of(controller)
    who = timeline.Accounts(transport, home, approver, lenses, factory, facts_.queue_of(controller))
    with shared.staged("lens_records"):
        found = applied.recorded(transport, home, listed, [number], set(config["kernel"]["required_lenses"]["model"]),
                                 config["authority"])
    with shared.staged("opened_records"):
        opened = applied.opened(transport, home, listed, facts_.opener_role(config["kernel"]))
    with shared.staged("snapshot"):
        facts, _, head = facts_.snapshot(transport, home, number, identities, who, listed.get("complete") is True, clock,
                                         with_head=True, opener=facts_.opener_of(controller, config["kernel"], config["apps"]),
                                         recorded=found[number], opened=opened)
    with shared.staged("issue_stood"):    # one not answered gives null; a fault of its own code is named (0187)
        facts = issue_stood(transport, config, home, facts, who)
    unread = []
    with shared.staged("pause"):
        if name_pause:
            paused, unread = pause_.explained(transport, home.split("/")[0], [home])
        else:
            paused = pause_.read(transport, home.split("/")[0], [home])
    with shared.staged("context"):     # no read: built from what the reads gave, and named as they are (decision 0187)
        rules = reads_.configured(controller)
        listed_, _, runs, _, _, _, context = pass_.context_of(listed, paused, [home], rules, now)
    if not listed_:
        with shared.staged("run_records"):
            raise Unanswered("the run records cannot be read")
    if unread and context["paused"] is None:
        with shared.staged("pause"):
            raise _parted(Unanswered("the Pause cannot be read"), unread[0])
    return facts, head, runs, context
