"""The identity port: a Role App's installation token for the one repo a Run is about, narrowed to the permissions the
Effects it asks for need (design section 4.9, issue 194's ruling 6, decision 0050).

The App's JWT is signed by `openssl`, since the standard library cannot sign RS256 and the repo installs nothing. The
key reaches `openssl` through a pipe, as `-sign /dev/fd/N`, and is never written to a file; `openssl` runs with an
environment of its own, so no configuration of the job's can reach it. The JWT lives ten minutes at most, its clock a
minute back (as `tools/trial_as_app.sh` signs one). The token is minted for the one repo, with exactly the permissions
the Effects need, each within what the App was granted for that Effect in `config/apps.json`; what GitHub answers is
held to what was asked. The token is held in memory, never written, never logged, never put in an error, and revoked
when `apply` ends.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess

from adapters import github

# The largest key read: an RSA key of 4096 bits is some 3.3 KB as PEM. One larger is no key, and would not fit the
# pipe's buffer, which `openssl` reads only once it starts.
KEY_MOST = 8 * 1024
SKEW = 60           # seconds the JWT's clock is set back, for a clock GitHub's is ahead of
LIFETIME = 540      # seconds the JWT lives from now: under GitHub's ten minutes, with SKEW
LEVELS = ("read", "write")
REPO = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}")
# What `openssl` is run with: the system's own, and no configuration of the job's.
OPENSSL_ENV = {"PATH": "/usr/bin:/bin"}


class Refused(ValueError):
    """No token: the App may not have what is asked, the key cannot sign, or GitHub answered other than was asked. The
    message is a code and names no token, key or JWT."""


class Token:
    """An installation token, held in memory: it says what it is for and never what it is."""
    __slots__ = ("_value", "repo", "permissions")

    def __init__(self, value: str, repo: str, permissions: dict):
        self._value, self.repo, self.permissions = value, repo, dict(permissions)

    def __repr__(self) -> str:
        return "Token(%s, %s)" % (self.repo, sorted(self.permissions.items()))

    __str__ = __repr__

    def reveal(self) -> str:
        """The token itself, for the one transport that sends it."""
        return self._value


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def signed(message: bytes, key: bytes, run=subprocess.run) -> bytes:
    """`message` signed RS256 by `openssl`, the key handed to it through a pipe's descriptor and never a file."""
    if not isinstance(key, bytes) or not key or len(key) > KEY_MOST:
        raise Refused("key_unreadable")
    read, write = os.pipe()
    try:
        left = memoryview(key)
        while left:
            left = left[os.write(write, left):]
        os.close(write)
        write = None
        done = run(["openssl", "dgst", "-sha256", "-sign", "/dev/fd/%d" % read, "-binary"], input=message,
                   capture_output=True, pass_fds=(read,), env=dict(OPENSSL_ENV), timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        raise Refused("key_cannot_sign") from None
    finally:
        os.close(read)
        if write is not None:
            os.close(write)
    if done.returncode != 0 or not done.stdout:
        raise Refused("key_cannot_sign")
    return done.stdout


def jwt(app_id: int, key: bytes, now: int, sign=signed) -> str:
    """The App's JWT: issued a minute back by the clock given, and living LIFETIME seconds from now."""
    if type(app_id) is not int or app_id < 1 or type(now) is not int:
        raise Refused("app_unreadable")
    head = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = b64url(json.dumps({"iat": now - SKEW, "exp": now + LIFETIME, "iss": app_id},
                               separators=(",", ":")).encode())
    return "%s.%s.%s" % (head, claims, b64url(sign(("%s.%s" % (head, claims)).encode(), key)))


def permissions(app: dict, needs: dict, effects) -> dict:
    """The permissions a token needs to write these Effect types: for each, the permission and level its need names in
    `config/apps.json`, and only where the App was granted that permission, at that level or above, for that need. An
    Effect whose need waits, or that the App was not granted, is refused: the token is never wider than the Effects."""
    wanted = {}
    for effect in sorted(set(effects)):
        name = "effect:" + effect
        need = needs.get(name) if isinstance(needs, dict) else None
        if not isinstance(need, dict) or "permission" not in need or need.get("level") not in LEVELS:
            raise Refused("effect_not_grantable")
        grant = app["permissions"].get(need["permission"])
        if (not isinstance(grant, dict) or name not in grant.get("needs", ())
                or LEVELS.index(grant.get("level")) < LEVELS.index(need["level"])):
            raise Refused("effect_not_granted")
        level = wanted.get(need["permission"], "read")
        wanted[need["permission"]] = max(level, need["level"], key=LEVELS.index)
    return wanted


def mint(as_app, app: dict, repo: str, wanted: dict) -> Token:
    """An installation token of `app` for `repo` alone, with exactly `wanted`, asked through `as_app`, a transport that
    carries the App's JWT. GitHub adds `metadata: read` to every token; anything else it answers beyond what was asked,
    another repo, or all of them, is refused."""
    if not isinstance(repo, str) or not REPO.fullmatch(repo) or not wanted:
        raise Refused("token_unreadable")
    found = as_app.send(github.request("GET", "/repos/%s/installation" % repo))
    body = found.get("body")
    if (found.get("status") != 200 or not isinstance(body, dict) or type(body.get("id")) is not int
            or body.get("app_id") != app["app_id"]):
        raise Refused("installation_unreadable")
    asked = {"repositories": [repo.split("/")[1]], "permissions": dict(wanted)}
    given = as_app.send(github.request("POST", "/app/installations/%d/access_tokens" % body["id"], body=asked))
    token = given.get("body")
    if given.get("status") != 201 or not isinstance(token, dict):
        raise Refused("token_refused")
    value = token.get("token")
    named = [r.get("full_name") for r in token.get("repositories", ()) if isinstance(r, dict)]
    if (not isinstance(value, str) or not value or any(c.isspace() for c in value)
            or token.get("permissions") != dict(wanted, metadata="read") or token.get("repository_selection") != "selected"
            or named != [repo]):
        raise Refused("token_not_as_asked")
    return Token(value, repo, wanted)


def revoke(as_token) -> bool:
    """Whether the token `as_token` carries was revoked: GitHub answers 204, and nothing else is a revocation."""
    try:
        return as_token.send(github.request("DELETE", "/installation/token")).get("status") == 204
    except github.Unanswered:
        return False
