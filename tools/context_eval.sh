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
# the Maintainer: it is copied into the export only after the agent has stopped, run on its own, and taken out again
# before `make verify`, the mutation check and the record, and this script never prints it. CLI, if given, is the
# CLI's program; by default the build the native installer kept for PIN, else `claude` on PATH. Whichever it is, it
# must say it is version PIN.
#
# In order, each in scratch directories outside every repo:
#   1. the CLI's version, which must be PIN;
#   2. the export, twice: one copy the agent works in, one kept as made, so that what it changed can be counted and
#      the judge's own files put back;
#   3. the agent: the CLI headless, the sentence as its whole prompt, CAP turns at most, with a scratch HOME and its
#      login alone, its network tools refused; its transcript is captured and never printed. Its shell is not
#      sandboxed (trial P-26 has no fixture yet): the record counts each path it named outside the export and each
#      command it could not read, so a run that looked elsewhere says so;
#   4. the judge, from the export as made: the held-out test copied in, run, and taken out; the Makefile and every
#      tool but tools/mutants.py put back as made, each one the agent had changed recorded; `make verify`; the whole
#      mutation check, which must kill every mutant, the agent's among them;
#   5. the record: tools/context_eval.py reads the transcript for the paths read, the first words of each command
#      and the result's counts, counts the changes by file, and writes OUT/record.json, a context-eval/1 run.
# OUT receives record.json, checked.json (each step's exit and counts), ran_at and requests.json (what was asked,
# without the sentence's answer or the transcript). The scratch directories are deleted, the transcript with them.
set -euo pipefail
set +x
export LC_ALL=C

# The version the engine port is pinned to, as trial P-13 recorded it (tools/trial_p13_cli.sh).
PIN=2.1.306
# The most turns the agent may take. The record keeps it beside what the run cost.
CAP=80
# What the agent may use: its file and shell tools; never the network, and never another agent.
ALLOWED="Read,Edit,Write,MultiEdit,Glob,Grep,Bash"
REFUSED="WebFetch,WebSearch,Task,Agent"
# --verbose here is the CLI's switch for the whole turn stream in stream-json, not a dump of any request; the stream
# goes to the scratch directory and is read for tool names, paths and counts alone.
OPTIONS="--output-format stream-json --verbose --permission-mode acceptEdits --no-session-persistence --strict-mcp-config --disable-slash-commands"
# The judge's own files, put back as made before it runs: the agent changes the Kernel, a test and tools/mutants.py.
JUDGES="Makefile GNUmakefile"

