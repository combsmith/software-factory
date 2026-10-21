#!/bin/sh
# Trial P-4 (combsmith/software-factory#187, design section 6): can an installation token be minted with a subset of
# the App's permissions and repos, and is it held to them?
#
#   tools/trial_p4_narrow.sh OUT KEY OWNER/REPO OTHER_OWNER/REPO
#
# The Maintainer runs it at his own terminal, from anywhere; no session runs it, since it mints a credential. OUT is a
# directory that does not exist yet, outside this repo. KEY is the path of the trial-author App's private key file,
# which only openssl reads. OWNER/REPO is a repo the App's installation reaches; OTHER_OWNER/REPO is one it does not
# reach. Needs curl, openssl and python3; no gh login is used.
#
# It signs a JWT with the App's key, reads the installation of OWNER/REPO, mints a token for it narrowed to the
# permission contents: read and to the one repository REPO, and with that token makes three reads, in order:
#   1. GET /repos/OWNER/REPO/contents/, the root listing, which the subset permits and every non-empty repo has;
#   2. PUT /repos/OWNER/REPO/contents/p4/trial.md, a write the subset does not permit;
#   3. GET /repos/OTHER_OWNER/OTHER_REPO/contents/, the root listing of a repository the token does not name. Where
#      that repository is public, any token reads it, so its answer shows what a repository subset does to a read.
# Then it revokes the token and records the revocation's status. The mint's answer is read by python, which keeps
# everything but the token itself (the permissions and the repository selection are what the trial is about) and
# hands the token to this shell alone. A token or a JWT is held in a shell variable only, reaches curl on its standard
# input, and is never printed, logged or written to a file. Each response is captured in a scratch directory outside
# the repo, redacted there by tools/redact_trial.py, and deleted; OUT receives only the redacted responses (clean-N),
# what was asked (requests.json) and when the run started (ran_at). A session then builds trials/P-4.json from OUT.
#
# A mint that curl fails or GitHub refuses, or a revocation that does not return 204, stops the script with a non-zero
# exit; a read's status, whatever it is, is the trial's answer and is kept. A token that may be live is told to the
# Maintainer.
set -eu
set +x
unset CURL_HOME

if [ "$#" -ne 4 ]; then
    echo "usage: tools/trial_p4_narrow.sh OUT KEY OWNER/REPO OTHER_OWNER/REPO" >&2
    exit 2
fi
root=$(cd "$(dirname "$0")/.." && pwd -P)
if [ -e "$1" ] || [ -L "$1" ]; then
    echo "trial_p4_narrow: $1 exists; name a new directory" >&2
    exit 2
fi
if ! parent=$(cd "$(dirname -- "$1")" 2>/dev/null && pwd -P); then
    echo "trial_p4_narrow: the directory that would hold $1 does not exist; make it first" >&2
    exit 2
fi
out=$parent/$(basename -- "$1")
case "$out/" in "$root"/*)
    echo "trial_p4_narrow: $out is inside the repo; name a directory outside it" >&2
    exit 2 ;;
esac
key=$2
if [ ! -r "$key" ]; then
    echo "trial_p4_narrow: cannot read the key file $key" >&2
    exit 2
fi
for repo in "$3" "$4"; do
    if ! printf '%s\n' "$repo" | grep -Eq '^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$'; then
        echo "trial_p4_narrow: $repo is not OWNER/REPO" >&2
        exit 2
    fi
done
if [ "$3" = "$4" ]; then
    echo "trial_p4_narrow: the two repos must differ" >&2
    exit 2
fi
repo=$3 other=$4

API=https://api.github.com
VERSION="X-GitHub-Api-Version: 2022-11-28"
ACCEPT="Accept: application/vnd.github+json"
JSON="Content-Type: application/json"
scratch=$(mktemp -d)
case "$scratch/" in "$root"/*)
    rmdir "$scratch"
    echo "trial_p4_narrow: the scratch directory $scratch is inside the repo; set TMPDIR outside it" >&2
    exit 2 ;;
esac
token=""

revoke() {
    printf 'Authorization: Bearer %s\n' "$token" | curl -q -sS -o /dev/null -w '%{http_code}' -X DELETE -H @- \
        -H "$ACCEPT" -H "$VERSION" "$API/installation/token"
}

unrevoked() {
    echo "trial_p4_narrow: revoking the token returned $1, not 204. The token may be live for up to an hour;" \
        "the Maintainer must revoke it by hand." >&2
}

finish() {
    if [ -n "$token" ]; then
        last=$(revoke || true)
        echo "trial_p4_narrow: stopped with a token live; revoking it returned $last" >&2
        [ "$last" = 204 ] || unrevoked "$last"
        token=""
    fi
    rm -rf "$scratch"
}
trap finish EXIT
trap 'exit 1' HUP INT TERM

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

# The App's id, from the data the trial-author App is not: the id P-1's and P-7's fixtures record for it.
app_id=$(cd "$root" && python3 -I -c '
import json
fixture = json.load(open("trials/P-1.json"))
first = fixture["exchanges"][0]
assert first["request"]["call"].endswith("/installation"), first["request"]["call"]
print(first["response"]["body"]["app_id"])')

mkdir -p "$out"
date -u +%Y-%m-%dT%H:%M:%SZ > "$out/ran_at"
n=0
asked=""

# One read with the token, captured with its headers, redacted into OUT as clean-N. Its status is the answer, kept
# whatever it is.
with_token() {   # METHOD PATH [BODY_FILE]
    n=$((n + 1))
    read_ok=1
    if [ -n "${3:-}" ]; then
        printf 'Authorization: Bearer %s\n' "$token" | curl -q -sS -i -X "$1" -H @- -H "$ACCEPT" -H "$VERSION" -H "$JSON" \
            --data-binary "@$3" "$API/$2" > "$scratch/crlf-$n" || read_ok=0
    else
        printf 'Authorization: Bearer %s\n' "$token" | curl -q -sS -i -X "$1" -H @- -H "$ACCEPT" -H "$VERSION" \
            "$API/$2" > "$scratch/crlf-$n" || read_ok=0
    fi
    tr -d '\r' < "$scratch/crlf-$n" > "$scratch/raw-$n"
    rm -f "$scratch/crlf-$n"
    if [ "$read_ok" = 0 ]; then
        rm -f "$scratch/raw-$n"
        echo "trial_p4_narrow: read $n ($1 /$2) failed in curl; nothing of it is kept." >&2
        exit 1
    fi
    (cd "$root" && python3 -m tools.redact_trial "$scratch/raw-$n" "$out/clean-$n") > "$out/redacted-$n"
    rm -f "$scratch/raw-$n"
    status=$(sed -n '1s/^HTTP\/[0-9.]* \([0-9][0-9]*\).*/\1/p' "$out/clean-$n")
    body=null
    [ -n "${3:-}" ] && body=$(cat "$3")
    asked="$asked{\"n\": $n, \"call\": \"$1 /$2\", \"body\": $body, \"status\": \"$status\"},"
    echo "read $n: $1 /$2 answered $status"
}

