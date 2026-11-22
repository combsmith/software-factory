"""The mutants of `adapters/facts.py`: tools/mutants.py runs them."""

import pathlib

from tools.mutants_of.common import F901_ROLE, S3_NAMED, S3_PORT

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent      # the tree, above tools/mutants_of/


def moved_before(rel: str, block: str, anchor: str) -> tuple:
    """(old, new) for a mutant that moves `block` up to just before the `anchor` that comes ahead of it in `rel`;
    STALE, as `moved_after`, if either is not found."""
    text = (ROOT / rel).read_text()
    end = text.find(block)
    start = text.rfind(anchor, 0, end) if end >= 0 else -1
    if start < 0:
        return anchor + block, block + anchor
    middle = text[start:end]
    return middle + block, block + middle


TARGETS = ("adapters/facts.py",)
MUTANTS = [
    # Issue 342: a pull request the Factory opens is bound to its issue by the Run that opened it, as well as its branch.
    ("the snapshot hands acceptance no opening Runs", 'adapters/facts.py',
     'acceptance.bounded(transport, first, accounts, opener, opened)', 'acceptance.bounded(transport, first, accounts, opener)', ('tests.test_adapters',)),
    ("no Role opens pull requests whatever the configuration", 'adapters/facts.py',
     '    return intent["role"] if isinstance(intent, dict) else None', '    return None', ('tests.test_adapters',)),
    # Issue 346: a Lens review whose applied/1 is past retention on an open pull request is asked for again.
    ("the snapshot names no expired Run", 'adapters/facts.py',
     'if r.get("expired") is True),', 'if False),', ('tests.test_adapters',)),
    # Issue 526: the facts port reads the description's edits, and an absent edit time is unread, never none (0140).
    ("the snapshot leaves the edit time out", 'adapters/facts.py', '        "description_edited_at": edited,\n', '',
     ("tests.test_adapters.Snapshot.test_a_snapshot_holds_every_part_of_the_facts_and_the_title_beside_them",)),
    ("the snapshot gives no edit where the edits cannot be read", 'adapters/facts.py',
     '    edited = edits.last_edited_at(transport, first)\n',
     '    try:\n        edited = edits.last_edited_at(transport, first)\n    except Unanswered:\n        edited = None\n',
     ("tests.test_adapters.Snapshot.test_a_snapshot_whose_description_edits_cannot_be_read_is_refused",)),
    ('the snapshot holds no reopening', 'adapters/facts.py',
     '"last_reopened_at": timeline.reopened_at(events),',
     '"last_reopened_at": None,', ("tests.test_adapters",)),
    # Issue 331: a thread's resolver typed by its account, never by resolvedBy's type (P-49, P-53).
    ('the configuration holds no queue App', 'adapters/facts.py',
     '    return (held["id"], "Bot") if isinstance(held, dict) else None',
     '    return None', ('tests.test_adapters',)),
    ("the queue App is not the Factory's", 'adapters/facts.py',
     '    return identities, approver, lenses, factory | ({queue} if queue else set())',
     '    return identities, approver, lenses, factory', ('tests.test_adapters',)),
    # Issue 306: every write a Factory identity made matched to a recorded Effect (I-33, decision 0061).
    ('a snapshot refused keeps what it read', 'adapters/facts.py',
     '    raw = {}\n',
     '    raw = kept if kept is not None else {}\n', ("tests.test_adapters",)),
    ('a snapshot keeps no timeline', 'adapters/facts.py',
     '    raw["events"] = (events, timeline_whole)\n',
     '', ("tests.test_adapters",)),
    # Pull request 688, the fourth dry run: the approving act found no Decision, and could not have read its diff.
    ('a pull request that changed while read is a read that failed', 'adapters/facts.py',
     '        raise Moved("the pull request changed while it was read',
     '        raise Unanswered("the pull request changed while it was read', ("tests.test_adapters",)),
    # Issue 681, trials/P-65.json: each check is given its workflow run's id and its suite's conclusion, both always
    # written where GitHub gives them, refused in any form but their own, and left out only where an answer leaves them out.
    ('acceptance is never read whole', 'adapters/facts.py',
     '"complete": {"acceptance": contract_whole,',
     '"complete": {"acceptance": False,', ('tests.test_adapters',)),
    ('the threads are never read', 'adapters/facts.py',
     '        "threads": found,',
     '        "threads": [],', ('tests.test_adapters',)),
    ('a pusher with no time is kept', 'adapters/facts.py',
     '    if pusher is not None and pushed_at is None:\n',
     '    if False:\n', ('tests.test_adapters',)),
    ('a snapshot whose head moved is kept', 'adapters/facts.py',
     '    if not pull.unchanged(transport, first):\n',
     '    if False:\n', ('tests.test_adapters',)),
    ('acceptance is read whole', 'adapters/facts.py',
     '"complete": {"acceptance": contract_whole,',
     '"complete": {"acceptance": True,', ('tests.test_adapters',)),
    ('threads are whole whatever the read', 'adapters/facts.py',
     '"threads": threads_whole,',
     '"threads": True,', ('tests.test_adapters',)),
    ('the runs are whole whatever the pass read', 'adapters/facts.py',
     '"runs": runs_whole is True,',
     '"runs": True,', ('tests.test_adapters',)),
    ("an unseen push is the epoch's", 'adapters/facts.py',
     '        "last_push_at": pushed_at or now,\n',
     '        "last_push_at": pushed_at or "1970-01-01T00:00:00Z",\n', ('tests.test_adapters',)),
    ("the snapshot's time is taken before its reads", 'adapters/facts.py',
     *moved_before("adapters/facts.py", "    now = clock()\n", "    first = pull.read(transport, repo, number)\n"),
     ('tests.test_adapters',)),
    ('a snapshot outside facts/1 is kept', 'adapters/facts.py',
     '    if problems:\n',
     '    if False:\n', ('tests.test_adapters',)),
    # Asked once the issues are listed, as a pass that read their Runs would: `listed` exists only after the records are read.
    ('the diff is compared with the base the pull request last named', 'adapters/facts.py',
     '    content = pull.diff(transport, first, branch["head"])\n',
     '    content = pull.diff(transport, first, first["base"]["sha"])\n', ('tests.test_adapters',)),
    ('the files are compared with the base the pull request last named', 'adapters/facts.py',
     '    paths = pull.changed_paths(transport, first, branch["head"])\n',
     '    paths = pull.changed_paths(transport, first, first["base"]["sha"])\n', ('tests.test_adapters',)),
    # S3: the open issues are listed from `issues.served_from` and each read by the issues port, whose facts reach the
    # Kernel through the pass; an App is named by the id the configuration holds (the Factory Builder's ruling A).
    ('an account whose App the catalogue does not name is named', 'adapters/facts.py',
     ' and isinstance(apps.get(code), dict)',
     '', S3_PORT),
    ('an App whose account is not held is named by its id', 'adapters/facts.py',
     'if isinstance(account, dict) and isinstance(apps.get(code), dict)',
     'if isinstance(apps.get(code), dict)', S3_PORT),
    ('an App is named by its id with no suffix', 'adapters/facts.py',
     'apps[code]["name"] + BOT_SUFFIX for code',
     'apps[code]["name"] for code', S3_PORT),
    ("a Role's App is not named by its id", 'adapters/facts.py',
     ' + sorted((held.get("roles") or {}).items())\n    return {(account["id"], "Bot")',
     '\n    return {(account["id"], "Bot")', S3_PORT),
    # Issues 963 and 965, the reader audits of #918 and #912: each issue's read dated by its own answer, the issues'
    # configuration left as written and its Apps named plain, and every account held to the names an App's id holds.
    ('an App the catalogue holds with no name is named by the suffix alone', 'adapters/facts.py',
     ' and apps[code].get("name")}',
     '}', S3_PORT),
    # Issue 901: a Role's App held under `roles` alone comments as that Role and makes no counted act; the queue's or
    # a Lens's name declared an issue's App refuses the issues alone; the tracking issue is no Work item.
    ("the Roles' accounts are among those whose acts are counted", 'adapters/facts.py',
     'factory = bots(held["agents"]) | set(lenses) |',
     'factory = bots(held["agents"]) | roles_of(controller) | set(lenses) |', F901_ROLE + S3_NAMED),
    ('a Role with no account held cannot be told apart', 'adapters/facts.py',
     '\n            if isinstance(account, dict)}',
     '}', F901_ROLE),
    # Carbon on 0218: a torn read either way, a last page that names other links, and a writer's act apart from a comment.
    ("the Maintainer is no one's", 'adapters/facts.py',
     '    maintainer = {(held["maintainer"]["id"], "User")} if held["maintainer"] else set()\n',
     '    maintainer = set()\n', ('tests.test_controller.Entry.test_each_snapshot_is_read_with_the_configured_accounts_and_kept',)),
    ("the dependency bots are no one's", 'adapters/facts.py',
     '"dependency": bots(held["dependencies"])}',
     '"dependency": set()}', ('tests.test_controller.Entry.test_each_snapshot_is_read_with_the_configured_accounts_and_kept',)),
    ("the agents are no one's", 'adapters/facts.py',
     'identities = {"agent": bots(held["agents"]),',
     'identities = {"agent": set(),', ('tests.test_controller.Entry.test_each_snapshot_is_read_with_the_configured_accounts_and_kept',)),
    ('the approver is no one', 'adapters/facts.py',
     '    approver = (held["approver"]["id"], "User") if held["approver"] else (0, "User")\n',
     '    approver = (0, "User")\n', ('tests.test_controller.Entry.test_each_snapshot_is_read_with_the_configured_accounts_and_kept',)),
    ("a Lens's App is read as any App", 'adapters/facts.py',
     '    lenses = {(a["id"], "Bot"): a["lens"] for a in held["lenses"]}\n',
     '    lenses = {}\n', ('tests.test_controller.Entry.test_each_snapshot_is_read_with_the_configured_accounts_and_kept',)),
    ("the Controller's acts are no Factory's", 'adapters/facts.py',
     ' | ({(held["controller"]["id"], "Bot")} if held["controller"] else set())',
     '', ('tests.test_controller.Entry.test_each_snapshot_is_read_with_the_configured_accounts_and_kept',)),
    ("a dispatch of the pass's token is no Run", 'adapters/facts.py',
     '    return (token["id"], token["type"]) if token else (0, "Bot")\n',
     '    return (0, "Bot")\n', ('tests.test_controller.Entry.test_each_snapshot_is_read_with_the_configured_accounts_and_kept',)),
    # Muse's read of #194's PR 3.
    ('the head handed back is not the one read', 'adapters/facts.py',
     'return (facts, title, str(first["head"]["sha"])) if with_head',
     'return (facts, title, "0" * 40) if with_head', ('tests.test_adapters.Snapshot.test_a_snapshot_hands_back_its_head',)),
    # A fault of a read's own code is named as a read GitHub refused is (#688's sixth dry run, decision 0187).
    ("a snapshot names the part of a read GitHub refused and of no other fault", "adapters/facts.py",
     '    except Exception as err:\n        raise _named(err, part[0])\n',
     '    except Unanswered as err:\n        raise _named(err, part[0])\n', ('tests.test_adapters.Snapshot.test_a_snapshot_names_the_part_github_did_not_answer',)),
    ("a snapshot names a fault in putting the facts together as the last read's", "adapters/facts.py",
     '    part[0] = "assembly"', '    pass', ('tests.test_adapters.Snapshot.test_a_snapshot_names_the_part_github_did_not_answer',)),
    ("a snapshot names no part GitHub did not answer", "adapters/facts.py",
     '        err.part = part\n', '        pass\n', ('tests.test_adapters.Snapshot.test_a_snapshot_names_the_part_github_did_not_answer',)),
    ("a snapshot names the read before the one GitHub did not answer", "adapters/facts.py",
     '    part[0] = "timeline"\n', '', ('tests.test_adapters.Snapshot.test_a_snapshot_names_the_part_github_did_not_answer',)),
    ("a snapshot names a writer's read as the reviews'", "adapters/facts.py",
     '    part[0] = "writer"\n', '', ('tests.test_adapters.Snapshot.test_a_snapshot_names_the_part_github_did_not_answer',)),
    ("a snapshot names a label's read as the writer's", "adapters/facts.py",
     '    part[0] = "labels"\n', '', ('tests.test_adapters.Snapshot.test_a_snapshot_names_the_part_github_did_not_answer',)),
    ("a snapshot names a push with no time as the edits'", "adapters/facts.py",
     '    part[0] = "edits"\n    edited = edits.last_edited_at(transport, first)\n    part[0] = "push"\n',
     '    part[0] = "edits"\n    edited = edits.last_edited_at(transport, first)\n', ('tests.test_adapters.Snapshot.test_a_snapshot_names_the_part_github_did_not_answer',)),
    ("a snapshot out of its schema is named the last read's", "adapters/facts.py",
     '    part[0] = "schema"\n', '', ('tests.test_adapters.Snapshot.test_a_snapshot_names_the_part_github_did_not_answer',)),
    ("a pull request that moved is named a part", "adapters/facts.py",
     '    if not isinstance(err, Moved):\n', '    if True:\n', ('tests.test_adapters.Snapshot.test_a_snapshot_names_the_part_github_did_not_answer',)),
    # Issue 295: a pull request the Factory opens is bound to its issue by its branch, never its body.
    ('the snapshot is not told the opener', 'adapters/facts.py',
     '    contract, contract_whole, contract_cut = acceptance.bounded(transport, first, accounts, opener, opened)\n',
     '    contract, contract_whole, contract_cut = acceptance.bounded(transport, first, accounts, opened=opened)\n', ('tests.test_adapters.Snapshot.test_a_snapshot_reads_the_ask_of_the_openers_pull_request_by_its_branch',)),
    ('an untold opener is read as none', 'adapters/facts.py',
     '        return acceptance.UNTOLD\n', '        return None\n', ('tests.test_controller.Entry.test_the_app_that_opens_pull_requests_is_read_from_the_configuration_by_its_role',)),
    ("another App's account is the opener's", 'adapters/facts.py',
     ' \\\n            or account.get("login") != app["name"] + "[bot]":\n', ':\n', ('tests.test_controller.Entry.test_the_app_that_opens_pull_requests_is_read_from_the_configuration_by_its_role',)),
    ("another App's name is the Role's", 'adapters/facts.py',
     'if not app.get("name") or app["name"] != intent["app"] or ', 'if not app.get("name") or ', ('tests.test_controller.Entry.test_the_app_that_opens_pull_requests_is_read_from_the_configuration_by_its_role',)),
    ('the opener is never told', 'adapters/facts.py',
     '    return account["id"], "Bot"\n', '    return None\n', ('tests.test_controller.Entry.test_the_app_that_opens_pull_requests_is_read_from_the_configuration_by_its_role',)),
    # Issue 338: what each Lens recorded, read from its Runs' applied/1; every recorded thread read, opened by that Lens;
    # a Lens thread's category and severity joined from its one Finding the Lens owns.
    ('the snapshot holds the threads to nothing', 'adapters/facts.py',
     '    found, threads_whole = applied.held(*threads.read(transport, first, accounts, raw), recorded, content["content_id"])\n',
     '    found, threads_whole = threads.read(transport, first, accounts, raw)\n', ('tests.test_adapters.Snapshot.test_a_snapshot_holds_every_thread_read_and_says_whether_they_were_read_whole',)),
    # Issue 823: the facts name the issue the Factory opened a pull request for, a fact the schema does not require.
    ("the snapshot names no issue the Factory opened a pull request for", "adapters/facts.py",
     '        "opened_for": acceptance.opened_for(first, opener, opened),\n', '        "opened_for": None,\n', ('tests.test_adapters.Snapshot.test_a_snapshot_reads_the_ask_of_the_openers_pull_request_by_its_branch',)),
    ("the snapshot leaves out the issue a pull request was opened for", "adapters/facts.py",
     '        "opened_for": acceptance.opened_for(first, opener, opened),\n', '', ('tests.test_adapters.Snapshot.test_a_snapshot_reads_the_ask_of_the_openers_pull_request_by_its_branch',)),
    ("the snapshot asks the issue a pull request was opened for without the opening Runs' records", "adapters/facts.py",
     '        "opened_for": acceptance.opened_for(first, opener, opened),\n',
     '        "opened_for": acceptance.opened_for(first, opener, None),\n', ('tests.test_adapters.Snapshot.test_a_snapshot_reads_the_ask_of_the_openers_pull_request_by_its_branch',)),
    # Issue 347: a later review by the same Lens on the current content supersedes its earlier records.
    ('the snapshot does not tell the threads its content', 'adapters/facts.py',
     'raw), recorded, content["content_id"])', 'raw), recorded)', ('tests.test_adapters.Snapshot.test_a_snapshot_tells_the_threads_its_content_so_a_later_review_supersedes',)),
    # Issue 381, the queue step's first part: each queue act a dispatched Run of the queue workflow once it is named.
    ("the queue workflow's runs are read with no queue App's account", 'adapters/facts.py',
     'queue = workflows["queue"] if controller["accounts"]["queue"] is not None else None',
     'queue = workflows["queue"]', ('tests.test_controller.Record.test_the_queue_workflows_runs_are_read_once_it_is_named',)),
    ("the queue workflow's runs are never read", 'adapters/facts.py',
     ' + ([queue] if queue is not None else [])',
     '', ('tests.test_controller.Record.test_the_queue_workflows_runs_are_read_once_it_is_named',)),
    ("the snapshot leaves out whether the acceptance read was cut", 'adapters/facts.py',
     '        "acceptance_bounded": contract_cut,\n', '', ('tests.test_adapters.Snapshot.test_a_snapshot_says_whether_its_acceptance_read_was_cut',)),
    ("the snapshot says no acceptance read was cut", 'adapters/facts.py',
     '"acceptance_bounded": contract_cut,', '"acceptance_bounded": False,', ('tests.test_adapters.Acceptance.test_a_bound_issues_timeline_is_read_to_ten_pages_and_past_them_is_not_whole', 'tests.test_adapters.Snapshot.test_a_snapshot_says_whether_its_acceptance_read_was_cut')),
    ('the snapshot leaves out whether its own timeline was cut', 'adapters/facts.py',
     '        "timeline_bounded": timeline_cut or reviews_cut,\n', '', ('tests.test_adapters.Snapshot.test_a_snapshot_says_whether_its_own_timeline_was_cut',)),
    ('the snapshot reads its own timeline past ten pages', 'adapters/facts.py',
     'events, timeline_whole, timeline_cut = timeline.bounded(transport, first)', 'events, timeline_whole = timeline.events(transport, first)\n    timeline_cut = False', ('tests.test_adapters.Snapshot.test_a_snapshot_says_whether_its_own_timeline_was_cut',)),
    ('the snapshot says its own timeline was not cut', 'adapters/facts.py',
     '"timeline_bounded": timeline_cut or reviews_cut,', '"timeline_bounded": False,', ('tests.test_adapters.Snapshot.test_a_snapshot_says_whether_its_own_timeline_was_cut',)),
    ('a cut reviews list is not said', 'adapters/facts.py',
     '"timeline_bounded": timeline_cut or reviews_cut,', '"timeline_bounded": timeline_cut,', ('tests.test_adapters.Snapshot.test_a_snapshot_says_whether_its_own_timeline_was_cut',)),
    ("a cut timeline is not said", 'adapters/facts.py',
     '"timeline_bounded": timeline_cut or reviews_cut,', '"timeline_bounded": reviews_cut,', ('tests.test_adapters.Snapshot.test_a_snapshot_says_whether_its_own_timeline_was_cut',)),
    ('the reviews are not told the timeline was read short', 'adapters/facts.py',
     ', raw,\n                                                           timeline_whole)', ', raw)', ('tests.test_adapters.Snapshot.test_a_snapshot_says_whether_its_own_timeline_was_cut',)),
    ('the snapshot keeps the cut as none', 'adapters/facts.py',
     'raw["cut"] = {"events": timeline_cut, "reviews": reviews_cut}', 'raw["cut"] = {"events": False, "reviews": False}', ('tests.test_adapters.Snapshot.test_a_snapshot_says_whether_its_own_timeline_was_cut',)),
    ('a timeline read short is kept as cut', 'adapters/facts.py',
     'raw["cut"] = {"events": timeline_cut, "reviews": reviews_cut}',
     'raw["cut"] = {"events": not timeline_whole, "reviews": not reviews_whole}', ('tests.test_adapters.Snapshot.test_a_snapshot_says_whether_its_own_timeline_was_cut',)),
    ('the snapshot keeps no cut for the seen port', 'adapters/facts.py',
     '    raw["cut"] = {"events": timeline_cut, "reviews": reviews_cut}\n', '', ('tests.test_adapters.Snapshot.test_a_snapshot_keeps_its_reads_for_reconciliation_only_once_it_is_whole',)),
    ("the snapshot says its own timeline was cut", 'adapters/facts.py',
     '"timeline_bounded": timeline_cut or reviews_cut,', '"timeline_bounded": True,', ('tests.test_adapters.Snapshot.test_a_snapshot_says_whether_its_own_timeline_was_cut',)),
]
