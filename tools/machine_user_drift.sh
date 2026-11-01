#!/bin/sh
# Compare the machine user's live role with config/machine-user.json (issue 89). Run by hand, never in CI. It reads through
# whoever is logged in to gh, and mints nothing. Each answer is written outside the repo, redacted by tools/redact_trial.py,
# and the raw answer deleted, before tools/machine_user_drift.py reads what is left on stdin.
set -eu
root=$(cd "$(dirname "$0")/.." && pwd -P)
dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT
trap 'exit 1' HUP INT TERM
# Each path resolved, links and all, so a TMPDIR that leads into the repo another way is refused too.
real=$(cd "$dir" && pwd -P)
case "$real/" in "$root"/*) echo "the scratch directory $real is inside the repo; set TMPDIR elsewhere" >&2; exit 2;; esac
: > "$dir/answers"
for call in $(cd "$root" && python3 -m tools.machine_user_drift --reads); do
  gh api --include "$call" > "$dir/raw" 2>/dev/null || true
  (cd "$root" && python3 -m tools.redact_trial < "$dir/raw" >> "$dir/answers") 2> /dev/null ||
      { echo "machine_user_drift: the redaction of $call failed" >&2; exit 1; }
  rm -f "$dir/raw"
  printf '\0' >> "$dir/answers"
done
cd "$root" && python3 -m tools.machine_user_drift < "$dir/answers"