usage() {
    echo "usage: bash tools/context_eval.sh OUT CONFIG_DIR REPO COMMIT SENTENCE HELD_OUT [CLI]" >&2
    exit 2
}
refuse() {
    echo "context_eval: $*" >&2
    exit 2
}
real() {   # PATH, as the file system resolves it, every link followed
    python3 -I -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1"
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
case "$cfg/" in "$repo"/*) refuse "CONFIG_DIR is inside REPO; a login must never be kept there" ;; esac

# SENTENCE and HELD_OUT: files outside REPO, OUT and CONFIG_DIR, every link followed. The sentence is one line; the
# test is never read here.
for f in "$5" "$6"; do
    [ -f "$f" ] || refuse "SENTENCE and HELD_OUT must be files"
    full=$(real "$f")
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
held_out=$(real "$6")
case "$(basename "$held_out")" in test_*.py) ;; *) refuse "HELD_OUT is named test_<something>.py" ;; esac

# The CLI: the one named, else the build kept for PIN if the native installer kept one, else the one on PATH.
if [ "$#" -eq 7 ]; then
    cli=$7
else
    cli="$HOME/.local/share/claude/versions/$PIN"
    [ -x "$cli" ] || cli=$(command -v claude || true)
fi
[ -n "$cli" ] && [ -f "$cli" ] && [ -x "$cli" ] || refuse "no claude CLI found at '$cli'; install version $PIN"
cli=$(real "$cli")

scratch=$(cd "$(mktemp -d)" && pwd -P)
case "$scratch/" in "$root"/* | "$repo"/* | "$cfg"/*) rm -rf "$scratch"; refuse "the scratch directory is inside the repo or CONFIG_DIR" ;; esac
finish() {
    rm -rf "$scratch"
}
trap finish EXIT
trap 'exit 130' INT TERM
work="$scratch/work"
pristine="$scratch/pristine"
agent_home="$scratch/home"
mkdir "$work" "$pristine" "$agent_home"

# The CLI, in the export, with no environment from this shell but what is named here: a scratch HOME, so that
# nothing of the Maintainer's own is under it, and its login in CONFIG_DIR alone.
run_cli() {
    (cd "$work" && env -i HOME="$agent_home" USER="${USER:-}" LOGNAME="${LOGNAME:-}" SHELL=/bin/bash \
        PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR="$scratch" LANG="${LANG:-en_US.UTF-8}" \
        CLAUDE_CONFIG_DIR="$cfg" DISABLE_AUTOUPDATER=1 "$cli" "$@")
}
# The judge, in the export, with the environment a required check has: the system's PATH, a scratch HOME, no key,
# and SIM_SEEDS if this shell sets it.
judge() {
    (cd "$work" && env -i HOME="$agent_home" PATH=/usr/bin:/bin LANG=C ${SIM_SEEDS:+SIM_SEEDS="$SIM_SEEDS"} "$@")
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
[ -f "$work/AGENTS.md" ] && [ -d "$work/tests" ] || refuse "the export holds no AGENTS.md or no tests/; COMMIT is not one of software-factory's"
[ ! -e "$work/tests/test_held_out.py" ] || refuse "the export already holds tests/test_held_out.py, where the held-out test goes"

# 3. The agent. Its transcript is captured and never printed; its standard error is counted, not kept.
code3=0
# shellcheck disable=SC2086  # OPTIONS is split into its words on purpose
run_cli -p "$sentence" --max-turns "$CAP" --allowedTools "$ALLOWED" --disallowedTools "$REFUSED" $OPTIONS \
    > "$scratch/raw-3" 2> "$scratch/raw-3.err" || code3=$?
err_lines=$(wc -l < "$scratch/raw-3.err" | tr -d ' ')
err_chars=$(wc -c < "$scratch/raw-3.err" | tr -d ' ')
rm -f "$scratch/raw-3.err"
find "$work" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

# 4. The judge. The held-out test is copied in under tests/, run on its own, and taken out before anything else.
code_test=0
if [ -e "$work/tests/test_held_out.py" ]; then
    code_test=3      # the agent wrote the file the held-out test goes in: its own test is not the held-out one
else
    cp "$held_out" "$work/tests/test_held_out.py"
    judge python3 -m unittest -q tests.test_held_out > "$scratch/judge-test" 2>&1 || code_test=$?
    rm -f "$work/tests/test_held_out.py"
fi
find "$work" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
# The judge's own files, put back as made; each the agent had changed is recorded.
restored=""
for f in $JUDGES $(cd "$pristine" && find tools -type f ! -name mutants.py | sort); do
    if [ -f "$pristine/$f" ] && ! cmp -s "$pristine/$f" "$work/$f"; then
        restored="$restored $f"
        cp "$pristine/$f" "$work/$f"
    fi
done
code_verify=0
judge make verify > "$scratch/judge-verify" 2>&1 || code_verify=$?
found=$(cd "$root" && TMPDIR="$scratch" python3 -m tools.context_eval mutants "$pristine" "$work")
code_mutants=0
mutant_verdict=missing
if [ "$(printf '%s' "$found" | python3 -I -c 'import json, sys; print(len(json.load(sys.stdin)["names"]))')" -gt 0 ]; then
    # The whole check: every mutant must die, the agent's among them, as the required check asks.
    judge python3 -m tools.mutants > "$scratch/judge-mutants" 2>&1 || code_mutants=$?
    mutant_verdict=$(printf '%s' "$found" | python3 -I -c '
import json, re, sys
names = json.load(sys.stdin)["names"]
killed = set()
for line in open(sys.argv[1]).read().splitlines():
    m = re.match(r"^killed\s+(.*?)(?: \(.*\))?$", line)
    if m:
        killed.add(m.group(1))
print("killed" if int(sys.argv[2]) == 0 and all(name in killed for name in names) else "survived")' "$scratch/judge-mutants" "$code_mutants")
fi
find "$work" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
test_verdict=pass
[ "$code_test" -eq 0 ] || test_verdict=fail
verify_verdict=pass
[ "$code_verify" -eq 0 ] || verify_verdict=fail
printf '{"held_out_test": "%s", "verify": "%s", "mutant": "%s"}\n' "$test_verdict" "$verify_verdict" "$mutant_verdict" > "$scratch/verdicts.json"
python3 -I -c '
import json, sys
json.dump({"commit": sys.argv[1], "ran_at": open(sys.argv[2]).read().strip(), "cli_version": sys.argv[3],
           "cap_turns": int(sys.argv[4]), "code": sys.argv[5], "restored": sys.argv[6].split()}, open(sys.argv[7], "w"))' \
    "$commit" "$out/ran_at" "$version" "$CAP" "$code" "$restored" "$scratch/meta.json"

# 5. The record, written in the scratch directory, which the recorder is told is its own and reads and writes under
# alone, then copied to OUT; and what was checked. Neither holds a word of the model's.
code5=0
(cd "$root" && TMPDIR="$scratch" python3 -m tools.context_eval record "$scratch/raw-3" "$pristine" "$work" \
    "$scratch/verdicts.json" "$scratch/meta.json" "$scratch/record.json") || code5=$?
[ "$code5" -ne 0 ] || cp "$scratch/record.json" "$out/record.json"
python3 -I -c '
import json, sys
a = sys.argv
json.dump({"agent": {"exit": int(a[1]), "stderr": {"lines": int(a[2]), "characters": int(a[3])}},
           "held_out_test": {"exit": int(a[4]), "verdict": a[5]}, "verify": {"exit": int(a[6]), "verdict": a[7]},
           "mutants": {"exit": int(a[8]), "verdict": a[9], "added": json.loads(a[10])["names"]},
           "judge_restored": a[11].split(), "record": {"exit": int(a[12])},
           "sandbox": "none: the agent'"'"'s shell had a scratch HOME, its login and no key, and no other boundary (trial P-26 has no fixture)"},
          open(a[13], "w"), indent=2)' \
    "$code3" "$err_lines" "$err_chars" "$code_test" "$test_verdict" "$code_verify" "$verify_verdict" \
    "$code_mutants" "$mutant_verdict" "$found" "$restored" "$code5" "$out/checked.json"
python3 -I -c '
import json, sys
env = {"CLAUDE_CONFIG_DIR": "the configuration directory the Factory alone uses, logged in on the Maintainer'"'"'s subscription",
       "DISABLE_AUTOUPDATER": "1", "HOME": "a scratch directory", "passed_on": ["USER", "LOGNAME", "LANG"],
       "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "SHELL": "/bin/bash", "TMPDIR": "the scratch directory", "nothing_else": True}
json.dump([{"n": 1, "via": "cli", "call": "claude --version", "env": env, "cwd": "the export"},
           {"n": 3, "via": "cli", "call": "claude -p SENTENCE --max-turns %s --allowedTools %s --disallowedTools %s %s"
            % (sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]), "env": env, "cwd": "the export of " + sys.argv[5],
            "pinned": sys.argv[6], "prompt": "the one sentence, which the record carries as the task",
            "sandbox": "none; the record counts what the agent named outside the export"}],
          open(sys.argv[7], "w"), indent=2)' "$CAP" "$ALLOWED" "$REFUSED" "$OPTIONS" "$commit" "$PIN" "$out/requests.json"

passed=false
[ "$code5" -eq 0 ] && passed=$(python3 -I -c 'import json, sys; print(str(json.load(open(sys.argv[1]))["passed"]).lower())' "$out/record.json")
echo "context_eval: agent exit $code3; held-out test $test_verdict; verify $verify_verdict; mutant $mutant_verdict; passed $passed"
echo "Done. Give a session this directory; it holds no credential and none of the model's text:"
echo "  $out"
[ "$passed" = true ] || exit 1
