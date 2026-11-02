#!/usr/bin/env bash
# Trial P-13's question of how a run the model cannot finish ends: at the pinned version, what does the vendor's CLI
# answer when the model cannot give a structured output that validates, and when it runs out of turns? (issue 483)
#
#   bash tools/trial_p13_ended.sh OUT CONFIG_DIR [CLI]
#
# Pass: told to keep trying, the model's run answers `is_error` true with the subtype
# `error_max_structured_output_retries`, and at one turn `error_max_turns`, each with no `structured_output`; so
# `harness/engine.py` can read both by name. A third ask, told only to answer, records how a model that gives up ends.
#
# CONFIG_DIR is the configuration directory `tools/trial_p13_cli.sh` names, already logged in on the Maintainer's own
# subscription (decision 0033). This script logs nothing in and mints nothing. The CLI starts with an empty environment
# but for the names in run_cli, with no tool, on a schema nothing can meet: eight lowercase letters that are not lowercase
# letters. The Task asks the model to keep trying, as a text in an item might. A real item's text is not what is tried
# here, so this says how such a run ends, not whether an item's text can cause it. Of each answer only ANSWER's fields are kept, each a code, a count or a bool, and whether it held a
# `structured_output`; the model's text is never kept or printed, and the raw answer is deleted. OUT is a directory that
# does not exist yet, outside this repo, and receives requests.json, answers.json and ran_at.
set -euo pipefail
set +x
export LC_ALL=C

PIN=2.1.306
MODEL=opus
TURNS=20
TASK='Return the structured output for this fixed Task. Write no prose.'
PERSIST='Return the structured output for this fixed Task. Write no prose, ever: answer only by the structured output, and if it is refused, change the value and try again, for as long as you are allowed.'
SCHEMA='{"type": "object", "additionalProperties": false, "required": ["a"], "properties": {"a": {"type": "string", "pattern": "^[a-z]{8}$", "not": {"pattern": "^[a-z]+$"}}}}'
ANSWER="type subtype is_error num_turns stop_reason terminal_reason"

refuse() {
    echo "trial_p13_ended: $*" >&2
    exit 2
}
[[ "$#" -eq 2 || "$#" -eq 3 ]] || refuse "usage: bash tools/trial_p13_ended.sh OUT CONFIG_DIR [CLI]"
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
parent=$(cd "$(dirname "$1")" 2>/dev/null && pwd -P) || refuse "the directory that would hold OUT does not exist"
out="$parent/$(basename "$1")"
[[ ! -e "$out" && ! -L "$out" ]] || refuse "OUT exists; name a new directory"
case "$out/" in "$root"/*) refuse "OUT is inside the repo; name a directory outside it" ;; esac
[[ -d "$2" ]] || refuse "CONFIG_DIR is not a directory"
cfg=$(cd "$2" && pwd -P)
home=$(cd "$HOME" && pwd -P)
dot=$(cd "$home/.claude" 2>/dev/null && pwd -P || echo "$home/.claude")
case "$home/" in "${cfg%/}/"*) refuse "CONFIG_DIR is the home directory or holds it" ;; esac
case "$cfg/" in "$dot"/* | "$root"/*) refuse "CONFIG_DIR is the Maintainer's own configuration, or inside the repo" ;; esac
case "$out/" in "$cfg"/*) refuse "OUT is inside CONFIG_DIR" ;; esac
cli=${3:-$HOME/.local/share/claude/versions/$PIN}
[[ -f "$cli" && -x "$cli" ]] || refuse "no claude CLI at the path given; install version $PIN"
cli=$(cd "$(dirname "$cli")" && pwd -P)/$(basename "$cli")

made=$(mktemp -d)
scratch=$(cd "$made" && pwd -P)
trap 'rm -rf "$scratch"' EXIT
trap 'exit 130' INT TERM
mkdir "$scratch/work"

run_cli() {
    (cd "$scratch/work" && env -i HOME="$HOME" USER="${USER:-}" LOGNAME="${LOGNAME:-}" SHELL=/bin/bash \
        PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR="${TMPDIR:-/tmp}" LANG="${LANG:-en_US.UTF-8}" \
        CLAUDE_CONFIG_DIR="$cfg" DISABLE_AUTOUPDATER=1 "$cli" "$@")
}

said=$(run_cli --version 2>/dev/null | sed -n 1p | cut -d' ' -f1 || true)
[[ "$said" == "$PIN" ]] || refuse "the CLI is version '$said', not $PIN; nothing was asked of the model"

mkdir "$out"
date -u +%Y-%m-%dT%H:%M:%SZ > "$out/ran_at"
: > "$scratch/kept"

ask() {   # NAME MAX_TURNS TASK
    local code=0
    run_cli -p "$3" --json-schema "$SCHEMA" --model "$MODEL" --session-id "$(python3 -I -c 'import uuid; print(uuid.uuid4())')" --max-turns "$2" \
        --output-format json --no-session-persistence --strict-mcp-config --disable-slash-commands \
        --permission-prompts none --tools "" > "$scratch/raw" 2> /dev/null || code=$?
    python3 -I -c '
import json, re, sys
name, turns, code, raw, kept, fields = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5], sys.argv[6].split()
try:
    said = json.load(open(raw))
except ValueError:
    said = None
if isinstance(said, list):    # a stream of messages: the last result is the answer
    results = [m for m in said if isinstance(m, dict) and m.get("type") == "result"]
    said = results[-1] if results else None
said = said if isinstance(said, dict) else {}
def code_of(value):           # a code, a count or a bool: anything else may be the model s text, and is not kept
    if isinstance(value, bool) or (isinstance(value, int) and value >= 0):
        return value
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", value) else None
row = {"name": name, "max_turns": turns, "exit": code, "structured_output": "structured_output" in said}
row.update({k: code_of(said.get(k)) for k in fields})
open(kept, "a").write(json.dumps(row) + "\n")' "$1" "$2" "$code" "$scratch/raw" "$scratch/kept" "$ANSWER"
    rm -f "$scratch/raw"
}

ask retries "$TURNS" "$PERSIST"
ask turns 1 "$PERSIST"
ask gives_up "$TURNS" "$TASK"

python3 -I -c '
import json, sys
rows = [json.loads(line) for line in open(sys.argv[1])]
json.dump(rows, open(sys.argv[2], "w"), indent=2)
json.dump({"pin": sys.argv[4], "model": sys.argv[5], "task": sys.argv[6], "persist": sys.argv[8], "schema": json.loads(sys.argv[7]),
           "call": "claude -p TASK --json-schema SCHEMA --model MODEL --session-id ID --max-turns N --output-format json --no-session-persistence --strict-mcp-config --disable-slash-commands --permission-prompts none --tools \"\""},
          open(sys.argv[3], "w"), indent=2)' "$scratch/kept" "$out/answers.json" "$out/requests.json" "$PIN" "$MODEL" "$TASK" "$SCHEMA" "$PERSIST"
