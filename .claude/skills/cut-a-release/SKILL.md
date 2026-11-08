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
  he sets the repo variable `FACTORY_RELEASE_AUTO` to `true` and no Pause is set. Its job mints the App's token for
  this repo alone, checks out the commit the run is of, `main`'s head, and runs `python3 -m release.move`, which cuts
  that commit. Until the App is registered and its key is in the environment, nothing can cut.
- **A session never** mints a credential, runs `gh auth token` or anything with `--show-token`, opens the App's key,
  writes or deletes a tag, or dispatches the release workflow. It reads, plans, and hands the Maintainer the one command.

## Before anything runs

- **The Pause.** Read `FACTORY_PAUSED` on the org and this repo. A rollback runs under a Pause; a cut waits.
- **The commit.** It is on `main`, and `verify` concluded `success` on it.
- **The eval gate (ruling 4″).** `next` moves only to a commit whose eval report for the cases `evals/pr-review` names at that
  commit, scored against the review's rubric, clears the bar of decision 0150: at least 90% of the clean cases passed and
  at least 30% of those that expect a Finding, no fault of the Engine or the run, and the set not empty (decision 0120).
  It guards against regression and sits under the measured recall, so a Release can go out with cases not passed, a
  blocking one among them: read the judge's line. A closed gate refuses every cut and move,
  `eval_gate_closed`: a gate-deciding Intent does not serve without its eval set (design section 9.1).
  The gate reads the commit's latest successful eval dispatch, so the review Intent's set, `pr-review`, is dispatched last,
  and a re-dispatch can still make it the best of several. Once `config/harness.json` names a gate set, `gate_set`, the
  gate pools every dispatch of it on the commit instead: have it dispatched three times on the commit, nothing between
  them. One cancelled, or stopped by the Engine or the Factory, closes the gate for that commit (decision 0169). Each
  asks the set's preflight first, and one it stopped, `preflight_failed`, closes it too: mend the pipeline before a
  dispatch on a new commit (decision 0170, the preflight).
- **The release key's environment.** Only `factory-release`'s deployment branches keep the App's key from another ref's copy
  of a workflow, and nothing in the repo can hold them. Have the Maintainer run `sh tools/environments_drift.sh` at a terminal, and stop if it says anything but `no drift`.
- **Which step.** A cut, a move forward to an existing Release, or a rollback.

## The plan, in this session

Read every factory/ tag through the Maintainer's gh login into a scratch directory outside the repo, as
`adapters/tags.py` reads them: `gh api repos/combsmith/software-factory/git/matching-refs/tags/factory`. Write one
JSON object of the reads: `step`, `refs` as `{name: commit}`, and `facts`, the commit's (`commit`, `on_main`,
`verified`, `gate`, and the `release` the gate judged). Plan from it on standard input. It is pure and writes nothing:

```bash
python3 -m release.move plan < reads.json
```

It prints the writes, or `{"refused": code}`. Each code is a constant of `release/cut.py`: say which rule refused,
and stop. A refused cut burns no version.

## The step, at the Maintainer's dispatch

A cut of `main`'s head as the next version, which creates the tag and then moves `next`; with no version, it is the
next patch:

```bash
gh workflow run release.yml -R combsmith/software-factory -f command=cut -f version=factory/v0.X.Y
```

A move of `next` forward to an existing Release, through the same gate, judged for that Release:

```bash
gh workflow run release.yml -R combsmith/software-factory -f command=move -f to=factory/v0.X.Y
```

A rollback, with no eval gate, so that it works while the Factory is broken. It moves `next` back to the greatest
Release below the one it is on unless `to` names another earlier one, and never forward. With no earlier Release it is
refused `no_earlier_release` and writes nothing (`release/fixtures/rollback.refused.json`):

```bash
gh workflow run release.yml -R combsmith/software-factory -f command=rollback
gh workflow run release.yml -R combsmith/software-factory -f command=rollback -f to=factory/v0.X.Y
```

Runs already made, those still waiting too, finish on the Release GitHub resolved for them (decision 0123). If that
Release is writing harm, set the Pause first.
Release runs go one at a time, and GitHub replaces a run still waiting with a newer one: read that the rollback's run
concluded, and dispatch it again if the schedule's took its place.

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
