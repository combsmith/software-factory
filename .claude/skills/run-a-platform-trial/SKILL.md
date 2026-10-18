---
name: run-a-platform-trial
description: Run one platform trial from section 6 of the design in the canary repo, combsmith/software-factory-canary, and bring what GitHub answered into trials/ as a redacted fixture, by pull request. Use when a story asks for a trial such as P-3, or to add a fixture or ground a rule of the simulator's fake GitHub.
---

# Run a platform trial

A trial puts one question from section 6 of `docs/architecture/software-factory-design.md` to the
real GitHub, once, and keeps what it answered. That fixture is what the simulator's fake GitHub is
held to (section 4.5). Read all of this before the first step. The canary is public, and so is
everything a trial leaves in it: its runs, logs and artifacts.

## Before anything runs

- **Order.** Section 6.1 runs the trials in batches. Batch 1, before any code: P-13; P-1, P-7,
  P-24; P-17, P-22; P-3; P-28, P-29; P-8; P-39. Batch 2, before the first approval: P-9, P-20; P-5,
  P-23, P-25; P-2; P-30; P-27, P-14, P-4; P-26. Batch 3, before the control room: P-11, P-19,
  P-21; P-16, P-18. Batch 4, as they come up: P-6, P-10, P-12, P-15. P-32, P-33 and P-34 run before
  the Factory's author is built. List `trials/` and check that every trial of an earlier batch has
  a fixture; if one has none, stop and ask the Maintainer.
- **Only the canary.** A trial runs in combsmith/software-factory-canary. Set
  `GH_REPO=combsmith/software-factory-canary` for every command of the trial, and name no other
  repo. P-8 needs twelve repos, P-11 the control room and the hub, P-19 a separate public repo,
  P-30 the Factory's own repo, and P-31 every repo an App is installed on: for these, stop and
  raise it with the Maintainer before anything runs. The fixture's schema accepts the canary,
  or the org `combsmith` for a trial about the org and its Apps alone, such as P-39 (decision
  0033), so any other trial outside the canary needs that decided first.
- **Nothing here reads the canary.** Only a document, a fixture, the fixture's example and its
  schema name it here, and so does `config/apps.json`, which declares where the Apps are
  installed and which nothing runs. `tools/check_trials.py` refuses any other file that names
  it. What a trial saw arrives here as a file, in a pull request.
- **Who acts.** This session acts only as the Maintainer, through their own `gh` login. The
  Maintainer is advised to give a trial session a fine-grained token scoped to the canary alone,
  installed outside the session. A step that must run as another identity (the machine user, an
  App, a workflow's token) runs in a workflow in the canary or at the Maintainer's own terminal.
- **Real credentials wait.** Nothing stores a real credential until P-3's fixture has the verdict
  `pass`, which means a secret restricted to the default branch was unreadable from a work
  branch. Until then a secret's value is a dummy. No long-lived credential is put in the canary.
- **What the Maintainer names.** The epic, "Epic: slice 0, foundations. The repo holds the line,
  its context is tested, and the platform facts are recorded", in its section "First: what only
  the Maintainer can do", says which identities and settings exist. If the trial needs one that
  is open there, stop and say which.

## Never, in this session

- A call that mints a credential: a registration token, an installation token, a runner's JIT
  config, a personal or fine-grained token. Such a step runs in a canary workflow or at the
  Maintainer's own terminal, and only its redacted result comes here.
- `gh auth token`, or any `--show-token`.
- `--verbose`, `GH_DEBUG`, `set -x`, or anything else that prints the request as it is sent.
- Reading a raw capture, or writing one inside the repo.

## A workflow in the canary

A trial run by a workflow logs in public. Before anything is printed, every field that can carry a
token is masked with `::add-mask::`. Better still, the workflow writes what it captures to a file,
runs the redaction on it (step 4) inside the job, and only then prints it or uploads it as an
artifact. No `set -x`, and no verbose curl.

## Steps

1. **Write the pass condition first.** Copy the question and the pass condition from the trial's
   row in section 6. Where section 6 gives no threshold, the story states one: copy that. Draft
   the fixture with `trial`, `question` and `pass` before anything runs. A condition written after
   the answer is not a pass condition.
2. **Capture outside the repo.** Make a scratch directory with `mktemp -d` and write every capture
   there, never under the repo. `gh api --include` writes the response's status and headers with
   its body, to a file: `gh api --include ... > "$dir/raw-1"`. It does not show the request, so
   record the request yourself: who made it (`as`: kind and name, never the credential), how
   (`via`), the call, every `-H` header you passed, and the body sent.
3. **Do not read it yet.** A raw capture is never printed, opened or read in this session.
4. **Redact it, then read only what comes out.** `python3 -m tools.redact_trial "$dir/raw-1"
   "$dir/clean-1"`, in the scratch directory. It deletes every field named for a credential, every
   header a fixture may not keep, and every string or line shaped like a credential, and says
   where, never what. Read only the clean file. Build the fixture from clean files: several
   requests are several entries of `exchanges`, in order; `ran_at` is when the trial started, in
   UTC to the second. In `removed`, write where each credential was, from what the redaction
   reported, as `exchanges[0].request.headers.authorization` for the header `gh` sent. Then run
   the redaction over the drafted fixture too: it deletes anything left and adds where to
   `removed`. Keep everything else as GitHub said it, even a model's
   name or the proof of concept's private repo, which a fixture alone may hold.
5. **Give the verdict** against the condition of step 1: `pass` or `fail`. A fail is told to the
   Maintainer, who opens an issue against the design before any code depends on the answer.
6. **Save it** in `trials/`, named for the trial, as P-12.json, or P-3.push.json when a trial
   leaves more than one. Its form is `schemas/trial.schema.json`; `examples/trial.json` is one.
   Run `python3 -m tools.check_trials` before any `git add`. If it finds a credential, delete the
   file, redact again, and tell the Maintainer: a credential that reached a file is rotated.
7. **Ground the fake.** In `sim/grounding.py`, find each rule whose trials include this one, and
   set its fixture to the new file if the fixture shows the rule holds. If it shows the fake is
   wrong, leave the rule unverified and say so to the Maintainer: changing the fake is a story of
   its own. A rule no trial asks cannot be grounded until a trial for it is added to section 6.
8. **Leave the canary as it was.** Undo everything the trial made, and list what was undone:
   - tokens and personal or fine-grained tokens: revoked, not left to expire;
   - deploy keys, self-hosted runners, webhooks and App installations: deleted;
   - environments and their secrets, repository secrets and variables: deleted;
   - branches, pull requests, issues, check runs and workflow runs that hold anything not redacted.

   Keep only what the story says stays.
9. **Verify, then hand over.** `make verify` and `python3 -m tools.mutants` pass. The pull request
   holds the fixture and its grounding only, and is the Maintainer's to open. Its body names the
   trial, the verdict, what was removed, and what step 8 undid.
