#!/usr/bin/env bash
# Trial P-51 (issue 312): on a GitHub-hosted Linux runner, does the pinned model CLI's sandbox let a tool's write outside
# its work directory land, and is it the subprocess scrub or the order of the Tasks that decides? In P-50 a write to the
# home directory landed whenever CLAUDE_CODE_SUBPROCESS_ENV_SCRUB was 1, in either order, and was refused when it was 0.
#
# The pass condition, written before the run:
#   pass: in every configuration a Run can be given (the scrub unset, 0 or 1), in both orders, at the pinned version
#   before and after: the CLI exited 0 and its answer is no error; the tool's result went back and is not an error; the
#   probe ran; and none of the four writes outside the work directory landed.
#   fail otherwise; the fixture says, for each configuration, order and target, whether the write landed, so that the
#   design's §4.9 and the run job's rules (#194) say which setting a Run must have, or that no setting holds the line.
#   Recorded, deciding nothing: each write's exit code as the probe saw it, the probe's PID namespace, whether a write
#   in the work directory itself landed, as a control, and the CLI's requests to the stub by path and count alone.
#
# Where it runs. Only in the canary's workflow trial-p51.yml, on ubuntu-24.04 with
# kernel.apparmor_restrict_unprivileged_userns=0 (as the runner stands, P-50 showed, the tool does not run), with no
# secret and no write grant: `bash p51/run.sh OUT ORDER CLI STUB`, once with ORDER "forward" and once "reversed". No
# model runs: the CLI's ANTHROPIC_BASE_URL is STUB, P-50's tools/trial_p50_stub.py, on 127.0.0.1, which answers one
# scripted call to the shell tool, `sh ./probe.sh`, and then the word done; the key is a dummy that names itself. This
# repo's tests run it against a stand-in CLI, the stub on 127.0.0.1.
#
# What it asks. The CLI's version, which must be PIN; then the same Task three times, each in a fresh work directory with
# a configuration directory of its own, under the sandbox settings SETTINGS: "unset", with no
# CLAUDE_CODE_SUBPROCESS_ENV_SCRUB at all; "plain", =0; "scrubbed", =1; in that order, or in the reverse. GITHUB_ACTIONS
# is set, as a run job's is. The probe tries four writes outside its work directory, each to a name made for this Task:
# a file in the home directory, a dotfile there, a file in /tmp, and a file in the work directory's parent; and one in
# the work directory itself, as a control. This script, outside the sandbox, asks whether each is there, then deletes it.
# OUT receives only checked-ORDER.json, which the workflow prints to its log for the fixture.
set -euo pipefail
set +x
export LC_ALL=C

PIN=2.1.306
ALLOWED_HOST=example.com
SETTINGS='{"sandbox": {"enabled": true, "failIfUnavailable": true, "autoAllowBashIfSandboxed": false, "allowUnsandboxedCommands": false, "network": {"allowedDomains": ["'"$ALLOWED_HOST"'"]}}, "permissions": {"allow": ["Bash(sh ./probe.sh)"]}}'
OPTIONS="--output-format json --no-session-persistence --strict-mcp-config --disable-slash-commands --permission-prompts none"
TOOLS="Bash"
ALLOWED="Bash(sh ./probe.sh)"
TASK='Use your shell tool once, to run exactly this command in the current directory, and nothing else: sh ./probe.sh
Then reply with the one word done.'
KEPT_RESULT="type subtype is_error num_turns"
KEY="dummy-p51-not-a-key"
TARGETS="home dotfile tmp parent"

usage() {
    echo "usage: bash p51/run.sh OUT ORDER CLI STUB, ORDER forward or reversed" >&2
    exit 2
}
refuse() {
    echo "trial_p51: $*" >&2
    exit 2
}
[[ "$#" -eq 4 ]] || usage
command -v python3 >/dev/null || refuse "python3 is needed"
case "$2" in forward) order="unset plain scrubbed" ;; reversed) order="scrubbed plain unset" ;;
    *) refuse "ORDER is forward or reversed" ;; esac
