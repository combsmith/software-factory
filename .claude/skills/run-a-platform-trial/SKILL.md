---
name: run-a-platform-trial
description: Run one platform trial from section 6 of the design in the canary repo, combsmith/software-factory-canary, and bring what GitHub answered into trials/ as a fixture, by pull request. Use when a story asks for a trial such as P-3, or to add a fixture or ground a rule of the simulator's fake GitHub.
---

# Run a platform trial

A trial puts one question from section 6 of `docs/architecture/software-factory-design.md` to the
real GitHub, once, and keeps what it answered. That fixture is what the simulator's fake GitHub is
held to (section 4.5). Read all of this before the first step.

## Where it runs, and what never happens

- A trial runs in combsmith/software-factory-canary and nowhere else. The schema refuses a fixture
  from any other repo.
- Nothing in this repo reads the canary at run time. No code, test or workflow here names it, and
  `tools/check_trials.py` refuses one that does. What a trial saw arrives here as a file, in a
  pull request.
- A credential is named, never written: not in the fixture, the pull request, a commit message or
  this session's output. This session acts only as the Maintainer, through their own `gh` login.
  A step that must run as another identity (the machine user, an App, a workflow's token) runs in
  the canary, in a workflow there or at the Maintainer's own terminal, and its credential never
  enters this session.
- No long-lived credential is put in the canary. Nothing stores a real credential before trial
  P-3 has the verdict "unreadable"; until then a secret's value is a dummy.

## Steps

1. **Write the pass condition first.** Copy the question and the pass condition from the trial's
   row in section 6. Where section 6 gives no threshold, the story states one: copy that. Start
   the fixture with `trial`, `question` and `pass` before anything runs. A condition written after
   the answer is not a pass condition.
2. **Check what it needs.** Each identity and setting the trial needs exists in the canary; the
   epic's table of what only the Maintainer can do says which are open. If one is missing, stop
   and say which.
3. **Make each request, and capture it whole.** `gh api --include` shows the status and headers.
   For each request record who made it (`as`: kind and name, never the credential), how (`via`),
   the call (method and path, GraphQL operation, command line, or workflow and event), the headers
   and body sent, then the status, headers and body that came back. Several requests are several
   entries of `exchanges`, in order. `ran_at` is when the trial started, in UTC to the second.
4. **Take out every credential.** Delete each header or field that carries one (authorization,
   cookie, a token in a body) and add where it was to `removed`, written as
   `exchanges[0].request.headers.authorization`. Delete it; do not leave a placeholder. Change
   nothing else: keep GitHub's words as it said them, even a model's name or the name of the proof
   of concept's private repo, which a fixture alone may hold. `make verify` refuses a field named
   for a credential and any string that starts like one: `ghp_`, `ghs_`, `github_pat_`, `Bearer`,
   a signed token.
5. **Give the verdict** against the condition of step 1: `pass` or `fail`. A fail opens an issue
   against the design, naming the trial, before any code depends on the answer.
6. **Save it** in `trials/`, named for the trial, as P-12.json, or P-3.push.json when a trial
   leaves more than one. Its form is `schemas/trial.schema.json`; `examples/trial.json` is one.
7. **Ground the fake.** In `sim/grounding.py`, find each rule whose trial is this one, and set its
   fixture to the new file if the fixture shows the rule holds. If it shows the fake is wrong,
   leave the rule unverified and say so in the issue of step 5: changing the fake is a story of
   its own. `make verify` prints every rule still unverified.
8. **Verify, then hand over.** `make verify` and `python3 -m tools.mutants` pass. The pull request
   holds the fixture and its grounding only, and is the Maintainer's to open. Its body names the
   trial, the verdict and what was removed.
9. **Leave the canary as it was.** Delete any secret, environment, branch or pull request the
   trial made there, unless the story says it stays.
