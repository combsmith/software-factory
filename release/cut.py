"""The rules that cut a Release and move a Channel, pure (rulings 4, 4″ and 5′).

`plan(step, refs, facts, channels)` returns `(writes, None)` or `([], code)`. `refs` is every `factory/` tag and the
commit it names, `{name: sha}`; `channels` the Channels `release/rings.json` declares; `facts` what was read of the
commit asked about, which it names (`commit`): whether it is on `main` (`on_main`), whether `verify` concluded success
on it (`verified`), and the eval gate's verdict on it (`gate`, `harness.eval.verdict`'s word, `pass` or why not) for
the Release it judged (`release`). A write is `("create", tag, commit)` or `("move", channel, commit)`; nothing here
writes it. A commit is its full sha; refs that hold anything else, or a step that cannot be read, are refused.

- `cut` (`version`, `commit`, `channel`): the tag is created and the Channel moved to it, in one plan, only when
  every rule holds; the eval gate is read before anything is written, so a closed gate burns no version.
- `move` (`channel`, `to`): the Channel moves to an existing Release, through the same gate.
- `rollback` (`channel`, `to` or none): the Channel moves back to an existing Release below the one it points at, by
  default the greatest, with no gate, so that it works while the Factory is broken (section 9.1). Since it passes no
  gate, it never moves forward, nor from a Channel at no Release: that is the Maintainer's admin login (ruling 5′).

A Channel moves only to a commit that is one Release's alone, so that `release/current.py` names it after the move.
No step writes a Release tag once it exists, nor `stable` until slice 3 builds promotion.
"""
from __future__ import annotations

from release import current

NOT_ON_MAIN = "not_on_main"
NOT_VERIFIED = "not_verified"
ALREADY_RELEASED = "already_released"
NOT_NEWER = "not_newer"
ANOTHER_MAJOR = "another_major"
RELEASE_IS_IMMUTABLE = "release_is_immutable"
NOT_A_RELEASE = "not_a_release"
PROMOTION_NOT_BUILT = "promotion_not_built"
EVAL_GATE_CLOSED = "eval_gate_closed"
NOT_A_CHANNEL = "not_a_channel"
NO_EARLIER_RELEASE = "no_earlier_release"
NOT_EARLIER = "not_earlier"
STEP_UNREADABLE = "step_unreadable"
PASS = "pass"
CODES = frozenset({NOT_ON_MAIN, NOT_VERIFIED, ALREADY_RELEASED, NOT_NEWER, ANOTHER_MAJOR, RELEASE_IS_IMMUTABLE,
                   NOT_A_RELEASE, PROMOTION_NOT_BUILT, EVAL_GATE_CLOSED, NOT_A_CHANNEL, NO_EARLIER_RELEASE,
                   NOT_EARLIER, STEP_UNREADABLE})
HEX = frozenset("0123456789abcdef")
SHA_LENGTH = 40


def sha(value) -> bool:
    """A commit, as GitHub names it: forty lower-case hex digits."""
    return isinstance(value, str) and len(value) == SHA_LENGTH and set(value) <= HEX


def releases(refs) -> dict:
    """Every Release among `refs`, by its version: {(MAJOR, MINOR, PATCH): name}."""
    return {current.version(name): name for name in refs if current.version(name)}


def _ring(name, channels) -> tuple:
    """(the Channel's major, None) for a Channel a step may move, or (None, the code that refuses it)."""
    if current.version(name):
        return None, RELEASE_IS_IMMUTABLE
    found = current.channel(name)
    if not found or name not in channels:
        return None, NOT_A_CHANNEL
    if found[1] == "stable":
        return None, PROMOTION_NOT_BUILT
    return found[0], None


def _gated(facts, release) -> str | None:
    """None when a Channel may move to the commit read: `verify` passed on it and the eval gate is open for `release`;
    else the code."""
    if facts.get("verified") is not True:
        return NOT_VERIFIED
    if facts.get("gate") != PASS or facts.get("release") != release:
        return EVAL_GATE_CLOSED
    return None


