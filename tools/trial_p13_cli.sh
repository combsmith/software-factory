#!/usr/bin/env bash
# Trial P-13: does the vendor's CLI, headless, at a pinned version, on a subscription it is logged in to,
# return output that validates against a result schema, and its usage? (design, section 6; issue 15)
#
#   bash tools/trial_p13_cli.sh OUT CONFIG_DIR [CLI]
#
# CONFIG_DIR is a configuration directory of its own, apart from the Maintainer's interactive one, which the
# Maintainer has already logged the CLI into on his own subscription at his own terminal (decision 0033). This
# script logs nothing in and mints nothing. It never reads, prints, copies or writes a credential: the CLI is
# started with an empty environment but for CLAUDE_CONFIG_DIR, DISABLE_AUTOUPDATER and the few names in
# run_cli, so no key or token in this shell reaches it, and it reads its own login from CONFIG_DIR. OUT is a
# directory that does not exist yet, outside this repo. CLI, if given, is the path of the CLI's program; by
# default it is the build the native installer kept for PIN, else `claude` on PATH. Whichever it is, it must
# say it is version PIN.
# Run it from a checkout of software-factory, with bash 3.2 or later and python3.
#
# Three asks, in order, each in an empty scratch directory outside the repo:
#   1. the CLI's version, which must be PIN;
#   2. whether it is logged in, and how: only the fields KEPT_STATUS names are kept, never an address;
#   3. one fixed Task, headless (-p), with --json-schema SCHEMA and --output-format json.
# The answers are captured in the scratch directory and never printed. Of the Task's answer only the fields
# KEPT_RESULT names are kept (issue 178): the model's text (`result`), the inputs of any tool it was refused
# and every field the CLI adds that is not named are dropped and counted, so a new field can never carry the
# model's text out; its structured output is validated against SCHEMA with tools/jsonschema_lite.py and kept
# only if it validates, and in every other kept field a string is kept only under a key STRING_KEYS names and in a
# code's shape, and a key is held to that shape too, as the CLI's counts and codes hold nothing else. What is left is redacted by tools/redact_trial.py, which takes out anything
# shaped like a credential, and the raw capture is deleted. The model runs with no tool at all (`--tools ""`).
# OUT receives only: ran_at, requests.json (what was asked), clean-N (each redacted answer), redacted-N (where
# the redaction took something, never what), and checked.json (each part of the pass, and of the Task's standard
# error only how many lines and characters it had: it may hold the model's text, so none of it is kept).
#
# If the structured output does not validate, issue 15 says the metered key is tried and recorded. This
# script does not do that: it is a second step, the Maintainer's, in the runbook.
set -euo pipefail
set +x
export LC_ALL=C
shopt -s nocasematch    # a path is compared without case: the file system may not tell .claude from .CLAUDE

# The version of the CLI this trial runs at. The design names the CLI (section 3.5, engine claude-cli) and
# asks for a pinned version (P-13), but leaves the version open. P-13 first ran at 2.1.302, the one installed
# then; the installer pruned that build, so the pin moved to 2.1.306 by a second run of this script at it
# (decision 0033's row), and each fixture records the version the engine port was pinned to when it ran.
PIN=2.1.306
# The fields of `auth status --json` kept, by name. Any other, an address or an org among them, is dropped.
KEPT_STATUS="loggedIn authMethod apiProvider subscriptionType"
# The fields of the Task's answer kept, by name: what the CLI says of the run and its counts, never the model's
# text. `structured_output` is kept only once it validates, and `permission_denials` only as tool names.
KEPT_RESULT="type subtype is_error num_turns duration_ms duration_api_ms total_cost_usd usage modelUsage stop_reason permission_denials structured_output"
# Under a kept field a string is kept only under one of these keys, and only in a code's shape: letters, digits, _ . : -
# and no more than 64 of them. The CLI's counts are numbers; its words are codes under known keys; anything else is dropped.
# These are the keys the run at 2.1.306 (trials/P-13.v2-1-306.json) found holding a string, at the top or under a kept
# key, and tool_name, which holds one only when a tool is refused (issue 247). One list serves every kept field: it is
# usage's and modelUsage's few words and the answer's own codes, and nothing else.
STRING_KEYS="type subtype stop_reason tool_name service_tier inference_geo speed canonicalModel provider costBasis"

