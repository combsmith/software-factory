#!/bin/sh
# Compare the Factory repo's live rulesets with config/rulesets.json (issues 62 and 95). Run by hand, never in CI.
# It reads through whoever is logged in to gh, and mints nothing. Each answer is written outside the repo, redacted
# by tools/redact_trial.py, and the raw answer deleted, before tools/rulesets_drift.py reads what is left on stdin.
set -eu
root=$(cd "$(dirname "$0")/.." && pwd -P)
dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT
trap 'exit 1' HUP INT TERM
# Each path resolved, links and all, so a TMPDIR that leads into the repo another way is refused too.
real=$(cd "$dir" && pwd -P)
case "$real/" in "$root"/*) echo "the scratch directory $real is inside the repo; set TMPDIR elsewhere" >&2; exit 2;; esac
repo=$(cd "$root" && python3 -c 'import json; print(json.load(open("config/rulesets.json"))["repo"])')
read_one() {
  gh api --include "$2" > "$dir/raw" 2>/dev/null || true
  (cd "$root" && python3 -m tools.redact_trial < "$dir/raw" > "$dir/$1") 2> /dev/null ||
      { echo "rulesets_drift: the redaction of $1 failed" >&2; exit 1; }
  rm -f "$dir/raw"
}
read_one list "repos/$repo/rulesets?per_page=100"   # rulesets_drift.py: PAGE
ids=$(python3 -I "$root/tools/rulesets_drift.py" --ids < "$dir/list")
for id in $ids; do
  read_one "ruleset-$id" "repos/$repo/rulesets/$id"
done
{ cat "$dir/list"; printf '\0'; for id in $ids; do cat "$dir/ruleset-$id"; printf '\0'; done; } |
  python3 -I "$root/tools/rulesets_drift.py"