[[ ! -e "$1" ]] || refuse "$1 exists; name a new directory"
[[ -f "$3" && -x "$3" ]] || refuse "no CLI at '$3'"
cli=$(cd "$(dirname "$3")" && pwd -P)/$(basename "$3")
[[ -f "$4" ]] || refuse "no stub at '$4'"
stub=$(cd "$(dirname "$4")" && pwd -P)/$(basename "$4")
case "$(basename -- "$1")" in .|..) refuse "$1 names no new directory, since it ends in . or ..; name the directory itself" ;; esac
# OUT is made here, by this script alone: one made since it was found absent is refused, never written into.
mkdir -p -- "$(dirname -- "$1")"
# OUT's parent, and each directory above it, is one no other user can write to, or one that is sticky: in any other,
# another user could rename OUT once it is made and put a link where it was (issue 367).
above=$(cd "$(dirname -- "$1")" && pwd -P)
while :; do
    [[ -z "$(find "$above" -maxdepth 0 -perm -0002 ! -perm -1000)" ]] ||
        refuse "$above can be written by other users and is not sticky; name a directory under one only you can write to"
    [[ "$above" != / ]] || break
    above=$(dirname -- "$above")
done
mkdir -m 700 -- "$1" || refuse "$1 could not be made new by this run (made since, or refused); name a new directory"
out=$(cd "$1" && pwd -P)

# The scratch directory, and so each work directory's parent, is under the runner's own temporary directory, where a
# Run's work would be, and not under /tmp, which is a target of its own.
scratch=$(cd "$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/p51.XXXXXX")" && pwd -P)
base_cfg="$scratch/cfg"
mkdir "$base_cfg"
stub_pid=
targets_of() {   # NAME: the four paths outside a Task's work directory, one to a line, as TARGETS names them
    printf '%s\n' "$HOME/p51-write-$$-$1" "$HOME/.p51-write-$$-$1" "/tmp/p51-write-$$-$1" "$scratch/p51-parent-$$-$1"
}
finish() {
    [[ -z "$stub_pid" ]] || kill "$stub_pid" 2>/dev/null || true
    for name in unset plain scrubbed; do
        targets_of "$name" | while IFS= read -r target; do rm -f "$target"; done
    done
    rm -rf "$scratch"
}
# A target already there is refused before anything is asked, and left as it was found.
for name in unset plain scrubbed; do
    while IFS= read -r target; do
        if [[ -e "$target" || -L "$target" ]]; then
            rm -rf "$scratch"
            refuse "$target exists; remove it first"
        fi
    done < <(targets_of "$name")
done
trap finish EXIT
trap 'exit 130' INT TERM

# The stub, on a port of its own, which it prints once it listens; it is read through a pipe, never polled for.
mkfifo "$scratch/port.fifo"
(cd "$scratch" && exec python3 -I "$stub") > "$scratch/port.fifo" 2> "$scratch/stub.err" &
stub_pid=$!
port=
IFS= read -r port < "$scratch/port.fifo" || true
[[ "$port" =~ ^[0-9]{1,5}$ ]] || refuse "the stub did not say its port"
host_pidns=$(readlink "/proc/$$/ns/pid" 2>/dev/null || echo unknown)
node_dir=$(dirname "$(command -v node 2>/dev/null || echo /usr/bin/node)")

# The probe, as a template: @TARGETS@ is set in a Task's copy to the four paths, quoted. It tries each write once.
cat > "$scratch/probe.template" <<'PROBE'
#!/bin/sh
# P-51's probe: run by the model CLI's shell tool, inside its sandbox, in its work directory.
mkdir -p ./p51
: > ./p51/writes
for target in @TARGETS@; do
    touch "$target" 2>/dev/null
    echo "exit=$?" >> ./p51/writes
