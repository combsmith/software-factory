# 0019. Under bypassPermissions, the protected hook tells and asks nothing

Status: accepted. Decided by the Maintainer on 2026-10-16, after the first session with the hooks
live found that the protected hook's "ask" prompts even under bypassPermissions, and that a session
on its own work (a push, an edit to `kernel/gate.py` or `config/hooks.json`) stopped for a person
again and again.

## Decision

When the session runs under bypassPermissions, `tools/hooks/protected.py` asks nothing. It gives
the session the same reasons it would have asked with, as context, and the command or edit goes on.
In any other mode, or with a mode it cannot read, it asks as before. This holds for every reason
the hook gives, a reading it could not finish among them. Where decisions 0016 and 0017 say the
protected hook asks the person, under bypassPermissions it tells the session instead.

The identity hook and the Stop hooks are unchanged in code, but not out of a session's reach. What
is no longer asked includes the files that hold them: the hooks themselves and their wiring
(`tools/hooks/`, `config/hooks.json`, `.claude/settings*.json`), git's configuration, and the
remote branch a stop compares with. A session under bypassPermissions could change the hooks the
next call runs, or the base the Stop hook lists changes against, with no person asked. The hooks
that run are the main checkout's, so a change to them in a worktree runs nowhere until it merges.

## Why

A session under bypassPermissions is one the Maintainer has set to run without them, and a prompt
there stops the work until they come back. The protected hook guards against mistakes; it was never
the boundary. The boundary is what reads the pull request: the required checks, the review that
approves it, and the rulesets. So the session is told what is the Maintainer's, says so in what it
reports, and the change is read there.

Keeping the ask for the hooks' own files alone was weighed and not taken: a push writes the remote
branch a stop compares with, and the hooks' stories edit them often, so the prompts would stay. A
session that disarms a hook still cannot pass CI, which checks out afresh, or the rulesets.

## Boundaries

| Boundary | Check |
|---|---|
| Under bypassPermissions, spelled exactly, a protected write is told to the session and not asked; under any other mode, or none, it is asked | `tests/test_hooks.py::test_under_bypass_permissions_the_hook_tells_the_session_and_asks_nothing` |
| Every reason, a reading the hook could not finish among them, is told and not asked under bypassPermissions | `tests/test_hooks.py::test_under_bypass_permissions_the_hook_tells_the_session_and_asks_nothing` |
