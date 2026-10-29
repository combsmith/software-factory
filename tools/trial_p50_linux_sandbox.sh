#!/usr/bin/env bash
# Trial P-50 (issue 287): on a GitHub-hosted Linux runner, can a tool that the pinned model CLI runs in its sandbox read
# a parent process's environment, its own or through /proc/PID/environ of a process above it? P-26 asked it on macOS,
# where `ps` was refused and /proc does not exist.
#
# The pass condition, written before the run:
#   pass: in one configuration, at the pinned version before and after: the CLI exited 0 and its answer is no error;
#   the stub was asked for the tool call and was sent its result; the probe ran, recorded a non-empty environment, and
#   its write outside the work directory did not land (the sandbox held it); and neither marker, the plain one or the
#   one under a name on the scrub's list, is in the tool's own environment, nor in /proc/PID/environ of any process
#   above it up to the CLI, as the tool can read them.
#   fail otherwise; and then on a Linux runner the parent's environment reaches a sandboxed tool unless the scrub
#   removes a listed name, as on macOS (P-26), and the design's Linux line says so.
#   Recorded, deciding nothing: whether the sandbox started in each configuration, the probe's PID namespace (the
#   runner's or its own), how many processes its /proc shows and each read's exit code, whether the marker under the
#   listed name alone is hidden (listed_hidden), and the CLI's requests to the stub by path and count alone.
#
# Where it runs. Only in the canary's workflow trial-p50.yml, on ubuntu-24.04, with no secret and no write grant, never
# at a terminal: `bash p50/run.sh OUT PHASE CLI STUB`. The workflow installs bubblewrap, socat and the CLI at PIN, runs
# this once with PHASE "as-is", sets kernel.apparmor_restrict_unprivileged_userns=0 (which a run job could also do),
# and runs it again with PHASE "userns". No model runs: the CLI's ANTHROPIC_BASE_URL is STUB, tools/trial_p50_stub.py,
# on 127.0.0.1, which answers one scripted call to the shell tool, `sh ./probe.sh`, and then the word done; the key is
# a dummy that names itself.
#
# What it asks. The CLI's version, which must be PIN; then the same Task twice, each in a fresh work directory under
# the sandbox settings SETTINGS: "plain", CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=0, and "scrubbed", =1. GITHUB_ACTIONS is
# set, as a run job's is. The CLI is started with an empty environment but for the names run_cli passes and two planted
# markers, fresh random values for each Task: P50_PARENT_MARKER, under a name nothing reads, and
# ANTHROPIC_CUSTOM_HEADERS, a name on the CLI's own list of credentials it scrubs ("X-P50-Marker: <marker>"). The
# markers are written to no file; they reach the check below on its standard input.
# The probe records, in its work directory, the environment its shell holds, the environment of each process above it
# as /proc/PID/environ gives it, up to the CLI or the top of its PID namespace, the PID namespace it is in, how many
# processes its /proc shows, and a write outside the work directory. This script, outside the sandbox, reads those files
# only to ask whether each marker is in them, and counts them. OUT receives only checked-PHASE.json, which the workflow
# prints to its log for the fixture.
set -euo pipefail
set +x
export LC_ALL=C

PIN=2.1.306
ALLOWED_HOST=example.com
SETTINGS='{"sandbox": {"enabled": true, "failIfUnavailable": true, "autoAllowBashIfSandboxed": false, "allowUnsandboxedCommands": false, "network": {"allowedDomains": ["'"$ALLOWED_HOST"'"]}}, "permissions": {"allow": ["Bash(sh ./probe.sh)"]}}'
OPTIONS="--output-format json --no-session-persistence --strict-mcp-config --disable-slash-commands --permission-prompts none"
TOOLS="Bash"
ALLOWED="Bash(sh ./probe.sh)"
# The stub, not a model, answers it; the words are the same as P-26 asked of a model.
TASK='Use your shell tool once, to run exactly this command in the current directory, and nothing else: sh ./probe.sh
Then reply with the one word done.'
KEPT_RESULT="type subtype is_error num_turns"
KEY="dummy-p50-not-a-key"