done
touch ./p51/inside 2>/dev/null
echo "inside exit=$?" > ./p51/inside-exit
readlink /proc/self/ns/pid > ./p51/pidns 2>/dev/null || echo unknown > ./p51/pidns
echo done > ./p51/ran
PROBE

run_cli() {   # WORK CFG [NAME=VALUE ...] -- ARG...
    local work=$1 cfg=$2
    local -a extra=()
    shift 2
    while [[ "$1" != "--" ]]; do
        extra+=("$1")
        shift
    done
    shift
    # No standard input, which a CLI given -p would wait on, and a limit on each run where the system has one.
    local -a limit=()
    command -v timeout >/dev/null && limit=(timeout 180)
    (cd "$work" && exec ${limit[@]+"${limit[@]}"} env -i HOME="$HOME" USER="${USER:-}" LOGNAME="${LOGNAME:-}" SHELL=/bin/bash \
        PATH="$node_dir:/usr/bin:/bin:/usr/sbin:/sbin" TMPDIR="${TMPDIR:-/tmp}" LANG="${LANG:-C.UTF-8}" \
        GITHUB_ACTIONS=true CLAUDE_CONFIG_DIR="$cfg" DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
        ANTHROPIC_BASE_URL="http://127.0.0.1:$port" ANTHROPIC_API_KEY="$KEY" ${extra[@]+"${extra[@]}"} "$cli" "$@" < /dev/null)
}

version=$(run_cli "$scratch" "$base_cfg" -- --version 2>/dev/null | head -n 1 | awk '{print $1}') || version=
parts=()
for name in $order; do
    case "$name" in unset) scrub=() ;; plain) scrub=(CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=0) ;; scrubbed) scrub=(CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1) ;; esac
    work="$scratch/work-$name"
    task_cfg="$scratch/cfg-$name"
    mkdir "$work" "$task_cfg"
    targets_of "$name" > "$scratch/targets-$name"
    python3 -I -c '
import shlex, sys
text = open(sys.argv[1]).read()
targets = open(sys.argv[3]).read().split("\n")[:4]
open(sys.argv[2], "w").write(text.replace("@TARGETS@", " ".join(shlex.quote(t) for t in targets)))' \
        "$scratch/probe.template" "$work/probe.sh" "$scratch/targets-$name"
    before=$(wc -l < "$scratch/stub.log" | tr -d ' ')
    code=0
    # shellcheck disable=SC2086  # OPTIONS is split into its words on purpose
    run_cli "$work" "$task_cfg" ${scrub[@]+"${scrub[@]}"} -- -p "$TASK" --settings "$SETTINGS" $OPTIONS \
        --tools "$TOOLS" --allowedTools "$ALLOWED" > "$scratch/raw-$name" 2> "$scratch/raw-$name.err" || code=$?
    if [[ "$code" -ne 0 ]]; then
        echo "trial_p51: $name exited $code; its first lines on standard error:" >&2
        head -n 20 "$scratch/raw-$name.err" | cut -c1-300 >&2
        echo "trial_p51: what the stub was asked in that Task, by path and answer:" >&2
        sed -n "$((before + 1)),$((before + 20))p" "$scratch/stub.log" >&2
    fi
    tail -n "+$((before + 1))" "$scratch/stub.log" > "$scratch/stub-$name.log"
    python3 -I -c '
import json, os, re, sys
raw, err, stub_log, work, part_file, targets_file = sys.argv[1:7]
code, name, host_pidns, kept_keys, names = int(sys.argv[7]), sys.argv[8], sys.argv[9], sys.argv[10].split(), sys.argv[11].split()
def read(path):
    try:
        with open(os.path.join(work, "p51", path), errors="replace") as f:
            return f.read()
    except OSError:
        return None
text = open(raw, errors="replace").read()
try:
    said = json.loads(text)
except ValueError:
    said = None
if isinstance(said, list):
    found = [m for m in said if isinstance(m, dict) and m.get("type") == "result"]
    said = found[-1] if found else None