# The JWT, ten minutes at most, signed by openssl from the key's path; the installation of OWNER/REPO read with it.
now=$(date +%s)
header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
claims=$(printf '{"iat":%d,"exp":%d,"iss":%d}' $((now - 60)) $((now + 540)) "$app_id" | b64url)
signature=$(printf '%s.%s' "$header" "$claims" | openssl dgst -sha256 -sign "$key" -binary | b64url)
jwt="$header.$claims.$signature"
n=1
printf 'Authorization: Bearer %s\n' "$jwt" | curl -q -sS -i -H @- -H "$ACCEPT" -H "$VERSION" \
    "$API/repos/$repo/installation" | tr -d '\r' > "$scratch/raw-1"
(cd "$root" && python3 -m tools.redact_trial "$scratch/raw-1" "$out/clean-1") > "$out/redacted-1"
rm -f "$scratch/raw-1"
installation=$(sed -n '/^{/,$p' "$out/clean-1" | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["id"])')
asked="{\"n\": 1, \"call\": \"GET /repos/$repo/installation\", \"body\": null, \"status\": \"$(sed -n '1s/^HTTP\/[0-9.]* \([0-9][0-9]*\).*/\1/p' "$out/clean-1")\"},"

# The mint, narrowed: contents read alone, and the one repository. GitHub's answer and its status are held in a
# variable, never a file, since the minted token is in the answer; python keeps the answer without its token.
n=2
printf '{"repositories":["%s"],"permissions":{"contents":"read"}}' "${repo#*/}" > "$scratch/mint.json"
minted=$(printf 'Authorization: Bearer %s\n' "$jwt" | curl -q -sS -w '\n%{http_code}' -X POST -H @- \
    -H "$ACCEPT" -H "$VERSION" -H "$JSON" --data-binary "@$scratch/mint.json" \
    "$API/app/installations/$installation/access_tokens" || true)
jwt=""
rm -f "$scratch/mint.json"
minted_status=$(printf '%s\n' "$minted" | tail -n 1)
token=$(printf '%s\n' "$minted" | sed '$d' | tr -d '\r' | python3 -I -c '
import json, sys
text = sys.stdin.read()
try:
    data = json.loads(text)
except ValueError:
    data = None
token = data.pop("token", "") if isinstance(data, dict) else ""
with open(sys.argv[1], "w") as kept:
    kept.write("HTTP/2 %s\n\n%s\n" % (sys.argv[2], json.dumps(data) if data is not None else "(an answer that is not JSON, not kept)"))
sys.stdout.write(token)' "$scratch/raw-2" "${minted_status:-000}" 2>/dev/null || true)
minted=""
(cd "$root" && python3 -m tools.redact_trial "$scratch/raw-2" "$out/clean-2") > "$out/redacted-2"
rm -f "$scratch/raw-2"
asked="$asked{\"n\": 2, \"call\": \"POST /app/installations/$installation/access_tokens\", \"body\": {\"repositories\": [\"${repo#*/}\"], \"permissions\": {\"contents\": \"read\"}}, \"status\": \"${minted_status:-none}\"},"
if [ "$minted_status" != 201 ] || [ -z "$token" ]; then
    token=""
    echo "trial_p4_narrow: no token was read from the mint (status ${minted_status:-none}); if one was minted it was not" \
        "revoked, and expires within an hour. GitHub's answer, redacted, is $out/clean-2." >&2
    exit 1
fi
echo "minted, narrowed, status 201"

# The three reads.
with_token GET "repos/$repo/contents/"
printf '{"message":"Trial P-4: a write the token does not permit","content":"QSBwbGF0Zm9ybSB0cmlhbC4K"}' > "$scratch/put.json"
with_token PUT "repos/$repo/contents/p4/trial.md" "$scratch/put.json"
rm -f "$scratch/put.json"
with_token GET "repos/$other/contents/"

revoked=$(revoke || true)
if [ "$revoked" != 204 ]; then
    unrevoked "$revoked"
    exit 1
fi
token=""
printf '{"as": "combsmith-sf-trial-author", "app_id": %d, "installation": %d, "narrowed_to": {"repositories": ["%s"], "permissions": {"contents": "read"}}, "revoked": "%s", "reads": [%s]}\n' \
    "$app_id" "$installation" "${repo#*/}" "$revoked" "${asked%,}" > "$out/requests.json"
echo "Done. Hand $out to a session; it holds no credential. The token was revoked with status $revoked."