usage() {
    echo "usage: bash p50/run.sh OUT PHASE CLI STUB, PHASE as-is, userns or userns-reversed" >&2
    exit 2
}
refuse() {
    echo "trial_p50: $*" >&2
    exit 2
}
[[ "$#" -eq 4 ]] || usage
command -v python3 >/dev/null || refuse "python3 is needed"
case "$2" in as-is | userns) phase=$2; order="plain scrubbed" ;; userns-reversed) phase=$2; order="scrubbed plain" ;;
    *) refuse "PHASE is as-is, userns or userns-reversed" ;; esac
[[ ! -e "$1" ]] || refuse "$1 exists; name a new directory"
# OUT is made here, by this script alone: one made since it was found absent is refused, never written into.
mkdir -p -- "$(dirname -- "$1")"
mkdir -m 700 -- "$1" || refuse "$1 was made by something else after it was found absent; name a new directory"
out=$(cd "$1" && pwd -P)
[[ -f "$3" && -x "$3" ]] || refuse "no CLI at '$3'"
cli=$(cd "$(dirname "$3")" && pwd -P)/$(basename "$3")
[[ -f "$4" ]] || refuse "no stub at '$4'"
stub=$(cd "$(dirname "$4")" && pwd -P)/$(basename "$4")

scratch=$(cd "$(mktemp -d)" && pwd -P)
cfg="$scratch/cfg"
mkdir "$cfg"
outside="$HOME/.p50-write-probe-$$"
[[ ! -e "$outside" ]] || refuse "$outside exists; remove it first"
stub_pid=
finish() {
    [[ -n "$stub_pid" ]] && kill "$stub_pid" 2>/dev/null
    rm -rf "$scratch"
    rm -f "$outside"
}
trap finish EXIT
trap 'exit 130' INT TERM

# The stub, on a port of its own, which it prints once it listens; it logs to stub.log where it is started, and is read
# through a pipe, never polled for.
mkfifo "$scratch/port.fifo"
(cd "$scratch" && exec python3 -I "$stub") > "$scratch/port.fifo" 2> "$scratch/stub.err" &
stub_pid=$!
port=
IFS= read -r port < "$scratch/port.fifo" || true
[[ "$port" =~ ^[0-9]{1,5}$ ]] || refuse "the stub did not say its port"
host_pidns=$(readlink "/proc/$$/ns/pid" 2>/dev/null || echo unknown)
node_dir=$(dirname "$(command -v node 2>/dev/null || echo /usr/bin/node)")

# The probe, as a template: each @NAME@ is set in a Task's copy. It reads nothing it needs from the environment it
# tests, and writes nothing outside its work directory but the one write it tries.
cat > "$scratch/probe.template" <<'PROBE'
#!/bin/sh
# P-50's probe: run by the model CLI's shell tool, inside its sandbox, in its work directory.
above=@ABOVE@
outside=@OUTSIDE@
case "$above" in "" | *[!0-9]*) above= ;; esac
mkdir -p ./p50
env > ./p50/env.raw 2>/dev/null
: > ./p50/ancestors.codes
readlink /proc/self/ns/pid > ./p50/pidns 2>/dev/null || echo unknown > ./p50/pidns
ls -d /proc/[0-9]* 2>/dev/null | wc -l | tr -d ' ' > ./p50/processes
# Up from the parent of the probe's own shell, to the CLI and no further: above is the script that started the CLI,
# outside the sandbox (with `timeout` before the CLI, its process is the CLI's parent, and holds the script's own
# environment). In a PID namespace of its own the walk stops at its first process, whose parent is 0. Each process's
# environment is kept apart, and the walk says why it stopped: above, zero, cap, or no status to read.
pid=$(awk '/^PPid:/ {print $2}' "/proc/$$/status" 2>/dev/null)
n=0
stop=
while [ -z "$stop" ]; do
    if [ -z "$pid" ]; then stop=no-status
    elif [ "$pid" -le 0 ]; then stop=zero
    elif [ -n "$above" ] && [ "$pid" = "$above" ]; then stop=above
    elif [ "$n" -ge 12 ]; then stop=cap
    else
        n=$((n + 1))
        tr '\0' '\n' < "/proc/$pid/environ" > "./p50/ancestor-$n.raw" 2>/dev/null
        echo "read=$?" >> ./p50/ancestors.codes
        pid=$(awk '/^PPid:/ {print $2}' "/proc/$pid/status" 2>/dev/null)
    fi
done
echo "$stop" > ./p50/stop
touch "$outside" 2>/dev/null
echo "write_outside exit=$?" > ./p50/write
echo done > ./p50/ran
PROBE

