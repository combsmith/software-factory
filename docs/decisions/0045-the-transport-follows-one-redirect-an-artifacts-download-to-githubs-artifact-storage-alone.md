# 0045. The transport follows one redirect: an artifact's download, to GitHub's artifact storage alone

Status: accepted. The Maintainer's ruling of 2026-10-21 on "Records port: the Factory's own run records, unidentified Runs and the cache" (issue 192), built in `adapters/artifacts.py`. It adds to `docs/decisions/0044-the-ports-are-the-one-place-that-reaches-the-network-through-one-transport-held-to-githubs-api.md`, whose transport follows no redirect, the one exception, and to the standard "Nothing is fetched" in `docs/standards/security-boundaries.md`.

## Decision

| What | Decided | Because |
|---|---|---|
| The one redirect followed | An artifact's download alone, `download(path)` of `/repos/{owner}/{repo}/actions/artifacts/{id}/zip`, is followed, once, to GitHub's artifact storage alone: `productionresultssa0` to `productionresultssa19.blob.core.windows.net`, the accounts GitHub names among the hosts a runner must reach, over HTTPS on its own port. No token and no header of the API's is sent there, no further redirect is followed, and its body is bounded at 64 KiB. Every other redirect is refused, by the replay as by the live transport | A Run's outcome is in its artifact, which GitHub serves only by a redirect off its API; without it no failed Run could be read, and every list holding one would defer for ever |
| The storage's address | It carries a signature: no error the transport raises holds it, or is chained to one that does, and only the transport names the storage (`tools/check_repo.py`) | A signed address is a credential for as long as it lasts |
| What is read from the artifact | The one artifact named `outcome`, a zip of one file, outcome.json, bounded by the size listed, the bytes downloaded, the file's size in the zip and the bytes read out of it, its digest checked where the listing gives one, and read only stored or deflated. The file is held to `outcome/1` and must name the Run whose artifact it is | Python bounds the output of those two methods as it reads, and of no other: a zip of a few hundred bytes in bzip2 grows by hundreds of megabytes |
| An outcome that is not there | A Run that left none, and one whose artifact is past its retention, read whole with none; an outcome GitHub lists but that cannot be read leaves the list not whole | The run list is never bounded by date: an expired outcome read as short would leave every pass short once any failed Run was older than the retention |

## Why

The records port reads a failed Run's outcome (decisions 0029 and 0039), and GitHub serves an artifact only by a redirect to its storage, which 0044's transport refused. Allowing exactly one, by endpoint and by host, keeps the boundary one review can read. The host is Azure's, the store GitHub's v4 artifacts are kept in, not a name under github.com; no trial has recorded a download yet, and the first that does is read by a test waiting for it.

## Boundaries

| Boundary | Check |
|---|---|
| Only an artifact's download follows its redirect, and only to GitHub's artifact storage over HTTPS | `tests/test_adapters.py::test_only_an_artifacts_download_follows_its_redirect_and_only_to_githubs_storage` |
| The storage address is under `/actions-results/`, with no segment that climbs out of it, plain or percent-encoded (the Maintainer's answer of 2026-10-21 on "Records port: the Factory's own run records, unidentified Runs and the cache", issue 192) | `tests/test_adapters.py::test_only_an_artifacts_download_follows_its_redirect_and_only_to_githubs_storage` |
| No token is sent to the storage, what it answers is bounded, and no error holds its address | `tests/test_adapters.py::test_the_live_transport_sends_no_token_to_the_storage_and_bounds_what_it_holds` |
| No code but the transport names the storage | `tests/test_tools.py::test_only_the_transport_names_githubs_artifact_storage` |
| An outcome is read from its one file, bounded, stored or deflated, and held to `outcome/1` and its Run | `tests/test_adapters.py::test_an_outcome_that_cannot_be_read_whole_is_not_whole`, `tests/test_adapters.py::test_an_outcome_is_held_in_the_bounds_before_it_is_read_out` |
| A pass record alone is downloaded under 1 MiB zipped and read out to 8 MiB; every other artifact under 64 KiB (`docs/decisions/0060-the-pass-entry-reads-through-the-ports-with-a-token-of-reads-and-the-last-two-pass-records.md`) | `tests/test_adapters.py::test_a_pass_record_alone_is_downloaded_under_a_wider_bound` |
| The storage host is the one GitHub serves an artifact from | not held yet: `tests/test_adapters.py::test_an_artifact_download_a_trial_recorded_is_read_as_the_port_reads_it` waits for a trial that records one |
