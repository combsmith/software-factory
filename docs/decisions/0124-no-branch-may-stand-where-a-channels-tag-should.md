# 0124. No branch may stand where a Channel's tag should

Status: accepted. The Maintainer's approval of 2026-11-02, by the Factory Builder, of what the security read of the shims of "Workflows: the frozen entry shim, the poller, the Run's three jobs and the nudge, each held to its shape" (issue 196) found.

## Decision

| What | Decided | Because |
|---|---|---|
| The fault | A shim's `uses: ...@factory/v0-next` also resolves a branch of that name, whenever no tag has it: before the first cut, or after a delete. A shim inherits secrets, so anyone with write could push such a branch and have the next tick run its file with every key, reviewed by no one and past the `main` and tag rulesets alike | Decision 0115 says the tag rulesets guard every key, and they guard tags alone |
| The rule | A ruleset, `factory channel branches`, refuses the creation of any branch named under factory/, at any depth, with no one able to bypass it, the admin role included. No branch may be named so | Refusing the name closes it whatever the tag's state, and a repo's own branches have no need of it |
| What it leaves | It targets branches alone, so it cannot refuse the release App's tags, which the two tag rulesets go on holding | The canary made a tag of that shape with it on |
| Its order | It goes on the repo before the shims go live. It is applied by the Factory Builder, on the Maintainer's word, once this check is on `main`, and its id is then recorded | A shim on `main` with no such ruleset is the fault itself |

## Why

The security read took this from GitHub's documentation and P-55, and the canary then ran it: a caller at `@rcase/v1` ran a branch's file with no tag of that name (run 41546839560), the tag's with both (run 41546922796), and the branch's again once the tag was deleted (run 41546954800). So a tag wins while it exists and protects nothing while it does not. With the ruleset on, the canary refused a branch one level and two levels down under the pattern, to its admin too, and made a branch beside it and a tag of that shape.

The pattern is `refs/heads/factory/**/*`, as run. An id is recorded null until GitHub gives one, and `tools/rulesets_drift.sh` says so until then, since it reads the live rulesets and this check reads only the file. Whether the live repo holds the rule is that script's to say, as for every ruleset here.

## Boundaries

| Boundary | Check |
|---|---|
| The ruleset is recorded, active, on branches named under factory/ alone, refusing their creation, with no one able to bypass it and no name left out | `tests/test_tools.py::test_no_branch_may_stand_where_a_channels_tag_should` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