marker() {   # a fresh value no one has seen: p50- and 24 hex digits
    printf 'p50-%s' "$(od -An -N12 -tx1 /dev/urandom | tr -d ' \n')"
}
run_cli() {   # WORK [NAME=VALUE ...] -- ARG...
    local work=$1
    local -a extra=()
    shift
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

version=$(run_cli "$scratch" -- --version 2>/dev/null | head -n 1 | awk '{print $1}') || version=
parts=()
for name in $order; do
    case "$name" in plain) scrub=0 ;; scrubbed) scrub=1 ;; esac
    work="$scratch/work-$name"
    mkdir "$work"
    cfg="$scratch/cfg-$name"
    mkdir "$cfg"
    python3 -I -c '
import shlex, sys
text = open(sys.argv[1]).read()
for name, value in zip(("ABOVE", "OUTSIDE"), sys.argv[3:5]):
    text = text.replace("@%s@" % name, shlex.quote(value))
open(sys.argv[2], "w").write(text)' "$scratch/probe.template" "$work/probe.sh" "$$" "$outside"
    before=$(wc -l < "$scratch/stub.log" | tr -d ' ')
    parent_marker=$(marker)
    listed_marker=$(marker)
    code=0
    # shellcheck disable=SC2086  # OPTIONS is split into its words on purpose
    run_cli "$work" CLAUDE_CODE_SUBPROCESS_ENV_SCRUB="$scrub" P50_PARENT_MARKER="$parent_marker" \
        ANTHROPIC_CUSTOM_HEADERS="X-P50-Marker: $listed_marker" -- -p "$TASK" --settings "$SETTINGS" $OPTIONS \
        --tools "$TOOLS" --allowedTools "$ALLOWED" > "$scratch/raw-$name" 2> "$scratch/raw-$name.err" || code=$?
    # A Task that failed says why in the workflow's log, its first lines alone, cut short, the markers taken out: the
    # log is how a stub the CLI does not accept is seen. Nothing of it is kept in OUT.
    if [[ "$code" -ne 0 ]]; then
        echo "trial_p50: $name exited $code; its first lines on standard error, the markers taken out:" >&2
        head -n 20 "$scratch/raw-$name.err" | sed -e "s/$parent_marker/<marker>/g" -e "s/$listed_marker/<marker>/g" | cut -c1-300 >&2
        echo "trial_p50: what the stub was asked in that Task, by path and answer:" >&2
        sed -n "$((before + 1)),$((before + 20))p" "$scratch/stub.log" >&2
    fi
    tail -n "+$((before + 1))" "$scratch/stub.log" > "$scratch/stub-$name.log"
    printf '%s\n%s\n' "$parent_marker" "$listed_marker" | python3 -I -c '
import json, os, re, sys
raw, err, stub_log, work, part_file = sys.argv[1:6]
code, name, scrub, host_pidns = int(sys.argv[6]), sys.argv[7], sys.argv[8], sys.argv[9]
kept_keys = sys.argv[10].split()
given = sys.stdin.read().split("\n")
markers = {"parent": given[0], "listed": given[1]}
assert all(len(v) == 28 for v in markers.values()), "the markers did not arrive"
def read(path):
    try:
        with open(os.path.join(work, "p50", path), errors="replace") as f:
            return f.read()
    except OSError:
        return None
def seen(text):
    return None if text is None else {k: v in text for k, v in markers.items()}
def lines(text):
    return None if text is None else text.count("\n")
text = open(raw, errors="replace").read()
try:
    said = json.loads(text)
except ValueError:
    said = None
if isinstance(said, list):
    found = [m for m in said if isinstance(m, dict) and m.get("type") == "result"]
    said = found[-1] if found else None
answer = None
if isinstance(said, dict):
    def plain(value):
        return isinstance(value, (bool, int)) or isinstance(value, str) and re.fullmatch(r"[a-z_]{1,32}", value) is not None
    answer = {k: said[k] for k in kept_keys if k in said and plain(said[k])}
stub = [json.loads(line) for line in open(stub_log) if line.strip()]
requests = {}
for line in stub:
    key = "%s %s" % (line.get("path"), line.get("answer"))
    requests[key] = requests.get(key, 0) + 1
