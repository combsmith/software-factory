"""The rules that cut a Release and move a Channel, pure (rulings 4, 4″ and 5′).

`plan(step, refs, facts)` returns `(writes, None)` or `([], code)`. `refs` is every `factory/` tag and the commit it
names; `facts` is what was read of the commit asked about, which it names (`commit`): whether it is on `main`
(`on_main`), whether `verify` concluded success on it (`verified`), and the eval gate's verdict on it (`gate`,
`harness.eval.verdict`'s word, `pass` or why not). A write is `("create", tag, commit)` or `("move", channel, commit)`; nothing here writes it.

- `cut` (`version`, `commit`, `channel`): the tag is created and the Channel moved to it, in one plan, only when
  every rule holds; the eval gate is read before anything is written, so a closed gate burns no version.
- `move` (`channel`, `to`): the Channel moves forward to an existing Release, through the same gate.
- `rollback` (`channel`, `to` or none): the Channel moves back to an existing Release below the one it points at, by
  default the greatest, with no gate, so that it works while the Factory is broken (section 9.1). Since it passes no
  gate, it never moves forward, nor from a Channel at no Release: that is the Maintainer's admin login (ruling 5′).

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


def releases(refs) -> dict:
    """Every Release among `refs`, by its version: {(MAJOR, MINOR, PATCH): name}."""
    return {current.version(name): name for name in refs if current.version(name)}


def _ring(name) -> tuple:
    """(the Channel's ring, None) for a Channel a step may move, or (None, the code that refuses it)."""
    if current.version(name):
        return None, RELEASE_IS_IMMUTABLE
    found = current.channel(name)
    if not found:
        return None, NOT_A_CHANNEL
    if found[1] == "stable":
        return None, PROMOTION_NOT_BUILT
    return found, None


def _gated(facts) -> str | None:
    """None when `next` may move to the commit read: `verify` passed on it and the eval gate is open; else the code."""
    if facts.get("verified") is not True:
        return NOT_VERIFIED
    if facts.get("gate") != PASS:
        return EVAL_GATE_CLOSED
    return None


def plan(step, refs, facts) -> tuple:
    """`(writes, None)` for the step asked, or `([], code)`; see the module's docstring."""
    if not isinstance(step, dict) or not isinstance(refs, dict) or not isinstance(facts, dict):
        return [], STEP_UNREADABLE
    command = step.get("command")
    found, refused = _ring(step.get("channel"))
    if refused:
        return [], refused
    major = found[0]
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
    if not wanted or not isinstance(commit, str) or not commit:
        return [], STEP_UNREADABLE
    if name in refs:
        return [], NOT_NEWER
    if facts.get("commit") != commit:
        return [], STEP_UNREADABLE
    if facts.get("on_main") is not True:
        return [], NOT_ON_MAIN
    gated = _gated(facts)
    if gated == NOT_VERIFIED:
        return [], gated
    if any(sha == commit for tag, sha in refs.items() if current.version(tag)):
        return [], ALREADY_RELEASED
    if any(wanted <= have for have in releases(refs)):
        return [], NOT_NEWER
    if wanted[0] != major:
        return [], ANOTHER_MAJOR
    if gated:
        return [], gated
    return [("create", name, commit), ("move", step["channel"], commit)], None


def _target(name, refs, major) -> tuple:
    """(the commit of the Release `name`, None), or (None, the code that refuses moving a Channel to it)."""
    wanted = current.version(name)
    if not wanted or name not in refs:
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
    gated = _gated(facts)
    if gated:
        return [], gated
    return [("move", step["channel"], commit)], None


def default_target(channel, refs) -> str | None:
    """The greatest Release below the one `channel` points at, of its major; None when there is none."""
    major = current.channel(channel)[0] if current.channel(channel) else None
    at = current.resolve(refs.get(channel), refs)
    if major is None or at is None:
        return None
    below = [v for v in releases(refs) if v[0] == major and v < current.version(at)]
    return releases(refs)[max(below)] if below else None


def _rollback(step, refs, major) -> tuple:
    to = step.get("to") or default_target(step["channel"], refs)
    if to is None:
        return [], NO_EARLIER_RELEASE
    commit, refused = _target(to, refs, major)
    if refused:
        return [], refused
    at = current.resolve(refs.get(step["channel"]), refs)
    if at is None or not current.version(to) < current.version(at):
        return [], NOT_EARLIER
    return [("move", step["channel"], commit)], None
