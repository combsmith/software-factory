# 0197. Bubblewrap is fetched from two mirrors of different operators, so one unreachable mirror fails no Run

Status: accepted. The Factory Builder's rulings of 2026-11-12 on "The CLI's install fetches bubblewrap from more than one mirror, so one unreachable mirror does not fail a Run" (issue 774). It amends decision 0195's rows "The fix" and "What it holds and what it does not", where they name one mirror; the rest of each row stands.

## Decision

| What | Decided | Because |
|---|---|---|
| The fault | From 01:47Z on 2026-11-12 runners intermittently could not connect to `mirrors.edge.kernel.org`, over IPv6 ("Network is unreachable") and IPv4 ("Could not wait for server fd"), and apt then answered "Unable to locate package bubblewrap". Two of a pull request's review Runs failed so (sf-run 43136883440 among them), and so did the eval dispatches of a Release's cut (43140773688 and 43140955538) | One mirror is one point of failure for every Run and every eval |
| The fix | `CLI_INSTALL_RUN` writes the source list in one line, `printf '%s\n'` and six sources, `>` to /tmp/ubuntu.list on the runner: `noble`, `noble-updates` and `noble-security`, `main` alone, from each of two mirrors of different operators, `https://azure.archive.ubuntu.com/ubuntu`, the runner image's own, and `https://mirrors.edge.kernel.org/ubuntu`, each `[signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg]`. Both apt lines read that list alone, with their options of decision 0195 unchanged | A trial workflow in the canary repo, run 43141154752, ran the block four ways on `ubuntu-24.04`: both mirrors up, installed in 7 s; kernel.org refused, 18 s, and kernel.org's connections dropped into a black hole, 28 s, each installed from Azure's; Azure's refused, 37 s, installed from kernel.org's. apt warned of the mirror it could not reach, took the package from the other, and the step held its three minutes |
| Why two operators | The two fail apart: Azure's mirror is Microsoft's, beside the runners, and kernel.org's is the Linux Foundation's. Two mirrors of one operator would share its network, its DNS and its outages, as the ubuntu.com names did on 2026-11-11 (decision 0195) | The faults seen so far were each of one operator |
| What still fails | Both mirrors unreachable at once fails the install, closed, and stops every Run and eval, as decision 0106's "Its limits" has it. A name that never resolves still stalls apt past its timeout, as on 2026-11-11, and with two sources the step's three minutes bound the sum: the trial's black hole cost 21 s more than both up | Named, as the residual of two dependencies outside the repo |
| How it is held | `tests/test_tools.py::test_the_cli_install_reads_only_signed_sources_over_https_by_its_own_list` holds the block to eight lines: the CLI's own install word for word, one line writing exactly the six sources, each mirror named literally, and the two apt lines with exactly their options. The template of the Run's jobs holds the same block, its `%` written `%%` for its own rendering | Decision 0195's allow-list, carried to two mirrors; cubic's two points on its fix, the mirror named literally and the list started, not added to, are held by the one line |

## Why

Decision 0195 moved the fetch off a mirror whose names stopped resolving, onto one mirror that later stopped connecting. Each fault was one operator's. Reading both, apt takes the package from whichever answers, and only both down at once stops a Run.

The trial, a workflow in the canary repo, run 43141154752, each case a job of its own on `ubuntu-24.04`:

| Case | The step | Installed from |
|---|---|---|
| Both mirrors up | 7 s | Azure's |
| kernel.org's connections refused | 18 s | Azure's |
| kernel.org's connections dropped into a black hole | 28 s | Azure's |
| Azure's connections refused | 37 s | kernel.org's |

## Boundaries

| Boundary | Check |
|---|---|
| One line writes six signed HTTPS sources of two operators' mirrors, the list started, not added to; either mirror missing, unsigned, in clear text, renamed or joined by another source is refused | `tests/test_tools.py::test_the_cli_install_reads_only_signed_sources_over_https_by_its_own_list`, `tools/check_workflows.py`, mutant: "noble-updates is held by no keyring", mutant: "noble-security is held by no keyring", mutant: "noble main is read in clear text", mutant: "the sources name another mirror", mutant: "one operator's mirror is left out", mutant: "the list is added to, not started", mutant: "a source is added outside the block's own form" |
