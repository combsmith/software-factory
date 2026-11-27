# 1311. A job's settings on the base's protected list pass the push grant

Status: accepted. 2026-11-27, the Solution Architect; issue 1177. Narrows decision 0239's first Decision row and its first Boundary row: a settings file on the base's protected list is not one a Factory patch may change.

## Decision

Decision 0239 refuses `push_commits` where a job that holds a secret takes its configuration from a file a Factory patch may change. A file on the base's protected list is not one: a Role's push that touches it is refused (decision 0188). So a job passes the clause where every file it takes its settings from, its own workflow among them, is on that list. Today `sonar-project.properties` is on it, so this repo's scan passes.

`guards/workflows.py` holds the clause. It fails closed: a key, an action at its pin, an input or an `env:` name its table does not name is refused. So is every route that points the scan at another settings file: the scan's `args` and `projectBaseDir`, the scanner's variables, a checkout of another commit or folder, and a line's end YAML reads where the guard reads none.

The rest of 0239's first row is unchanged, and still waits on the settings port: which jobs hold a secret, what runs a file a patch may change, and what the read cannot see.

Limits: every job read is taken to hold a secret, so a job with no secret is refused with one that has. The runner is taken to be GitHub's own. What a listed file says is a person's: a properties file that names modules points the scanner at files this does not hold.

## Why

0239 refused this repo for a file its list already protects, while a later line said the list was enough. A file on the base's list is a person's to change, as decision 0225 already holds for the scan. From this repo's head the scan cannot be pointed elsewhere: its workflow is protected and held by a hash, and the pinned action reads only its inputs and variables the guard refuses.

## Boundaries

| Boundary | Check |
|---|---|
| A job's settings file and its workflow on the base's list pass; either off it is refused | `tests/test_guards.py::Settings.test_a_jobs_settings_on_the_bases_list_pass_and_off_it_are_refused`, `guards/workflows.py`, mutant: "a job's settings off the base's list pass" |
| What the table does not name is refused, never passed | `tests/test_guards.py::Settings.test_what_the_table_does_not_name_is_refused`, `guards/workflows.py`, mutant: "a step may run a command" |
| Every route that points the scan at another settings file is refused | `tests/test_guards.py::Settings.test_every_route_that_points_the_scan_at_another_settings_file_is_refused`, `guards/workflows.py`, mutant: "the scan may be given its base" |
| The list the guard is handed is the base's, never the head's | waiting on `adapters/settings.py` |
