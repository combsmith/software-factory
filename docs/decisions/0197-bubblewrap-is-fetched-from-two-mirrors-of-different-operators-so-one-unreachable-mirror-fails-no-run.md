# 0197. Bubblewrap is fetched from two mirrors of different operators, so one unreachable mirror fails no Run

Status: accepted. The Factory Builder's rulings of 2026-11-12 on "The CLI's install fetches bubblewrap from more than one mirror, so one unreachable mirror does not fail a Run" (issue 774). It amends decision 0195's rows "The fix", "The exception to 'nothing is installed'", "What it holds and what it does not" and "How it is held", where they name one mirror or one retry setting, and its choice of a mirror outside ubuntu.com, for one of the two; the rest of each row stands.

## Decision

| What | Decided | Because |
|---|---|---|
| The fault | From 01:47Z on 2026-11-12 runners intermittently could not connect to `mirrors.edge.kernel.org` over IPv4, the connection timing out ("Could not wait for server fd" once), and apt then answered "Unable to locate package bubblewrap". The runners have no IPv6, so its "Network is unreachable" is no part of the fault. Two of a pull request's review Runs failed so (sf-run 43136883440 and 43137291487), and so did a Release's eval dispatches (43140773688 and 43140955538) | One mirror is one point of failure for every Run and every eval |
| The fix | `CLI_INSTALL_RUN` writes the source list in one line, `printf '%s\n'` and six sources, `>` to /tmp/ubuntu.list on the runner: `noble`, `noble-updates` and `noble-security`, `main` alone, from each of two mirrors of different operators, `https://azure.archive.ubuntu.com/ubuntu`, the runner image's own, and `https://mirrors.edge.kernel.org/ubuntu`, each `[signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg]`. Both apt lines read that list alone, as decision 0195 has them. The update tries each mirror once, `Acquire::Retries=0`, since the other mirror is its retry; the install keeps `Acquire::Retries=2`; both bound each connection at 10 s | Trials in the canary repo (below): each mirror made unreachable in turn, apt warned of it, took the package from the other, and the step held its three minutes |
| Why two operators | Azure's mirror is Microsoft's, beside the runners, and kernel.org's is the Linux Foundation's, so their hosts and networks fail apart: the fault of 2026-11-12 was kernel.org's alone. Azure's name is under ubuntu.com, though, whose DNS is Canonical's, so a repeat of 2026-11-11, when no ubuntu.com name resolved (decision 0195), leaves kernel.org's mirror alone, as decision 0195 had it | Each fault seen so far was of one operator: ubuntu.com's names on 2026-11-11, kernel.org's connections on 2026-11-12 |
| What still fails | Both mirrors unreachable at once fails the install, closed, and stops every Run and eval, as decision 0106's "Its limits" has it; one trial job met exactly that, with Azure's names failing and kernel.org's connections down in the same seconds. A name that stalls as on 2026-11-11, about 20 s a lookup, is bounded by no apt timeout: tried once on each of three index files it costs about a minute, inside the step's three, where three tries would cost the three minutes whole; this is reasoned from that day's log, since no trial stalled a lookup so long | Named, as the residual of two dependencies outside the repo |
| How it is held | `tests/test_tools.py::test_the_cli_install_reads_only_signed_sources_over_https_by_its_own_list` holds the block to eight lines: the CLI's own install word for word, one line writing exactly the six sources, each mirror named literally, and the two apt lines with exactly their options. The template of the Run's jobs holds the same block, its `%` written `%%` for its own rendering | Decision 0195's allow-list, carried to two mirrors; cubic's two points on its fix, the mirror named literally and the list started, not added to, are held by the one line |

## Why

Decision 0195 moved the fetch off a mirror whose names stopped resolving, onto one mirror that later stopped connecting. Each fault was one operator's. Reading both, apt takes the package from whichever answers, and only both down at once stops a Run.

The trials, workflows in the canary repo on `ubuntu-24.04`, each fault made by the runner's own hosts file or firewall; the times are of the install step:

| Case | Run | The step | Installed from |
|---|---|---|---|
| Both mirrors up | 43141154752 | 4 s | Azure's |
| kernel.org's connections refused | 43141154752 | 15 s | Azure's |
| kernel.org's connections dropped into a black hole | 43141154752 | 26 s | Azure's |
| Azure's connections refused | 43141154752 | 33 s | kernel.org's |
| ubuntu.com's DNS queries dropped, kernel.org down on its own | 43146217794 | 13 s | Neither: refused, closed |

## Boundaries

| Boundary | Check |
|---|---|
| One line writes six signed HTTPS sources of two operators' mirrors, the list started, not added to; either mirror missing, unsigned, in clear text, renamed or joined by another source is refused; the update tries each mirror once and the install twice more | `tests/test_tools.py::test_the_cli_install_reads_only_signed_sources_over_https_by_its_own_list`, `tools/check_workflows.py`, mutant: "noble-updates is held by no keyring", mutant: "noble-security is held by no keyring", mutant: "noble main is read in clear text", mutant: "the sources name another mirror", mutant: "Azure's mirror is left out", mutant: "one operator's mirror is left out", mutant: "a suite of one mirror is left out", mutant: "the redirection is quoted", mutant: "the list is added to, not started", mutant: "a source is added outside the block's own form", mutant: "the update retries each mirror" |
