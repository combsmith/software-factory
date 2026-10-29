"""The item read again by a Run's own credential, as the pass reads it, for `apply` and the approving act (decisions
0054 and 0055): the facts, the head commit the snapshot was held to, the run records and the context.

The run records are the records port's list of the Role workflow files, counted by the pass's own token's account;
the Pause is `FACTORY_PAUSED` on the org and on the item's repo; the facts are the facts port's snapshot of the pull
request, with the accounts `controller/1` holds, the App that opens pull requests (issue 295), whether the run
records were read whole and what the item's Lenses recorded in them (`adapters/applied.py`). The context is built from
them by `controller/pass_.context_of`, as one pass builds it, with no pass records before, so `passes_since` is
unreadable, which defers nothing. What cannot be read raises, and the job that asked records whose fault it was."""
from __future__ import annotations

from adapters import applied, facts as facts_, pause as pause_, records, timeline
from adapters.github import Unanswered
from controller import pass_, reads as reads_


def item(transport, config: dict, number: int, now: str, clock) -> tuple:
    """`(facts, head, runs, context)` of pull request `number` of the home repo, read through `transport`. `config` is
    `controller/configuration.load`'s; `clock` gives the facts' `read_at`, `now` the time the context is built at."""
    controller = config["controller"]
    home, branch = controller["home"]["repo"], controller["home"]["branch"]
    listed = records.runs(transport, home, branch, [controller["workflows"]["run"], controller["workflows"]["approval"]],
                          facts_.dispatcher_of(controller))
    identities, approver, lenses, factory = facts_.accounts_of(controller)
    who = timeline.Accounts(transport, home, approver, lenses, factory, facts_.queue_of(controller))
    found = applied.recorded(transport, home, listed, [number], set(config["kernel"]["required_lenses"]["model"]),
                             config["authority"])
    facts, _, head = facts_.snapshot(transport, home, number, identities, who, listed.get("complete") is True, clock,
                                     with_head=True, opener=facts_.opener_of(controller, config["kernel"], config["apps"]),
                                     recorded=found[number])
    paused = pause_.read(transport, home.split("/")[0], [home])
    rules = reads_.configured(controller)
    listed_, _, runs, _, _, _, context = pass_.context_of(listed, paused, [home], rules, now)
    if not listed_:
        raise Unanswered("the run records cannot be read")
    return facts, head, runs, context
