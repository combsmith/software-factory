#!/usr/bin/env bash
# What the trial-author App writes for a platform trial (design, section 6: P-1, P-7, P-24, P-28),
# at the Maintainer's own terminal and nowhere else. No session and no workflow runs this.
#
#   bash tools/trial_as_app.sh open KEY REPO BRANCH FILE   # a branch from the default branch, one commit, a pull request
#   bash tools/trial_as_app.sh push KEY REPO PR FILE       # one commit to the head of an open pull request
#
# KEY is the path of the App's private key. Only openssl opens it, to sign; this script never
# reads, prints or copies what it holds. FILE is a new file's path in REPO; the commit adds it.
# The script mints one installation token, which no command line ever holds, revokes it before it
# exits, on a failure too, and keeps in a new scratch directory outside this repo only what
# tools/redact_trial.py let through. It prints that directory, the pull request and its head.
# Run it from anywhere in a checkout of this repo, with bash 3.2 or later, curl, openssl, gh, python3.
set -euo pipefail
set +x
unset GH_DEBUG DEBUG CURL_HOME
# gh sends GH_TOKEN to the host GH_HOST names, or its configured default: pin it to the host the curl calls use.
export GH_HOST=github.com GH_NO_UPDATE_NOTIFIER=1 GH_PROMPT_DISABLED=1

APP_ID=5363178
APP=combsmith-sf-trial-author
API=https://api.github.com
VERSION=2022-11-28
ACCEPT=application/vnd.github+json

