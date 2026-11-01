# 0112. The release App is in the data, and alone holds `workflows`

Status: accepted. PR 3 of "Release: cut an immutable tag, move next, and roll back in one action" (issue 197), under its ruling 4′ as amended, the orchestrator's brief of 2026-10-31 and the Maintainer's ruling of 2026-10-30 that a protected file's pull request needs no separate sign-off, only the four reads. It changes the rows of decisions 0071 and 0076 that say the release App's needs wait on its registration, and decision 0101's line that the key's row names its environment since config/apps.json has no release App: that row's environment is now null, as every App's is.

## Decision

| What | Decided | Because |
|---|---|---|
| The App | `combsmith-sf-release`, App 5502359, on `combsmith/software-factory` alone, its key in `factory-release` as `RELEASE_APP_KEY` | As the Maintainer registered it. The release job holds its key, so `check_apps` names that job's environment for it, as it does for the queue App's |
| Its needs | `write:release_tag` and `write:move_channel` under `contents: write`; `write:deployment` under `deployments: write`; `read:release.runs` under `actions: read`; `read:release.checks` under `checks: read`. Each stops waiting. `read:release.refs` it reads too, and the reader still does | Ruling 4′'s grants and `checks: read` (decision 0076) |
| Two new needs | `write:workflow_commit_tag`, under `workflows: write`; and `read:release.repo`, under `metadata: read` | A permission serves a named need, and GitHub grants `metadata: read` with any other; neither was yet named |
| `workflows` | The one exception to `NEVER`, for this App by name (`EXCEPT`). Any other App that holds it is refused, at any level, and this App holding `security_events` is refused as any App is | A tag on a commit that touches `.github/workflows/` needs it (ruling 4′), and every Release is such a commit in time |
| What this opens | The App can push to `.github/workflows/`, where GitHub otherwise refuses an App. What holds that is where its key is: `.github/workflows/release.yml`, the one workflow that names it, whose every line `release_problems` holds; and `factory-release`, whose deployment branches are `main`'s alone. That setting is held by nothing in this repo. It was read live on 2026-10-31: `main` alone, and admins cannot bypass it. A fixture would say only what it was that day, so noticing a change needs a live read, "Each factory environment's deployment branches are read at run time" | Stated plainly, since the design's line on `.github/` said no Factory App holds it, and that line changes here |
| A Role | No manifest may name this App, as none may name the Controller's or the reader's | It writes tags and no item. The ceiling already refused it any Effect, and one more edit would have opened that |
| The read | `trials/P-39.release.json`: its registration through the Maintainer's login, and its reach at his terminal, with a token narrowed to `metadata: read` and revoked (204). It has no events, `selected`, and this repo alone. The installation's grants stay in `trials/P-39.grants.json` | P-39's other fixtures keep the time they ran at. `tools/trial_p39_reach.sh` now takes the Apps it is given, each with its own key |
| Not done | The cut itself, which waits for the eval to pass. P-30's fixture and the tag ruleset naming this App are those of "Trial P-30: one identity cuts a Release and moves a channel tag under the tag ruleset" (issue 189) | Nothing can cut until then, whatever the data says |

## Why

Its needs had waited on this registration since the release step was built. With the App read and held to the data as the
other four are, the first cut waits on nothing of this file.

## Boundaries

| Boundary | Check |
|---|---|
| Only this App holds `workflows`, and it holds `security_events` as little as any; its key is held to the release job's environment | `tests/test_tools.py::test_only_the_release_app_holds_workflows_and_it_holds_security_events_as_little_as_any` |
| Any App holding `workflows` or `security_events` otherwise is refused | `tests/test_tools.py::test_no_app_may_change_a_workflow_or_upload_to_code_scanning` |
| Each of its needs is its own, and no other App's | `tests/test_release.py::test_each_of_the_release_apps_needs_is_its_own` |
| A Role's manifest may not name it | `tests/test_tools.py::test_a_role_writes_through_no_app_that_is_no_roles` |
| What GitHub registered, installed and reached for it agrees with the data | `tests/test_tools.py::test_the_data_is_held_to_what_github_granted_each_app` |
| The reach script reads the Apps it is named, and refuses before anything is minted | `tests/test_tools.py::test_only_the_apps_named_are_read_and_each_refusal_comes_before_anything_is_minted` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