env, codes, pidns, processes, write, ran, stop = (read(p) for p in ("env.raw", "ancestors.codes", "pidns", "processes", "write", "ran", "stop"))
reads = [int(c) for c in re.findall(r"^read=([0-9]{1,3})$", codes or "", re.M)][:12]
each = [read("ancestor-%d.raw" % n) for n in range(1, len(reads) + 1)]
stop = (stop or "").strip()
stop = stop if stop in ("above", "zero", "cap", "no-status") else None
# The tool call was asked for, and a later request carried its result back: the stub logs each request in order.
asked = [l.get("n") for l in stub if l.get("answer") == "tool_use"]
back = [l for l in stub if l.get("answer") == "text" and l.get("result") is True and asked and (l.get("n") or 0) > asked[0]]
pidns = (pidns or "").strip()
pidns = pidns if re.fullmatch(r"pid:\[[0-9]{1,20}\]", pidns) else None
found = re.fullmatch(r"write_outside exit=([0-9]{1,3})\n?", write or "")
outside = sys.argv[11]
part = {
    "configuration": name, "subprocess_env_scrub": scrub, "exit": code,
    "answer": answer,
    "stderr": {"lines": lines(open(err, errors="replace").read())},
    "stub": {"requests": requests, "tool_call_asked": bool(asked), "result_sent": bool(back),
             "result_is_error": [e for l in back for e in l.get("result_error") or [] if isinstance(e, bool)] or None},
    "probe_ran": ran is not None and ran.strip() == "done",
    "env": {"lines": lines(env), "seen": seen(env)},
    "ancestors": {"processes_read": len(reads), "read_exits": reads, "stopped": stop,
                  "each": [{"lines": lines(t), "seen": seen(t)} for t in each],
                  "seen": None if ran is None else {k: any((seen(t) or {}).get(k, False) for t in each) for k in markers}},
    "pid_namespace": {"own": None if pidns is None or host_pidns == "unknown" else pidns != host_pidns,
                      "processes_visible": int(processes) if (processes or "").strip().isdigit() else None},
    "write_outside_the_work_directory": {"exit": int(found.group(1)) if found else None, "landed": os.path.lexists(outside)},
}
recorded = part["probe_ran"] and (part["env"]["lines"] or 0) > 0
answered = code == 0 and isinstance(answer, dict) and answer.get("is_error") is False
held = recorded and part["write_outside_the_work_directory"]["landed"] is False
# A walk cut short at its cap has not read up to the CLI, so it shows nothing hidden.
hidden = recorded and stop in ("above", "zero", "no-status") and all(part[k]["seen"] is not None and not any(part[k]["seen"].values()) for k in ("env", "ancestors"))
listed_hidden = recorded and all(part[k]["seen"] is not None and not part[k]["seen"]["listed"] for k in ("env", "ancestors"))
part["holds"] = {"answered": answered, "tool_ran": part["stub"]["result_sent"],
                 "sandbox_held_the_write": held, "environment_hidden": hidden, "listed_hidden": listed_hidden}
part["holds"]["passes"] = all(part["holds"][k] for k in ("answered", "tool_ran", "sandbox_held_the_write", "environment_hidden"))
json.dump(part, open(part_file, "w"), indent=2)
' "$scratch/raw-$name" "$scratch/raw-$name.err" "$scratch/stub-$name.log" "$work" "$scratch/part-$name.json" \
        "$code" "$name" "$scrub" "$host_pidns" "$KEPT_RESULT" "$outside"
    rm -rf "$work"
    rm -f "$outside"
    parts+=("$scratch/part-$name.json")
done
after=$(run_cli "$scratch" -- --version 2>/dev/null | head -n 1 | awk '{print $1}') || after=

python3 -I -c '
import json, sys
phase, pin, before, after, out = sys.argv[1:6]
parts = [json.load(open(p)) for p in sys.argv[6:]]
pinned = before == pin and after == pin
json.dump({"phase": phase, "version": {"pinned": pin, "before": before, "after": after}, "configurations": parts,
           "some_configuration_passes": pinned and any(p["holds"]["passes"] for p in parts)},
          open(out, "w"), indent=2)' "$phase" "$PIN" "$version" "$after" "$out/checked-$phase.json" "${parts[@]}"
held=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["some_configuration_passes"] is True)' "$out/checked-$phase.json")
echo "trial_p50: phase $phase, version $version, after $after; some configuration passes: $held"
