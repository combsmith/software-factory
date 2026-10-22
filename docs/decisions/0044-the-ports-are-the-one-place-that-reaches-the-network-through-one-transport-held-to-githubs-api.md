# 0044. The ports are the one place that reaches the network, through one transport held to GitHub's API

Status: accepted. Taken as a working ruling on 2026-10-21 for "Facts port: one snapshot of a pull request from GitHub, with its completeness flags" (issue 191), which the Maintainer may overturn in review. It adds to `docs/decisions/0001-one-repo-and-a-kernel-that-does-no-io.md`, whose I/O it places, and to the standard "Nothing is fetched" in `docs/standards/security-boundaries.md`, to which it is the second exception.

## Decision

| What | Decided | Because |
|---|---|---|
| Where the network is reached | Only `adapters/github.py` imports what reaches it. Everywhere else `tools/check_repo.py` refuses an import of `urllib.request`, `http`, `socket`, `ssl` and the like by name, with an alias or from its package; `urllib.parse`, which reaches nothing, stays allowed. It is a net, as the search for secrets is: a module reached by another name, through importlib or by a subprocess passes it, and review is the guard | One file that touches GitHub can be read whole in review. Before this, `urllib.request` passed the check as `urllib`, though the standard said it was refused |
| What the transport sends | HTTPS to `api.github.com` alone, by a path from the API's root, with no redirect followed and no proxy, a timeout on each socket operation and a bound on every answer. Its token is given by its caller and never read from the environment; it keeps no body but the answer it returns, and a body that is not JSON is decoded without loss, so a hash is over the bytes GitHub sent | The port is a trust boundary: a request that could go anywhere, or a token it found for itself, would be a credential and a destination no review chose |
| How a port is tested | By replaying a trial's fixture: each recorded request is answered once, in the order recorded, matched by method, path, Accept and the whole body, a GraphQL query's variables among it, and any other is refused. The required check holds no token, and fetches nothing | A stub that answers anything was the proof of concept's failure (L-51); a fixture is what GitHub said |
| How a directory is built in parts | Its `AGENTS.md` names the files not built yet, in one line of plain words. A rule may wait on one of those files, and the wait holds until the file exists; a wait on any other file in a built directory has arrived, as a forgotten wait would (`tools/check_context.py`) | The first file in `adapters/` would otherwise fail every one of the 58 rows waiting on `adapters/` at once, and no port story could land alone or say which rows it holds |
| The facts port's first part | `adapters/pull.py` reads, through the transport, a pull request's own fields, its last pusher, its diff with its content id and its changed paths, each with whether the read was whole, and the title beside them. The rest of `facts/1` comes in the parts named in `adapters/AGENTS.md` | Reviews, threads, checks and acceptance rest on trials not yet run (P-41, P-42, P-43), and one review cannot read the whole snapshot at once |

## Why

The Kernel does no I/O (decision 0001), so every read and write the Factory makes is a port's, and slice 1 needs the first. A port reaches GitHub, which the standard "Nothing is fetched" refused for the whole repo; that rule was meant for the required check, which still fetches nothing. Placing the exception in one file, held by a check, keeps the rule's purpose and makes the boundary reviewable. Building the ports in parts needs a wait narrower than a directory, and naming the parts in the directory's own rules keeps every wait visible where the next author reads.

## Boundaries

| Boundary | Check |
|---|---|
| Only `adapters/github.py` imports what reaches the network, by name, with an alias or from its package | `tests/test_tools.py::test_only_the_transport_reaches_the_network` |
| The transport sends to GitHub's API alone, follows no redirect, takes no proxy and takes its token from its caller | `tests/test_adapters.py::test_a_request_stays_on_githubs_api`, `tests/test_adapters.py::test_the_live_transport_takes_its_token_from_its_caller_and_follows_no_redirect` |
| A replay answers each recorded request once, in order and with its whole body, and refuses any other | `tests/test_adapters.py::test_a_replay_answers_only_what_the_fixture_holds_and_each_once` |
| A wait on a file a built directory plans holds until the file exists; any other file there has arrived | `tests/test_tools.py::test_a_wait_on_a_file_a_built_directory_plans_holds_until_the_file_exists` |
| A pull request's class is the account the caller names, by its id and type, a Bot for an App and a User for the Maintainer, and anyone else, a fork among them, is `outside` | `tests/test_adapters.py::test_the_class_is_the_account_named_or_outside` |
| One exception, the Maintainer's ruling on "Design: the CLI's sandbox limits connections but passes the parent's environment through (P-26 failed); the run job relies on the scrub and --tools """ (issue 287): `tools/trial_p50_stub.py`, P-50's stub of the model's API, held by an allowlist. It imports `http.server`, `json`, `os` and `sys` by their own names and names nothing else of them; it makes its server one way, on `127.0.0.1` written as it is; it touches no socket and calls nothing that reaches round a name; and no workflow of this repo names it. A trial runs it only in the canary's workflow; this repo's tests reach it on `127.0.0.1` through a child process | `tests/test_tools.py::test_the_p50_stub_alone_may_serve_and_only_on_loopback` |
