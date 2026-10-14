# software-factory: Kernel proof of concept

A small proof of concept of the Factory's decision core, built to test one claim: that every
decision can be a pure function of facts read from GitHub and the Factory's own run records, and
that such a function can be checked before it is trusted.

The design it implements is in `petry-projects/.github-private`, at
`docs/architecture/software-factory-design.md`.

## What is here

- **Schemas** for the facts, a run record, a Decision, a Finding, an acceptance contract, a rubric,
  the authority table, the Lifecycle and the Kernel's configuration, each with an example.
- **A validator** for those schemas in about a hundred lines, with no dependencies.
- **The Kernel** for a pull request: derived State, Convergence, Admission and the attention class.
- **Checks**: Kernel purity, Lifecycle termination, authority, examples.
- **A simulator** that plays the poller, the jobs of a Run and the people, and injects stale reads,
  incomplete reads, dropped ticks, a Run missing from the list, and Runs killed mid-flight.
- **A mutation check** that breaks one rule at a time.

## What is not here

Anything that touches GitHub, any model, any workflow, the issue Lifecycle, acceptance evidence in
Convergence, and the control room.

## Run it

`make verify`. Python 3.9 or later; nothing to install.