usage() {
    echo "usage: bash tools/trial_as_app.sh open KEY OWNER/REPO BRANCH FILE" >&2
    echo "       bash tools/trial_as_app.sh push KEY OWNER/REPO PR FILE" >&2
    exit 2
}
[ "$#" -eq 5 ] || usage
action=$1 key=$2 repo=$3 target=$4 file=$5
case "$action" in open|push) ;; *) usage ;; esac
case "$repo" in */*/*|/*|*/) usage ;; */*) ;; *) usage ;; esac
case "$file" in ""|/*|*..*|*" "*) echo "FILE is a new path inside REPO, such as trial-notes/p-1.md" >&2; exit 2 ;; esac
if [ "$action" = push ]; then
    case "$target" in ""|*[!0-9]*) usage ;; esac
else
    case "$target" in ""|-*|*" "*|*..*) usage ;; esac
fi
[ -f "$key" ] && [ -r "$key" ] || { echo "no readable file at the key's path" >&2; exit 2; }
for tool in curl openssl gh python3; do
    command -v "$tool" >/dev/null || { echo "$tool is needed" >&2; exit 2; }
done

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
[ -f "$root/tools/redact_trial.py" ] || { echo "run the copy of this script in a checkout of software-factory" >&2; exit 2; }
out=$(cd "$(mktemp -d)" && pwd -P)
case "$out/" in "$root"/*) echo "the scratch directory is inside the repo" >&2; exit 2 ;; esac

jwt="" token="" n=0 id="" raw=""

# The value at a dotted path of the JSON body of a redacted capture.
value() {
    python3 -I -c '
import json, sys
text = open(sys.argv[1]).read()
head, gap, body = text.partition("\n\n")
data = json.loads(body if gap else text)
for key in sys.argv[2].split("."):
    data = data[int(key)] if isinstance(data, list) else data[key]
print(data)' "$1" "$2"
}

# A JSON object of the string arguments given as name=value.
object() {
    python3 -I -c '
import json, sys
print(json.dumps(dict(arg.split("=", 1) for arg in sys.argv[1:])))' "$@"
}

# The next exchange: what was asked, written down here, never the credential that asked it.
record() {   # CALL WHO BODY
    n=$((n + 1))
    id=$(printf '%02d' "$n")
    raw="$out/$id.raw"
    python3 -I -c '
import json, sys
call, who, body, version, accept, path = sys.argv[1:7]
json.dump({"as": {"kind": "app", "name": who}, "via": "rest", "call": call,
           "headers": {"accept": accept, "x-github-api-version": version, "authorization": "not recorded"},
           "body": json.loads(body) if body else None}, open(path, "w"), indent=2)' \
        "$1" "$2" "$3" "$VERSION" "$ACCEPT" "$out/$id.request.json"
}

# A raw capture, redacted beside it and then deleted. Only the redaction's report is printed.
redact() {   # RAW
    (cd "$root" && python3 -m tools.redact_trial < "$1" 2>&1 > "${1%.raw}.clean") | sed "s|^|$(basename "${1%.raw}"): |"
    rm -f "$1"
}

# As the App itself, by its JWT: the header goes to curl on its standard input, never as an argument.
as_app() {   # METHOD PATH
    record "$1 /$2" "$APP, by its JWT" ""
    printf 'Authorization: Bearer %s\n' "$jwt" |
        curl -q -sS -i --fail-with-body -X "$1" -H @- -H "Accept: $ACCEPT" \
            -H "X-GitHub-Api-Version: $VERSION" "$API/$2" | tr -d '\r' > "$raw"
    redact "$raw"
}

# As the App's installation: gh reads the token from its environment, never from an argument.
as_installation() {   # METHOD PATH [BODY]
    record "$1 /$2" "${APP}[bot], by an installation token" "${3:-}"
    if [ -n "${3:-}" ]; then
        printf '%s' "$3" | GH_TOKEN="$token" gh api --include -X "$1" -H "Accept: $ACCEPT" \
            -H "X-GitHub-Api-Version: $VERSION" "$2" --input - | tr -d '\r' > "$raw"
    else
        GH_TOKEN="$token" gh api --include -X "$1" -H "Accept: $ACCEPT" \
            -H "X-GitHub-Api-Version: $VERSION" "$2" | tr -d '\r' > "$raw"
    fi
    redact "$raw"
}

# Revoke the token first, whatever happened; then redact what is left and gather the exchanges.
finish() {
    status=$?
    trap - EXIT INT TERM
    set +e
    if [ -n "$token" ]; then
        as_installation DELETE installation/token
        [ "$(sed -n 1p "$out/$id.clean" 2>/dev/null | cut -d' ' -f2)" = 204 ] ||
            { echo "THE TOKEN WAS NOT REVOKED: it lapses within the hour; say so to the session" >&2; status=1; }
    fi
    token="" jwt=""
    unset token jwt
    for left in "$out"/*.raw; do
        [ -e "$left" ] && redact "$left"
    done
    python3 -I -c '
import json, pathlib, sys
out, exchanges = pathlib.Path(sys.argv[1]), []
for asked in sorted(p for p in out.iterdir() if p.name.endswith(".request.json")):
    clean = out / asked.name.replace(".request.json", ".clean")
    text = clean.read_text() if clean.exists() else ""
    head, gap, body = text.partition("\n\n")
    lines = head.splitlines() if gap else []
    body = body if gap else text
    status = lines[0].split()[1] if lines and len(lines[0].split()) > 1 else None
    headers = {}
    for line in lines[1:]:
        name, _, said = line.partition(":")
        headers[name.strip().lower()] = said.strip()
    try:
        body = json.loads(body) if body.strip() else None
    except ValueError:
        pass
    exchanges.append({"request": json.load(open(str(asked))),
                      "response": {"status": int(status) if status and status.isdigit() else status,
                                   "headers": headers, "body": body}})
json.dump({"exchanges": exchanges}, open(str(out / "exchanges.unchecked.json"), "w"), indent=2)' "$out"
    redact_json="$out/exchanges.unchecked.json"
    (cd "$root" && python3 -m tools.redact_trial < "$redact_json" > "$out/exchanges.json") 2> /dev/null ||
        { echo "trial_as_app: the redaction of the exchanges failed" >&2; exit 1; }
    rm -f "$redact_json"
    echo "Done, status $status. Give the session this directory; it reads only exchanges.json and the .clean files:"
    echo "  $out"
    exit "$status"
}
trap finish EXIT
trap 'exit 130' INT TERM

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '=\n'; }

# The App's JWT, ten minutes at most, signed by openssl from the key's path.
now=$(date +%s)
header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
claims=$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' "$((now - 60))" "$((now + 540))" "$APP_ID" | b64url)
signature=$(printf '%s.%s' "$header" "$claims" | openssl dgst -sha256 -sign "$key" -binary | b64url)
jwt="$header.$claims.$signature"
unset header claims signature

as_app GET "repos/$repo/installation"
installation=$(value "$out/$id.clean" id)

# The token, minted: python keeps it apart from what is written, and hands it to this shell alone.
record "POST /app/installations/$installation/access_tokens" "$APP, by its JWT" ""
token=$(printf 'Authorization: Bearer %s\n' "$jwt" |
    curl -q -sS -i --fail-with-body -X POST -H @- -H "Accept: $ACCEPT" -H "X-GitHub-Api-Version: $VERSION" \
        "$API/app/installations/$installation/access_tokens" |
    python3 -I -c '
import json, sys
text = sys.stdin.read().replace("\r\n", "\n")
# The last blank line ends the headers: a proxy prints its own "Connection established" block before the one
# from GitHub, and a JSON body holds no blank line.
head, gap, body = text.rpartition("\n\n")
try:
    data = json.loads(body)
except ValueError:
    data = None
token = data.pop("token", "") if isinstance(data, dict) else ""
with open(sys.argv[1], "w") as kept:
    kept.write(head + "\n\n" + (json.dumps(data) if data is not None else body))
sys.stdout.write(token)' "$raw")
redact "$raw"
jwt=""
[ -n "$token" ] || { echo "no installation token was read: if one was minted it was not revoked, and expires within an hour" >&2; exit 1; }

as_installation GET installation/repositories

content=$(printf 'A platform trial: this file was added by the trial-author App, through %s.\n' "$action" | openssl base64 -A)
if [ "$action" = open ]; then
    branch=$target
    as_installation GET "repos/$repo"
    base=$(value "$out/$id.clean" default_branch)
    as_installation GET "repos/$repo/git/ref/heads/$base"
    sha=$(value "$out/$id.clean" object.sha)
    as_installation POST "repos/$repo/git/refs" "$(object "ref=refs/heads/$branch" "sha=$sha")"
    as_installation PUT "repos/$repo/contents/$file" \
        "$(object "message=Trial: $file, added by the trial-author App" "content=$content" "branch=$branch")"
    as_installation POST "repos/$repo/pulls" "$(object "title=Trial: $branch, opened by the trial-author App" \
        "head=$branch" "base=$base" "body=A platform trial. It is approved by the machine user alone, and read.")"
    pr=$(value "$out/$id.clean" number)
else
    pr=$target
    as_installation GET "repos/$repo/pulls/$pr"
    [ "$(value "$out/$id.clean" head.repo.full_name)" = "$repo" ] || { echo "the pull request's head is not in $repo" >&2; exit 1; }
    [ "$(value "$out/$id.clean" state)" = open ] || { echo "pull request $pr is not open" >&2; exit 1; }
    branch=$(value "$out/$id.clean" head.ref)
    as_installation PUT "repos/$repo/contents/$file" \
        "$(object "message=Trial: $file, pushed by the trial-author App" "content=$content" "branch=$branch")"
fi
as_installation GET "repos/$repo/pulls/$pr"
echo "Pull request $pr, branch $branch, head $(value "$out/$id.clean" head.sha)"

as_installation DELETE installation/token
[ "$(sed -n 1p "$out/$id.clean" | cut -d' ' -f2)" = 204 ] || { echo "the revocation did not answer 204" >&2; exit 1; }
token=""