usage() {
    echo "usage: bash tools/trial_p13_cli.sh OUT CONFIG_DIR [CLI]" >&2
    exit 2
}
refuse() {
    echo "trial_p13_cli: $*" >&2
    exit 2
}
[[ "$#" -eq 2 || "$#" -eq 3 ]] || usage
command -v python3 >/dev/null || refuse "python3 is needed"

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
[[ -f "$root/tools/redact_trial.py" && -f "$root/tools/jsonschema_lite.py" ]] ||
    refuse "run the copy of this script in a checkout of software-factory"

# OUT: new, and outside the repo, read as the file system resolves it.
case "$1" in "") usage ;; esac
parent=$(cd "$(dirname "$1")" 2>/dev/null && pwd -P) || refuse "the directory that would hold OUT does not exist"
out="$parent/$(basename "$1")"
[[ ! -e "$out" && ! -L "$out" ]] || refuse "$out exists; name a new directory"
case "$out/" in "$root"/*) refuse "OUT is inside the repo; name a directory outside it" ;; esac

# CONFIG_DIR: one of its own, never the Maintainer's interactive one, and never inside the repo or OUT.
[[ -d "$2" ]] || refuse "CONFIG_DIR is not a directory; log the CLI in to it first (the runbook, step 1)"
cfg=$(cd "$2" && pwd -P)
home=$(cd "$HOME" && pwd -P)
above="${cfg%/}/"    # CONFIG_DIR with one trailing slash, so that / is "/" and every directory under it is held
case "$home/" in "$above"*) refuse "CONFIG_DIR is the home directory or holds it: the default configuration, not one of its own" ;; esac
dot=$(cd "$home/.claude" 2>/dev/null && pwd -P || echo "$home/.claude")    # ~/.claude as the file system resolves it
case "$cfg/" in "$dot"/*) refuse "CONFIG_DIR is under ~/.claude: the Maintainer's own configuration, not one of its own" ;; esac
case "$cfg/" in "$root"/*) refuse "CONFIG_DIR is inside the repo; a login must never be kept there" ;; esac
case "$out/" in "$cfg"/*) refuse "OUT is inside CONFIG_DIR; name a directory apart from it" ;; esac

# The CLI: the one named, else the build kept for PIN if the native installer kept one, else the one on PATH.
# Its version is asked below, before anything else.
if [[ "$#" -eq 3 ]]; then
    cli=$3
else
    cli="$HOME/.local/share/claude/versions/$PIN"
    [[ -x "$cli" ]] || cli=$(command -v claude || true)
fi
[[ -n "$cli" && -f "$cli" && -x "$cli" ]] || refuse "no claude CLI found at '$cli'; install version $PIN"
cli=$(cd "$(dirname "$cli")" && pwd -P)/$(basename "$cli")

TASK=$(cat <<'EOF'
You are given one Task, as JSON, and return its Result as the structured output. Write no prose.
Task: {"schema": "task/1", "run": "r_p13", "role": "pr-review", "intent": "adjudicate-findings", "findings": [{"id": "f_9c1e", "asked": "Return early from parse() when its list is empty, before it reads the first item.", "change": "parse() now returns an empty result when the list is empty, before reading any item."}, {"id": "f_22ab", "asked": "Add a test of parse() on an empty list.", "change": "No test was added or changed."}], "result_schema": "result/1"}
Give each finding one disposition. A finding the change fully answers is accepted. A finding the change does not fully answer is rejected, with the reason code fix_incomplete. The status is completed. The run is the run of the Task.
EOF
)
# The smallest Result that section 3.5 implies, as the model returns it: no `usage`, which the Harness fills
# from the CLI's own output, and no `release`, `effects`, `bundle` or `preflight`, which this Task has none of.
# Every string is a code or an id, so a valid answer holds no prose. Written in the subset tools/jsonschema_lite.py
# enforces, and with no $ref, so that the CLI and this repo read it alike.
SCHEMA=$(cat <<'EOF'
{"type": "object", "additionalProperties": false, "required": ["schema", "run", "status", "dispositions"], "properties": {"schema": {"const": "result/1"}, "run": {"type": "string", "pattern": "^r_[a-z0-9]+$"}, "status": {"enum": ["completed", "incomplete", "failed", "refused", "superseded"]}, "dispositions": {"type": "array", "items": {"type": "object", "additionalProperties": false, "required": ["finding", "decision"], "properties": {"finding": {"type": "string", "pattern": "^f_[0-9a-f]{4}$"}, "decision": {"type": "object", "additionalProperties": false, "required": ["result"], "properties": {"result": {"enum": ["accepted", "rejected"]}, "reason": {"enum": ["fix_incomplete"]}}}}}}}}
EOF
)
OPTIONS="--output-format json --no-session-persistence --strict-mcp-config --disable-slash-commands --permission-prompts none"
# The model is given no tool: --tools with an empty list. Held apart from OPTIONS so that the empty word survives.
TOOLS=""

# Its own line: inside the cd, a failed mktemp would be read as the directory this stands in, which the clean-up removes.
made=$(mktemp -d)
scratch=$(cd "$made" && pwd -P)
case "$scratch/" in "$root"/* | "$cfg"/*) rm -rf "$scratch"; refuse "the scratch directory is inside the repo or CONFIG_DIR" ;; esac
finish() {
    rm -rf "$scratch"
}
trap finish EXIT
trap 'exit 130' INT TERM
work="$scratch/work"
mkdir "$work"

# The CLI, in an empty directory, with no environment from this shell but what is named here.
run_cli() {
    (cd "$work" && env -i HOME="$HOME" USER="${USER:-}" LOGNAME="${LOGNAME:-}" SHELL=/bin/bash \
        PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR="${TMPDIR:-/tmp}" LANG="${LANG:-en_US.UTF-8}" \
        CLAUDE_CONFIG_DIR="$cfg" DISABLE_AUTOUPDATER=1 "$cli" "$@")
}

# A capture in the scratch directory, redacted into OUT; only the redaction's report is kept beside it.
redact() {   # RAW N
    (cd "$root" && python3 -m tools.redact_trial < "$1" > "$out/clean-$2") 2> "$out/redacted-$2"
    rm -f "$1"
}

mkdir "$out"
date -u +%Y-%m-%dT%H:%M:%SZ > "$out/ran_at"

# 1. The version, which must be the pin.
code1=0
run_cli --version > "$scratch/raw-1" 2>&1 || code1=$?
version=$(sed -n 1p "$scratch/raw-1" | cut -d' ' -f1)
redact "$scratch/raw-1" 1
if [[ "$code1" -ne 0 || "$version" != "$PIN" ]]; then
    echo "trial_p13_cli: the CLI at $cli is version '$version', exit $code1, not $PIN; nothing was asked of the model" >&2
    exit 1
fi

# 2. Whether it is logged in, and how. Python reads the answer and keeps only the named fields.
code2=0
run_cli auth status --json > "$scratch/raw-2" 2>/dev/null || code2=$?
logged_in=$(python3 -I -c '
import json, sys
try:
    said = json.load(open(sys.argv[1]))
except ValueError:
    said = None
import re
kept = {k: said[k] for k in sys.argv[3].split() if isinstance(said, dict) and k in said}
# A kept value is a bool or a code: letters, digits and _ . : - up to 64; an address or prose under a named key is dropped.
kept = {k: v for k, v in kept.items() if isinstance(v, bool) or (isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", v))}
json.dump(kept, open(sys.argv[2], "w"), indent=2)
status = kept.get("loggedIn")
print("yes" if status is True else "no" if status is False else "unknown")' "$scratch/raw-2" "$scratch/kept-2" "$KEPT_STATUS")
rm -f "$scratch/raw-2"
redact "$scratch/kept-2" 2
if [[ "$code2" -ne 0 || "$logged_in" != yes ]]; then
    python3 -I -c '
import json, sys
json.dump({"exit": None, "version": {"pinned": sys.argv[2], "before": sys.argv[3]},
           "login": {"exit": int(sys.argv[4]), "status": sys.argv[5]}, "every_part_holds": False},
          open(sys.argv[1], "w"), indent=2)' "$out/checked.json" "$PIN" "$version" "$code2" "$logged_in"
    echo "trial_p13_cli: the CLI's login under CONFIG_DIR is '$logged_in', exit $code2, not yes; nothing was asked of the model (the runbook, step 1)" >&2
    exit 1
fi

# 3. The Task, headless, with the schema.
code3=0
# shellcheck disable=SC2086  # OPTIONS is split into its words on purpose
run_cli -p "$TASK" --json-schema "$SCHEMA" $OPTIONS --tools "$TOOLS" > "$scratch/raw-3" 2> "$scratch/raw-3.err" || code3=$?
code_after=0
said_after=$(run_cli --version 2>/dev/null) || code_after=$?    # its exit is read, as the first --version's is
after=$(printf '%s\n' "$said_after" | sed -n 1p | cut -d' ' -f1)

# The answer, kept by allowlist: only the fields KEPT_RESULT names, the model's text and every other field dropped
# and counted; its structured output validated, and kept only if it validates.
(cd "$root" && python3 -I -c '
import json, sys
sys.path.insert(0, sys.argv[1])
from tools.jsonschema_lite import validate

raw, kept, checked, schema = sys.argv[2], sys.argv[3], sys.argv[4], json.loads(sys.argv[5])
code, pin, version, after, logged_in = int(sys.argv[6]), sys.argv[7], sys.argv[8], sys.argv[9], sys.argv[10]
allowed, string_keys = sys.argv[11].split(), sys.argv[13].split()
text = open(raw).read()
try:
    said = json.loads(text)
except ValueError:
    said = None
if isinstance(said, list):    # a stream of messages: the last result is the answer
    results = [m for m in said if isinstance(m, dict) and m.get("type") == "result"]
    said = results[-1] if results else None
taken, found, source, errors = [], None, None, None
if isinstance(said, dict):
    prose = said.get("result")
    if prose is not None:
        taken.append({"field": "result", "characters": len(prose) if isinstance(prose, str) else None})
    if "structured_output" in said:
        found, source = said["structured_output"], "structured_output"
    elif isinstance(prose, str):
        try:
            found, source = json.loads(prose), "result"
        except ValueError:
            pass
    dropped = sorted(k for k in said if k not in allowed and k != "result")
    if dropped:
        taken.append({"field": "every field KEPT_RESULT does not name", "fields": len(dropped)})
    said = {k: said[k] for k in allowed if k in said}
    DROP = object()
    import re
    def prose(text):             # the CLI answers in numbers and codes: anything else is prose
        return not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", text)
    def counts(value, where, key=None):    # a value, or a key with what is under it, that is prose or under no named key is dropped and counted
        if isinstance(value, dict):
            kept_here = [(k, DROP if prose(k) else counts(v, where + "." + k, k)) for k, v in value.items()]
            taken.extend({"field": where + ".<key>", "characters": len(k)} for k, v in kept_here if v is DROP and prose(k))
            return {k: v for k, v in kept_here if v is not DROP}
        if isinstance(value, list):    # an item of a list is under no key of its own: a string there is never a code
            return [v for v in (counts(v, where + "[]", None) for v in value) if v is not DROP]
        if isinstance(value, str) and (prose(value) or key not in string_keys):
            taken.append({"field": where, "characters": len(value)})
            return DROP
        if isinstance(value, float) and not value == value:    # a number that is not one
            return DROP
        return value
    # The refused tools are kept as names, and the structured output is set aside, before the walk, so that the record
    # of what was taken out names nothing that is kept.
    denials = said.get("permission_denials")
    if isinstance(denials, list) and denials:
        said["permission_denials"] = [{"tool_name": d.get("tool_name")} if isinstance(d, dict) else None
                                      for d in denials]
        taken.append({"field": "permission_denials[].tool_input", "items": len(denials)})
    said.pop("structured_output", None)
    said = counts(said, "$")
    if source is not None:
        errors = sorted({e.split(":")[0] for e in validate(found, schema)})
        if errors:
            taken.append({"field": "structured_output", "why": "it did not validate, so it may hold prose"})
        else:
            said["structured_output"] = found
    json.dump(said, open(kept, "w"), indent=2)
else:
    open(kept, "w").write("the answer was not one JSON object; its text is not kept\n")
    taken.append({"field": "$", "characters": len(text)})
usage = said.get("usage") if isinstance(said, dict) else None
counts = isinstance(usage, dict) and all(isinstance(usage.get(k), int) and not isinstance(usage.get(k), bool)
                                         for k in ("input_tokens", "output_tokens"))
err = open(sys.argv[14]).read()
parts = {
    "exit": code,
    "stderr": {"lines": err.count("\n"), "characters": len(err)},
    "version": {"pinned": pin, "before": version, "after": after, "after_exit": int(sys.argv[15]),
                "held": version == pin == after and int(sys.argv[15]) == 0},
    "logged_in": logged_in,
    "login": {"exit": int(sys.argv[12]), "status": logged_in},
    "is_error": said.get("is_error") if isinstance(said, dict) else None,
    "subtype": said.get("subtype") if isinstance(said, dict) else None,
    "structured_output": {"from": source, "validates": errors == [], "failing_paths": errors},
    "usage": {"counts": counts, "fields": sorted(usage) if isinstance(usage, dict) else None,
              "total_cost_usd": isinstance(said, dict) and "total_cost_usd" in said},
    "model_text_removed": taken,
}
parts["every_part_holds"] = (code == 0 and parts["version"]["held"] and logged_in == "yes" and errors == []
                             and counts and parts["is_error"] is False)
json.dump(parts, open(checked, "w"), indent=2)
' "$root" "$scratch/raw-3" "$scratch/kept-3" "$scratch/checked" "$SCHEMA" "$code3" "$PIN" "$version" "${after:-}" "$logged_in" "$KEPT_RESULT" "$code2" "$STRING_KEYS" "$scratch/raw-3.err" "$code_after")
rm -f "$scratch/raw-3" "$scratch/raw-3.err"
redact "$scratch/kept-3" 3
(cd "$root" && python3 -m tools.redact_trial < "$scratch/checked" > "$out/checked.json") 2> /dev/null ||
    { echo "trial_p13_cli: the redaction of checked.json failed" >&2; exit 1; }

# What was asked: the command lines, the Task and the schema. No credential, path or address is in it.
python3 -I -c '
import json, sys
task, schema, options, pin = sys.argv[2], json.loads(sys.argv[3]), sys.argv[4], sys.argv[5]
env = {"CLAUDE_CONFIG_DIR": "a configuration directory of its own, logged in to the Maintainer\x27s own subscription (decision 0033)",
       "DISABLE_AUTOUPDATER": "1", "passed_on": ["HOME", "USER", "LOGNAME", "PATH", "TMPDIR", "LANG"],
       "SHELL": "/bin/bash", "nothing_else": True}
where = "an empty scratch directory outside the repo"
asked = [
    {"n": 1, "via": "cli", "call": "claude --version", "env": env, "cwd": where},
    {"n": 2, "via": "cli", "call": "claude auth status --json", "env": env, "cwd": where,
     "kept": sys.argv[6].split()},
    {"n": 3, "via": "cli", "call": "claude -p TASK --json-schema SCHEMA " + options + " --tools \"\"", "env": env,
     "cwd": where, "pinned": pin, "prompt": task, "json_schema": schema, "kept": sys.argv[7].split()},
]
json.dump(asked, open(sys.argv[1], "w"), indent=2)' "$out/requests.json" "$TASK" "$SCHEMA" "$OPTIONS" "$PIN" "$KEPT_STATUS" "$KEPT_RESULT"

held=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1])).get("every_part_holds") is True)' "$out/checked.json")
echo "trial_p13_cli: CLI exit $code3; version $version, after $after; logged in: $logged_in; every part holds: $held"
for n in 1 2 3; do
    sed "s|^|clean-$n: |" "$out/redacted-$n"
done
echo "Done. Give a session this directory; it holds no credential and none of the model's text:"
echo "  $out"
[[ "$held" = True ]] || exit 1
