# 0205. Each lookup of the CLI's install is bounded by glibc, not the update by a timeout, which would lose the index it read

Status: accepted. The Factory Builder's ruling of 2026-11-13 on "The CLI's apt update is bounded by a timeout, so a stalled lookup cannot spend the install step" (issue 776), against the issue's own proposal, `sudo timeout 60 apt-get update`, which the trials below showed fails the install it was meant to save. It amends decision 0197's rows "The fix", "What still fails" and "How it is held", where they say the two apt lines have exactly their options and that a stalled name is bounded by no timeout; the rest of each row stands.

## Decision

| What | Decided | Because |
|---|---|---|
| The fault | A name that stalls rather than fails, as every ubuntu.com name did on 2026-11-11, is bounded by no apt option: `Acquire::https::Timeout` bounds a connection, not the lookup before it. Each of Azure's three index files costs an SRV lookup, `_https._tcp.azure.archive.ubuntu.com`, and an address lookup, each tried and waited out in turn, so a stall of 60 s a lookup kept the update six minutes, twice the step's three | The trials below: the unbounded update took 6 min at 60 s a lookup and 2 min at 20 s |
| Why not a timeout on the update | Killing `apt-get update` keeps none of the index it had read: apt moves what it fetched into place only as the update ends. Bounded at 90 s, an update had read kernel.org's `noble-updates` and `noble-security` whole by +21 s, was killed at 90 s, and the install answered "Unable to locate package bubblewrap". At 20 s a lookup, near 2026-11-11's, the unbounded update ends in 2 min and the step passes in 131 s; bounded at 60 s it is killed first, and the step fails | A bound on the update can only make the install fail sooner; at 2026-11-11's stall it fails a step that passes without it |
| The fix | Both apt lines run as `sudo RES_OPTIONS='timeout:5 attempts:2' apt-get ...`: glibc's resolver waits at most 5 s for an answer over UDP and asks twice, so no query waits more than 10 s, whatever the resolver behind it does. `sudo` passes the variable, since the runner's rule is `ALL`, which implies `SETENV`. apt itself is never killed, so the other mirror's index is kept, and the install still fails closed when neither mirror gave one | The exact two-line block, under each fault below: at most 80 s of the step's 180 |
| What it costs | A name the runner's resolver takes more than 10 s to answer fails, where it might have resolved later. The mirrors resolve in milliseconds when their DNS is well; a resolver that slow for both at once fails the install, closed, as two mirrors down does (decision 0197) | Named, as the residual of the bound |
| What still fails | Both mirrors unreachable at once, as decision 0197 has it. A stall longer than a lookup's 10 s now costs about 20 s for each of Azure's three index files, and one stalled lookup of the install's own, about 80 s in all; a mirror that answers each request just inside its 10 s connection bound is not bounded by this. An address lookup is asked as it is and then with each of the runner's search domains, each query its own 10 s, so a resolver that stalls every name, and not ubuntu.com's alone, costs about 20 s a lookup; it stalls kernel.org's names too, and the install fails closed. glibc's fallback to TCP, after an answer that comes truncated, waits with no bound of its own; the runner's resolver is systemd-resolved on 127.0.0.53, which truncates only an answer it holds, so a stalled name never reaches TCP, and the step's three minutes end any other case, closed. These two are reasoned from glibc's resolver, not trialled | Decision 0197's residual, the stall taken out of it; the Claude review and Astra, on the pull request |
| How it is held | `tests/test_tools.py::test_the_cli_install_reads_only_signed_sources_over_https_by_its_own_list` holds both apt lines word for word, `RES_OPTIONS=timeout:5 attempts:2` among their words; the template of the Run's jobs holds the same block | Decision 0197's allow-list, with the lookup bound in it |

## Why

The issue proposed bounding the update by `timeout 60`, so that a stalled lookup could not spend the step before the other mirror was tried. The trials found the other mirror is tried at once, in parallel, and that what spends the step is the stalled mirror's lookups after it; and that the update cannot be cut short without losing what the other mirror gave. Bounding each lookup instead keeps apt whole and costs the stalled mirror seconds.

The trials, by a pull request to the canary repo, a workflow on `ubuntu-24.04` (decision 0197's): a local DNS server on the runner, which glibc was pointed at with the stall's own `timeout` and `attempts`, never answered an ubuntu.com name over UDP or TCP and forwarded every other, each on its own socket; kernel.org's mirror and the runner's own name were given by the hosts file. The first runs made faults of their own, named so their numbers are not read as the fix's:

| Run | What it showed |
|---|---|
| 43343655253 | Unbounded at 60 s a lookup: the update 6 min. The bounded job ran on a runner whose own name did not resolve, so `sudo` stalled before `timeout` began; not read |
| 43345120043 | A server that answered nothing at all cut the runner off from GitHub; every stalled job cancelled at 20 min; not read |
| 43347690275 | `timeout 60`, and `timeout -k 10 60`: each killed the update at exactly 60 s, and the install answered "Unable to locate package bubblewrap". kernel.org's index had not begun by then, behind a lookup of the server's own (below) |
| 43348905046 | The server's log: each fetch asks `_https._tcp.<host>` first; kernel.org's went unanswered through a server that forwarded on one socket, a fault of the trial, which the next run's server mended |
| 43350645508 | Unbounded at 60 s a lookup: the update 6 min 5 s, kernel.org's index whole within it, the install from kernel.org. Bounded at 90 s: kernel.org's `noble-updates` and `noble-security` read whole by +21 s, the update killed at 90 s, and the install "Unable to locate package bubblewrap". Bounded at 60 s: killed with nothing read |
| 43351895815 | At 20 s a lookup: unbounded, the step 131 s, passing; bounded at 60 s, killed, failing. `RES_OPTIONS` on the update alone: 133 s at 60 s a lookup, 89 s at 20 s, 7 s with no fault |

The exact two-line block, in run 43352443840:

| Case | The step | Installed from |
|---|---|---|
| ubuntu.com stalled 60 s a lookup | 80 s | kernel.org's |
| ubuntu.com stalled 20 s a lookup | 80 s | kernel.org's |
| Both mirrors up, kernel.org's connections timing out on their own that minute | 20 s | Azure's |
| kernel.org's connections refused | 14 s | Azure's |

## Boundaries

| Boundary | Check |
|---|---|
| Both apt lines bound each lookup at two tries of 5 s, in the block and in the template of the Run's jobs; neither line is killed at a bound | `tests/test_tools.py::test_the_cli_install_reads_only_signed_sources_over_https_by_its_own_list`, `tests/test_evals.py::test_the_eval_workflow_names_each_credential_in_one_step_alone`, `tools/check_workflows.py`, mutant: "RES_OPTIONS is dropped from the update", mutant: "RES_OPTIONS is dropped from the install", mutant: "a lookup waits as long as it is let", mutant: "the update is killed at a bound", mutant: "RES_OPTIONS is dropped from the Run's jobs' update", mutant: "RES_OPTIONS is dropped from the Run's jobs' install" |
