"""The mutants of `harness/push_steps.py`: tools/mutants.py runs them."""

# The push whole (issue 838; the Solution Architect's ruling 2 of 2026-11-28).
LANDS = ('tests.test_harness.Push.test_a_push_lands_exactly_its_patch_through_every_check',)
REFUSES = ('tests.test_harness.Push.test_the_loop_refuses_on_each_check',)
PUSH_PY = 'harness/push_steps.py'

TARGETS = (PUSH_PY,)
MUTANTS = [
    ("a push to another repo is pushed", PUSH_PY,
     '    why = push_loop.first((("consumer", lambda: judged.consumer(repo, told["own"])), ("listed", listed),\n',
     '    why = push_loop.first((("consumer", lambda: None), ("listed", listed),\n', REFUSES),
    ("the list is read at the admitted commit alone", PUSH_PY,
     '        for sha in dict.fromkeys((default, parent)):\n',
     '        for sha in dict.fromkeys((parent,)):\n', REFUSES),
    ("the list is read at the default head alone", PUSH_PY,
     '        for sha in dict.fromkeys((default, parent)):\n',
     '        for sha in dict.fromkeys((default,)):\n', REFUSES),
    ("the contract's paths are not held", PUSH_PY,
     '            patterns += said\n        changes, why = _read(reading, sender, told)\n',
     '            pass\n        changes, why = _read(reading, sender, told)\n', REFUSES),
    ("the paths that land are not asked about", PUSH_PY,
     '        return why or apply.push_refusal(paths, read, sorted(set(patterns)))\n',
     '        return why or apply.push_refusal([], [], sorted(set(patterns)))\n', REFUSES),
    ("a first push off the default head goes on", PUSH_PY,
     '        return None if not first or case in (base.HEAD, base.ANCESTOR) else BASE_UNREAD if case is None else OFF_DEFAULT\n',
     '        return None if not first or case in (base.HEAD, base.ANCESTOR, base.NEITHER) else BASE_UNREAD if case is None else OFF_DEFAULT\n',
     REFUSES),
    ("the workflows at the admitted commit are not read again", PUSH_PY,
     '        for sha in dict.fromkeys((standing()[1], parent)):\n',
     '        for sha in dict.fromkeys((standing()[1],)):\n', REFUSES),
    ("the workflows at the default head are not read again", PUSH_PY,
     '        for sha in dict.fromkeys((standing()[1], parent)):\n',
     '        for sha in dict.fromkeys((parent,)):\n', REFUSES),
    ("a workflow's refusal lets the push go on", PUSH_PY,
     '            why = why or workflows.refusal_at(files, got["list"], told["default"], told["own"])\n',
     '            why = why or workflows.refusal_at(files, got["list"], told["default"], told["own"]) and None\n', REFUSES),
    ("a default head that moved before the branch's write is written", PUSH_PY,
     '    if moved != got["base"][1]:\n',
     '    if moved is None:\n', REFUSES),
    ("an admitted commit off the default head after the write lands", PUSH_PY,
     '    case = base.on_default(reader, repo, parent)[0] if first else base.HEAD\n',
     '    case = base.HEAD\n', REFUSES),
    ("a removed file is written as no change", PUSH_PY,
     '        return port.make_tree(repo, state["tree"], entries + removed)\n',
     '        return port.make_tree(repo, state["tree"], entries)\n', LANDS),
    ("a push told in part goes on", PUSH_PY,
     '    if type(told) is not dict or set(told) != set(TOLD):\n',
     '    if type(told) is not dict:\n', REFUSES),
]
