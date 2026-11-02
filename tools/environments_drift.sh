#!/bin/sh
# Hold each factory environment to main alone (issue 463). Run by hand, never in CI. It reads through whoever is logged in to gh,
# and mints nothing. Each answer is written outside the repo, redacted by tools/redact_trial.py, and the raw answer deleted,
# before tools/environments_drift.py reads what is left on stdin. It reads no secret, and no list of them.
set -euf     # no globbing: a call holds a ?
root=$(cd "$(dirname "$0")/.." && pwd -P)
dir=$(mktemp -d "${TMPDIR:-/tmp}/environments-drift.XXXXXX")     # bare, macOS ignores TMPDIR
trap 'rm -rf "$dir"' EXIT
trap 'exit 1' HUP INT TERM
# Each path resolved, links and all, so a TMPDIR that leads into the repo another way is refused too.
real=$(cd "$dir" && pwd -P)
case "$real/" in "$root"/*) echo "the scratch directory $real is inside the repo; set TMPDIR elsewhere" >&2; exit 2;; esac
cd "$root"
repo=$(python3 -c 'import json; print(json.load(open("config/rulesets.json"))["repo"])')
read_one() {
  gh api --include "$2" > "$dir/raw-$1" 2>/dev/null || true
  python3 -m tools.redact_trial < "$dir/raw-$1" > "$dir/$1" 2> /dev/null ||
      { echo "environments_drift: the redaction of $1 failed" >&2; exit 1; }
  rm -f "$dir/raw-$1"
}
read_one list "repos/$repo/environments?per_page=100"     # environments_drift.py: PAGE
{ cat "$dir/list"; printf '\0'; } > "$dir/first"
names=$(python3 -m tools.environments_drift --names < "$dir/first")
for name in $names; do
  read_one "env-$name" "repos/$repo/environments/$name/deployment-branch-policies?per_page=100"
done
{ cat "$dir/first"; for name in $names; do cat "$dir/env-$name"; printf '\0'; done; } |
  python3 -m tools.environments_drift
