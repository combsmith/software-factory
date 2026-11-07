# 0151. The artifact storage is any productionresults account numbered in one to three digits

Status: accepted. Replaces `docs/decisions/0147-the-engine-runs-the-pinned-model-by-its-full-id-at-the-tiers-effort-and-keeps-an-answer-only-from-that-model.md`, the one record in force of those that hold decision 0045's rows: 0138 kept them, and 0147 kept 0138. Of them it overturns one clause, the accounts 0045's row "The one redirect followed" names, and restates that row below. Nothing else in 0147, or in what it kept of 0138, 0045 and 0050, changes. The Maintainer's ruling of 2026-11-06, restated to this lane by the Factory Builder, after the cut of the first Release was refused: allow `productionresultssa` followed by one to three digits, and keep everything else in that row as it is.

## Decision

| What | Decided | Because |
|---|---|---|
| The one redirect followed | An artifact's download alone, `download(path)` of `/repos/{owner}/{repo}/actions/artifacts/{id}/zip`, is followed, once, to GitHub's artifact storage alone: `productionresultssa` and a number of one to three digits, written without a leading zero, `.blob.core.windows.net`, over HTTPS on its own port. No token and no header of the API's is sent there, no further redirect is followed, and its body is bounded at 64 KiB. Every other redirect is refused, by the replay as by the live transport | A Run's outcome is in its artifact, which GitHub serves only by a redirect off its API; without it no failed Run could be read, and every list holding one would defer for ever |
| The accounts | `productionresultssa0` to `productionresultssa999`, in the letters and ASCII digits GitHub gives, and no other name, number or host. A number with a leading zero, as sa07 or sa032, is refused: that is narrower than the ruling's one to three digits, and GitHub's names have none | GitHub served an artifact from `productionresultssa32`, past the twenty accounts it once named, and its list of the hosts a runner must reach now gives only `*.blob.core.windows.net`, with no numbers. A pattern of that list would let any Azure account answer; the accounts GitHub has used are one name and a number |

## Why

Decision 0045 named sa0 to sa19, the accounts GitHub then listed. On 2026-11-06 the eval run at the main commit that holds decision 0150 passed, but the cut of the first Release was refused with `eval_gate_closed` and wrote nothing: the eval report's download redirected to `productionresultssa32`, the transport refused it as off the storage, and the report was read as unanswered, so the gate was shut by a read, not by the eval. Every artifact the ports read goes by the same redirect, a Run's outcome, a Lens's `applied/1`, the pass records and the eval report, so each had the same latent failure whenever GitHub served it from an account past sa19. Three digits leave room for GitHub's growth without opening the name. That every such account is GitHub's is assumed, not known: only sa0 to sa19 and sa32 have been seen as GitHub's, and an Azure account name goes to whoever takes it first. The ruling accepts that, since the transport follows the redirect only when GitHub's own API sends it there, and sends no token or header of the API's; the rest of 0045, its path rule and its bounds, is unchanged.

## Boundaries

| Boundary | Check |
|---|---|
| The storage is `productionresultssa` and one to three ASCII digits with no leading zero, under `blob.core.windows.net`: sa32 and sa199 are; sa1000, a leading zero, a letter or other character in the number, another account name and another host are not | `tests/test_adapters.py::test_the_storage_is_any_productionresults_account_numbered_in_one_to_three_digits` |
| Everything else in 0045's row stands: the one redirect, from an artifact's download alone, over HTTPS on its own port, under `/actions-results/`, with no token or header sent and no further redirect | `tests/test_adapters.py::test_only_an_artifacts_download_follows_its_redirect_and_only_to_githubs_storage`, `tests/test_adapters.py::test_the_live_transport_sends_no_token_to_the_storage_and_bounds_what_it_holds` |
| A fourth digit, a stop at sa99 or at sa19, a leading zero, a letter after the number and any account name each have a mutant that a test kills | `tools/mutants.py` |
| The storage host is the one GitHub serves an artifact from | not held yet: `tests/test_adapters.py::test_an_artifact_download_a_trial_recorded_is_read_as_the_port_reads_it` waits for a trial that records one |