def plan(step, refs, facts, channels) -> tuple:
    """`(writes, None)` for the step asked, or `([], code)`; see the module's docstring."""
    if not isinstance(step, dict) or not isinstance(refs, dict) or not isinstance(facts, dict) \
            or not isinstance(channels, (set, frozenset)):
        return [], STEP_UNREADABLE
    if not all(isinstance(name, str) and sha(commit) for name, commit in refs.items()):
        return [], STEP_UNREADABLE
    command = step.get("command")
    major, refused = _ring(step.get("channel"), channels)
    if refused:
        return [], refused
    if command == "cut":
        return _cut(step, refs, facts, major)
    if command == "move":
        return _move(step, refs, facts, major)
    if command == "rollback":
        return _rollback(step, refs, major)
    return [], STEP_UNREADABLE


def _cut(step, refs, facts, major) -> tuple:
    name, commit = step.get("version"), step.get("commit")
    wanted = current.version(name)
    if not wanted or not sha(commit) or facts.get("commit") != commit:
        return [], STEP_UNREADABLE
    if facts.get("on_main") is not True:
        return [], NOT_ON_MAIN
    gated = _gated(facts, name)
    if gated == NOT_VERIFIED:
        return [], gated
    if any(at == commit for tag, at in refs.items() if current.version(tag)):
        return [], ALREADY_RELEASED
    if any(wanted <= have for have in releases(refs)):
        return [], NOT_NEWER
    if wanted[0] != major:
        return [], ANOTHER_MAJOR
    if gated:
        return [], gated
    return [("create", name, commit), ("move", step["channel"], commit)], None


def _target(name, refs, major) -> tuple:
    """(the commit of the Release `name`, None), or (None, the code that refuses moving a Channel to it): it must be an
    existing Release of the Channel's major, whose commit no other Release names."""
    wanted = current.version(name)
    if not wanted or name not in refs or current.resolve(refs[name], refs) != name:
        return None, NOT_A_RELEASE
    if wanted[0] != major:
        return None, ANOTHER_MAJOR
    return refs[name], None


def _move(step, refs, facts, major) -> tuple:
    commit, refused = _target(step.get("to"), refs, major)
    if refused:
        return [], refused
    if facts.get("commit") != commit:
        return [], STEP_UNREADABLE
    if facts.get("on_main") is not True:
        return [], NOT_ON_MAIN
    gated = _gated(facts, step["to"])
    if gated:
        return [], gated
    return [("move", step["channel"], commit)], None


def next_version(channel, refs) -> str | None:
    """The version a cut asked with none is of: the next patch of the greatest Release of the Channel's major, or that
    major's first, `.1.0`, where it has none (ruling 2); None for a name that is no Channel."""
    found = current.channel(channel)
    if not found:
        return None
    mine = [v for v in releases(refs) if v[0] == found[0]]
    if not mine:
        return "%s%d.1.0" % (current.PREFIX, found[0])
    top = max(mine)
    return "%s%d.%d.%d" % (current.PREFIX, top[0], top[1], top[2] + 1)


def default_target(channel, refs) -> str | None:
    """The greatest Release below the one `channel` points at, of its major and its commit's alone; None when there is
    none."""
    major = current.channel(channel)[0] if current.channel(channel) else None
    at = current.resolve(refs.get(channel), refs)
    if major is None or at is None:
        return None
    below = [v for v, name in releases(refs).items()
             if v[0] == major and v < current.version(at) and current.resolve(refs[name], refs) == name]
    return releases(refs)[max(below)] if below else None


def _rollback(step, refs, major) -> tuple:
    to = step.get("to")
    if to is None:
        to = default_target(step["channel"], refs)
        if to is None:
            return [], NO_EARLIER_RELEASE
    commit, refused = _target(to, refs, major)
    if refused:
        return [], refused
    at = current.resolve(refs.get(step["channel"]), refs)
    if at is None or not current.version(to) < current.version(at):
        return [], NOT_EARLIER
    return [("move", step["channel"], commit)], None
