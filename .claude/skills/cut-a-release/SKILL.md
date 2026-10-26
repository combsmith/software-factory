---
name: cut-a-release
description: Cut a Release of the Factory, factory/vX.Y.Z, from main and move the next Channel to it, or roll next back to an earlier Release, through the release workflow and its eval gate. Use when a story or the Maintainer asks for a Release, a move of next, or a rollback, or to read why a cut was refused.
---

# Cut a Release

A Release is a lightweight tag `factory/vMAJOR.MINOR.PATCH` on a commit of `main`, and it never moves once made: a
ruleset with no bypass holds it. A Channel, `factory/v0-next` or `factory/v0-stable`, is a tag that moves. `next`
serves this repo (`release/rings.json`); `stable` serves nothing until slice 3 builds promotion. Read all of this
before the first step. The rules are `release/cut.py`'s, and the rulings are those of "Release: cut an immutable tag, move
next, and roll back in one action".

## Who does what

- **The cut and the move are the release workflow's**, release.yml under .github/workflows/, run by its App,
  `combsmith-sf-release`, in the environment `factory-release`. The Maintainer dispatches it, or the schedule does once
  he sets the repo variable `FACTORY_RELEASE_AUTO` to `true`. It is the next pull request's; until it is on `main`,
  nothing here can cut.
- **A session never** mints a credential, runs `gh auth token` or anything with `--show-token`, opens the App's key,
  writes or deletes a tag, or dispatches the release workflow. It reads, plans, and hands the Maintainer the one command.

## Before anything runs

- **The Pause.** Read `FACTORY_PAUSED` on the org and this repo. A rollback runs under a Pause; a cut waits.
- **The commit.** It is on `main`, and `verify` concluded `success` on it.
- **The eval gate (ruling 4″).** `next` moves only to a commit whose eval report holds a `pass` verdict for every case
  `evals/pr-review` names at that commit, scored against the review's rubric, the count equal to the set's, and the set
  not empty. Today the set's `count` is 0, so the gate is closed and every cut and move is refused,
  `eval_gate_closed`. That is right: a gate-deciding Intent does not serve without its eval set (design section 9.1).
- **Which step.** A cut, a move forward to an existing Release, or a rollback.

## The plan, in this session

Read every factory/ tag through the Maintainer's gh login into a scratch directory outside the repo, as
`adapters/tags.py` reads them: `gh api repos/combsmith/software-factory/git/matching-refs/tags/factory`. Write the
step, the refs as `{name: commit}`, and the commit's facts (`commit`, `on_main`, `verified`, `gate`) as three JSON
files, then plan. It is pure and writes nothing:

```bash
python3 -m release.move plan step.json refs.json facts.json
```

It prints the writes, or `{"refused": code}`. Each code is a constant of `release/cut.py`: say which rule refused,
and stop. A refused cut burns no version.

## The step, at the Maintainer's dispatch

A cut of the next version, which creates the tag and then moves `next`:

```bash
gh workflow run release.yml -R combsmith/software-factory -f command=cut -f version=factory/v0.X.Y
```

A rollback, with no eval gate, so that it works while the Factory is broken. It moves `next` back to the greatest
Release below the one it is on unless `to` names another earlier one, and never forward:

```bash
gh workflow run release.yml -R combsmith/software-factory -f command=rollback
gh workflow run release.yml -R combsmith/software-factory -f command=rollback -f to=factory/v0.X.Y
```

Runs already started finish on the Release they started on. If that Release is writing harm, set the Pause first.

## Read back

Read the run's conclusion, the Deployment it recorded on `factory-next`, and the tags again. The step is done when
the tag and `next` name the commit the plan named. A rollback is timed from the dispatch to its read-back, against
FR-49's 15 minutes.

## When the workflow cannot run

The fallback is the Maintainer's own admin login, at his terminal, which records itself as his act: one update of
the `next` ref with `force`, then the same read-back. No dispatch input skips the eval gate; this is the only way
past it, and it is his.

## Verify, then hand over

Run `make verify`. A fixture of a cut or a rollback is kept under release/, redacted as a trial's is.
