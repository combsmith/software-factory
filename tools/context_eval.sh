#!/usr/bin/env bash
# The context's test (issue 8): a fresh agent, given one export of this repo and one sentence, adds a rule to the
# Kernel; the held-out answer, `make verify` and the mutation check judge what it left; the run is recorded with
# no text of the model's in it.
#
#   bash tools/context_eval.sh OUT CONFIG_DIR REPO COMMIT SENTENCE HELD_OUT [CLI]
#
# OUT is a directory that does not exist yet, outside every repo. CONFIG_DIR is the configuration directory the
# Factory alone uses, logged in to the CLI at the Maintainer's own terminal on his own subscription (decision 0033);
# this script logs nothing in and mints nothing, and starts the CLI with an empty environment but for the few names
# in run_cli, so no key or token of this shell reaches it. REPO is a checkout of software-factory and COMMIT a commit
# in it: `git archive` of that commit is the agent's whole world, with no history, no remote and no other checkout.
# SENTENCE is a file holding the task's one sentence, outside REPO, which names the rule and its reason code and
# nothing of how. HELD_OUT is the boundary test for that rule, outside REPO and OUT, copied from the private home by
# the Maintainer: it is copied into the export only after the agent has stopped, run, and taken out again before
# anything is recorded, and this script never prints it. CLI, if given, is the CLI's program; by default the build
# the native installer kept for PIN, else `claude` on PATH. Whichever it is, it must say it is version PIN.
#
# In order, each in scratch directories outside every repo:
#   1. the CLI's version, which must be PIN;
#   2. the export, twice: one copy the agent works in, one kept as made, so that what it changed can be counted;
#   3. the agent: the CLI headless, the sentence as its whole prompt, its file and shell tools allowed inside the
#      export, its network tools refused, CAP turns at most; its transcript is captured and never printed;
#   4. the judge: the held-out test copied in and run; `make verify`; the mutation check on the mutants the agent
#      added, by the paths they target; the held-out test taken out;
#   5. the record: tools/context_eval.py reads the transcript for the paths read, the first words of each command
#      and the result's counts, counts the changes by file, and writes OUT/record.json, a context-eval/1 run.
# OUT receives record.json, checked.json (each step's exit and counts), ran_at and requests.json (what was asked,
# without the sentence's answer or the transcript). The scratch directories are deleted, the transcript with them.
set -euo pipefail
set +x
export LC_ALL=C

# The version the engine port is pinned to, as trial P-13 recorded it (tools/trial_p13_cli.sh).
PIN=2.1.302
# The most turns the agent may take. The record keeps it beside what the run cost.
CAP=80
# What the agent may use: its file and shell tools, inside the export; never the network, and never another agent.
ALLOWED="Read,Edit,Write,MultiEdit,Glob,Grep,Bash"
REFUSED="WebFetch,WebSearch,Task,Agent"
OPTIONS="--output-format stream-json --verbose --permission-mode acceptEdits --no-session-persistence --strict-mcp-config --disable-slash-commands"

usage() {
    echo "usage: bash tools/context_eval.sh OUT CONFIG_DIR REPO COMMIT SENTENCE HELD_OUT [CLI]" >&2
    exit 2
}
refuse() {
    echo "context_eval: $*" >&2
    exit 2
}
[ "$#" -eq 6 ] || [ "$#" -eq 7 ] || usage
command -v python3 >/dev/null || refuse "python3 is needed"
command -v git >/dev/null || refuse "git is needed"
command -v tar >/dev/null || refuse "tar is needed"

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
[ -f "$root/tools/context_eval.py" ] && [ -f "$root/tools/jsonschema_lite.py" ] ||
    refuse "run the copy of this script in a checkout of software-factory"

