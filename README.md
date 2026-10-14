# software-factory

The decision core of the Factory, and the context its authors work from. It began as a proof of
one claim: that every decision can be a pure function of facts read from GitHub and the Factory's
own run records, and that such a function can be checked before it is trusted.

If you are about to change something, read `AGENTS.md`. It is one page.

## What is here

- **The Kernel** for a pull request: derived State, Convergence, Admission and the attention class.
- **Schemas** for the facts, a run record, a Decision, a Finding, an acceptance contract, a rubric,
  the authority table, the Lifecycle and the configuration, each with an example and with
  counter-examples that must be rejected. A validator for them with no dependencies.
- **Checks**: Kernel purity, Lifecycle termination, authority, examples, what must never be in the
  repo, the rules every workflow obeys, and the rules the documents themselves obey.
- **A simulator** that plays the poller, the jobs of a Run and the people, and injects stale reads,
  incomplete reads, dropped ticks, a Run missing from the list, and Runs killed mid-flight.
- **A mutation check** that breaks one Kernel rule at a time.
- **The context**: `AGENTS.md` here and in each directory, and under `docs/` the standards, the
  decision log, the lessons of the proof of concept, and the glossary.

## What is not here

Anything that touches GitHub, any model, any workflow that runs, the issue Lifecycle, acceptance
evidence in Convergence, and the control room.

## Local Development Commands

- Install: nothing. Python 3.9 or later, standard library only
- Dev run: there is nothing to run yet; the simulator runs inside the tests
- Test: `make verify`, then `python3 -m tools.mutants`
- Lint: `make verify` runs every check there is
- Typecheck: none; a type checker is an install (`docs/decisions/0014-where-this-repo-departs-from-the-orgs-standards.md`)

## Required Environment Variables

None. `SIM_SEEDS` is optional: the number of simulator seeds to run, 300 if unset;
`SIM_SEEDS=40 make verify` is a quicker local run.

The design this implements is `docs/architecture/software-factory-design.md`; its first section is
the whole of it on one page.