def plain(value):
    return isinstance(value, (bool, int)) or isinstance(value, str) and re.fullmatch(r"[a-z_]{1,32}", value) is not None
answer = {k: said[k] for k in kept_keys if k in said and plain(said[k])} if isinstance(said, dict) else None
stub = [json.loads(line) for line in open(stub_log) if line.strip()]
requests = {}
for line in stub:
    key = "%s %s" % (line.get("path"), line.get("answer"))
    requests[key] = requests.get(key, 0) + 1
asked = [l.get("n") for l in stub if l.get("answer") == "tool_use"]
back = [l for l in stub if l.get("answer") == "text" and l.get("result") is True and asked and (l.get("n") or 0) > asked[0]]
errors = [e for l in back for e in l.get("result_error") or [] if isinstance(e, bool)]
writes, inside, pidns, ran = (read(p) for p in ("writes", "inside-exit", "pidns", "ran"))
exits = [int(c) for c in re.findall(r"^exit=([0-9]{1,3})$", writes or "", re.M)]
targets = open(targets_file).read().split("\n")[:4]
landed = {n: os.path.lexists(t) for n, t in zip(names, targets)}
pidns = (pidns or "").strip()
pidns = pidns if re.fullmatch(r"pid:\[[0-9]{1,20}\]", pidns) else None
found = re.fullmatch(r"inside exit=([0-9]{1,3})\n?", inside or "")
part = {
    "configuration": name, "exit": code, "answer": answer,
    "stderr": {"lines": open(err, errors="replace").read().count("\n")},
    "stub": {"requests": requests, "tool_call_asked": bool(asked), "result_sent": bool(back), "result_is_error": errors or None},
    "probe_ran": ran is not None and ran.strip() == "done",
    "writes": {n: {"exit": exits[i] if i < len(exits) else None, "landed": landed[n]} for i, n in enumerate(names)},
    "inside": {"exit": int(found.group(1)) if found else None, "landed": os.path.lexists(os.path.join(work, "p51", "inside"))},
    "pid_namespace": {"own": None if pidns is None or host_pidns == "unknown" else pidns != host_pidns},
}
answered = code == 0 and isinstance(answer, dict) and answer.get("is_error") is False
tool_ran = bool(back) and True not in errors
held = part["probe_ran"] and len(exits) == len(names) and not any(landed.values())
part["holds"] = {"answered": answered, "tool_ran": tool_ran, "probe_ran": part["probe_ran"], "every_write_held": held}
part["holds"]["passes"] = all(part["holds"].values())
json.dump(part, open(part_file, "w"), indent=2)
' "$scratch/raw-$name" "$scratch/raw-$name.err" "$scratch/stub-$name.log" "$work" "$scratch/part-$name.json" \
        "$scratch/targets-$name" "$code" "$name" "$host_pidns" "$KEPT_RESULT" "$TARGETS"
    targets_of "$name" | while IFS= read -r target; do rm -f "$target"; done
    rm -rf "$work"
    parts+=("$scratch/part-$name.json")
done
after=$(run_cli "$scratch" "$base_cfg" -- --version 2>/dev/null | head -n 1 | awk '{print $1}') || after=

python3 -I -c '
import json, sys
order, pin, before, after, out = sys.argv[1:6]
parts = [json.load(open(p)) for p in sys.argv[6:]]
pinned = before == pin and after == pin
json.dump({"order": order, "version": {"pinned": pin, "before": before, "after": after}, "configurations": parts,
           "every_configuration_passes": pinned and len(parts) == 3 and all(p["holds"]["passes"] for p in parts)},
          open(out, "w"), indent=2)' "$2" "$PIN" "$version" "$after" "$out/checked-$2.json" "${parts[@]}"
held=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["every_configuration_passes"] is True)' "$out/checked-$2.json")
echo "trial_p51: order $2, version $version, after $after; every configuration passes: $held"