# OUT: new, and outside the repo, read as the file system resolves it.
case "$1" in "") usage ;; esac
parent=$(cd "$(dirname "$1")" 2>/dev/null && pwd -P) || refuse "the directory that would hold OUT does not exist"
out="$parent/$(basename "$1")"
[ ! -e "$out" ] && [ ! -L "$out" ] || refuse "$out exists; name a new directory"
case "$out/" in "$root"/*) refuse "OUT is inside the repo; name a directory outside it" ;; esac

# CONFIG_DIR: the Factory's own, never the Maintainer's, and never inside the repo or OUT.
[ -d "$2" ] || refuse "CONFIG_DIR is not a directory; log the CLI in to it first"
cfg=$(cd "$2" && pwd -P)
home=$(cd "$HOME" && pwd -P)
case "$cfg" in "$home" | /) refuse "CONFIG_DIR is the home directory or holds it, not one the Factory alone uses" ;; esac
case "$home/" in "$cfg"/*) refuse "CONFIG_DIR is the home directory or holds it, not one the Factory alone uses" ;; esac
lower=$(printf '%s' "$cfg" | tr '[:upper:]' '[:lower:]')
lower_home=$(printf '%s' "$home" | tr '[:upper:]' '[:lower:]')
case "$lower/" in "$lower_home/.claude/"*) refuse "CONFIG_DIR is under ~/.claude, the default configuration" ;; esac
case "$cfg/" in "$root"/*) refuse "CONFIG_DIR is inside the repo; a login must never be kept there" ;; esac
case "$out/" in "$cfg"/*) refuse "OUT is inside CONFIG_DIR; name a directory apart from it" ;; esac

# REPO and COMMIT: a checkout, and a commit it holds. The export is what the agent sees, so REPO may be this one.
[ -d "$3" ] || refuse "REPO is not a directory"
repo=$(cd "$3" && pwd -P)
git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1 || refuse "REPO is not a git checkout"
commit=$(git -C "$repo" rev-parse --verify --quiet "$4^{commit}") || refuse "COMMIT is not a commit in REPO"
case "$out/" in "$repo"/*) refuse "OUT is inside REPO; name a directory outside it" ;; esac

# SENTENCE and HELD_OUT: files outside REPO, OUT and CONFIG_DIR. The sentence is one line; the test is never read here.
for f in "$5" "$6"; do
    [ -f "$f" ] || refuse "SENTENCE and HELD_OUT must be files"
    full=$(cd "$(dirname "$f")" && pwd -P)/$(basename "$f")
    case "$full" in "$repo"/* | "$root"/* | "$cfg"/*) refuse "SENTENCE and HELD_OUT stay outside the repo and CONFIG_DIR" ;; esac
done
sentence=$(python3 -I -c '
import re, sys
lines = [l for l in open(sys.argv[1]).read().splitlines() if l.strip()]
if len(lines) != 1 or not re.fullmatch(r"[A-Z][^.\n]{10,398}\.", lines[0].strip()):
    sys.exit(1)
print(lines[0].strip())' "$5") || refuse "SENTENCE is not one sentence that names a rule"
# shellcheck disable=SC2016  # the backticks are a regex, not a command
code=$(printf '%s' "$sentence" | python3 -I -c '
import re, sys
found = re.findall(r"`([a-z_]+)`", sys.stdin.read())
print(found[0] if len(found) == 1 else "")')
[ -n "$code" ] || refuse "SENTENCE names no reason code, or more than one, in backticks"
held_out=$(cd "$(dirname "$6")" && pwd -P)/$(basename "$6")
case "$(basename "$held_out")" in test_*.py) ;; *) refuse "HELD_OUT is named test_<something>.py" ;; esac

# The CLI: the one named, else the build kept for PIN if the native installer kept one, else the one on PATH.
if [ "$#" -eq 7 ]; then
    cli=$7
else
    cli="$HOME/.local/share/claude/versions/$PIN"
    [ -x "$cli" ] || cli=$(command -v claude || true)
fi
[ -n "$cli" ] && [ -f "$cli" ] && [ -x "$cli" ] || refuse "no claude CLI found at '$cli'; install version $PIN"
cli=$(cd "$(dirname "$cli")" && pwd -P)/$(basename "$cli")

scratch=$(cd "$(mktemp -d)" && pwd -P)
case "$scratch/" in "$root"/* | "$repo"/* | "$cfg"/*) rm -rf "$scratch"; refuse "the scratch directory is inside the repo or CONFIG_DIR" ;; esac
finish() {
    rm -rf "$scratch"
}
trap finish EXIT
trap 'exit 130' INT TERM
work="$scratch/work"
pristine="$scratch/pristine"
mkdir "$work" "$pristine"

# The CLI, in the export, with no environment from this shell but what is named here.
run_cli() {
    (cd "$work" && env -i HOME="$HOME" USER="${USER:-}" LOGNAME="${LOGNAME:-}" SHELL=/bin/bash \
        PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR="${TMPDIR:-/tmp}" LANG="${LANG:-en_US.UTF-8}" \
        CLAUDE_CONFIG_DIR="$cfg" DISABLE_AUTOUPDATER=1 "$cli" "$@")
}
# The judge, in the export, with the environment a required check has: no key, and SIM_SEEDS if this shell sets it.
judge() {
    (cd "$work" && env -i HOME="$HOME" PATH="$PATH" LANG=C ${SIM_SEEDS:+SIM_SEEDS="$SIM_SEEDS"} "$@")
}

mkdir "$out"
date -u +%Y-%m-%dT%H:%M:%SZ > "$out/ran_at"

# 1. The version, which must be the pin.
code1=0
run_cli --version > "$scratch/raw-1" 2>&1 || code1=$?
version=$(sed -n 1p "$scratch/raw-1" | cut -d' ' -f1)
rm -f "$scratch/raw-1"
if [ "$code1" -ne 0 ] || [ "$version" != "$PIN" ]; then
    echo "context_eval: the CLI at $cli is version '$version', exit $code1, not $PIN; nothing was asked of the model" >&2
    exit 1
fi

# 2. The export, twice.
git -C "$repo" archive "$commit" | tar -x -C "$work"
git -C "$repo" archive "$commit" | tar -x -C "$pristine"
[ -f "$work/AGENTS.md" ] || refuse "the export holds no AGENTS.md; COMMIT is not one of software-factory's"

# 3. The agent. Its transcript is captured and never printed; its standard error is counted, not kept.
code3=0
# shellcheck disable=SC2086  # OPTIONS is split into its words on purpose
run_cli -p "$sentence" --max-turns "$CAP" --allowedTools "$ALLOWED" --disallowedTools "$REFUSED" $OPTIONS \
    > "$scratch/raw-3" 2> "$scratch/raw-3.err" || code3=$?
err_lines=$(wc -l < "$scratch/raw-3.err" | tr -d ' ')
err_chars=$(wc -c < "$scratch/raw-3.err" | tr -d ' ')
rm -f "$scratch/raw-3.err"

# 4. The judge. The held-out test is copied in under tests/, run, and taken out before anything is recorded.
name=$(basename "$held_out" .py)
cp "$held_out" "$work/tests/$name.py"
code_test=0
judge python3 -m unittest -q "tests.$name" > "$scratch/judge-test" 2>&1 || code_test=$?
code_verify=0
judge make verify > "$scratch/judge-verify" 2>&1 || code_verify=$?
found=$(cd "$root" && python3 -m tools.context_eval mutants "$pristine" "$work")
targets=$(printf '%s' "$found" | python3 -I -c 'import json, sys; print(" ".join(json.load(sys.stdin)["targets"]))')
code_mutants=0
mutant_verdict=missing
if [ -n "$targets" ]; then
    # shellcheck disable=SC2086  # the targets are paths, one word each
    judge python3 -m tools.mutants $targets > "$scratch/judge-mutants" 2>&1 || code_mutants=$?
    mutant_verdict=$(printf '%s' "$found" | python3 -I -c '
import json, sys
names = json.load(sys.stdin)["names"]
lines = open(sys.argv[1]).read().splitlines()
killed = all(any(line.startswith("killed") and name in line for line in lines) for name in names)
print("killed" if names and killed else "survived")' "$scratch/judge-mutants")
fi
rm -f "$work/tests/$name.py"
find "$work" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
test_verdict=pass
[ "$code_test" -eq 0 ] || test_verdict=fail
verify_verdict=pass
[ "$code_verify" -eq 0 ] || verify_verdict=fail
printf '{"held_out_test": "%s", "verify": "%s", "mutant": "%s"}\n' "$test_verdict" "$verify_verdict" "$mutant_verdict" > "$scratch/verdicts.json"
python3 -I -c '
import json, sys
json.dump({"commit": sys.argv[1], "ran_at": open(sys.argv[2]).read().strip(), "cli_version": sys.argv[3],
           "cap_turns": int(sys.argv[4]), "code": sys.argv[5]}, open(sys.argv[6], "w"))' \
    "$commit" "$out/ran_at" "$version" "$CAP" "$code" "$scratch/meta.json"

# 5. The record, and what was checked. Neither holds a word of the model's.
code5=0
(cd "$root" && python3 -m tools.context_eval record "$scratch/raw-3" "$pristine" "$work" "$scratch/verdicts.json" \
    "$scratch/meta.json" "$out/record.json") || code5=$?
python3 -I -c '
import json, sys
a = sys.argv
json.dump({"agent": {"exit": int(a[1]), "stderr": {"lines": int(a[2]), "characters": int(a[3])}},
           "held_out_test": {"exit": int(a[4]), "verdict": a[5]}, "verify": {"exit": int(a[6]), "verdict": a[7]},
           "mutants": {"exit": int(a[8]), "verdict": a[9], "targets": a[10].split()}, "record": {"exit": int(a[11])}},
          open(a[12], "w"), indent=2)' \
    "$code3" "$err_lines" "$err_chars" "$code_test" "$test_verdict" "$code_verify" "$verify_verdict" \
    "$code_mutants" "$mutant_verdict" "$targets" "$code5" "$out/checked.json"
python3 -I -c '
import json, sys
env = {"CLAUDE_CONFIG_DIR": "the configuration directory the Factory alone uses, logged in on the Maintainer'"'"'s subscription",
       "DISABLE_AUTOUPDATER": "1", "passed_on": ["HOME", "USER", "LOGNAME", "PATH", "TMPDIR", "LANG"],
       "SHELL": "/bin/bash", "nothing_else": True}
json.dump([{"n": 1, "via": "cli", "call": "claude --version", "env": env, "cwd": "the export"},
           {"n": 3, "via": "cli", "call": "claude -p SENTENCE --max-turns %s --allowedTools %s --disallowedTools %s %s"
            % (sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]), "env": env, "cwd": "the export of " + sys.argv[5],
            "pinned": sys.argv[6], "prompt": "the one sentence, which the record carries as the task"}],
          open(sys.argv[7], "w"), indent=2)' "$CAP" "$ALLOWED" "$REFUSED" "$OPTIONS" "$commit" "$PIN" "$out/requests.json"

passed=false
[ "$code5" -eq 0 ] && passed=$(python3 -I -c 'import json, sys; print(str(json.load(open(sys.argv[1]))["passed"]).lower())' "$out/record.json")
echo "context_eval: agent exit $code3; held-out test $test_verdict; verify $verify_verdict; mutant $mutant_verdict; passed $passed"
echo "Done. Give a session this directory; it holds no credential and none of the model's text:"
echo "  $out"
[ "$passed" = true ] || exit 1
