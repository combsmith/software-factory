"""The eval job's seal step, for a gate set alone (issue 612, and the Solution Architect's ruling on where its ledger goes).

The ledger `run` left in the scratch, each case's outcome with its Result, is encrypted with `openssl cms`, RSA-OAEP
and AES-256, to each certificate RECIPIENTS pins, into SEALED in the workspace, which the upload after this step takes
whatever the verdicts. The report is given the ciphertext's sha256 beside the ledger's own, salted, so that a check that
holds no key can hold a ledger to the report it backs; a gate set's report without it is unreadable to the gate. The
plaintext is removed once sealed. No key that opens a ledger is in the job or the repo: only the Maintainer's
certificates, each pinned by its sha256 in a protected path, `.github/`, so that changing who can read the ledgers needs
his approval. Nothing here is given a credential.

A development set has no ledger, its report being its cases': the step seals nothing. A gate set with no certificate
pinned, or one that is not the one pinned, fails the run by a code, and nothing is uploaded but what was before.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess

from harness.eval import AGGREGATE, LEDGER, REPORT, Stop, _planned, _write, exit_with, gate_set, within

# Each certificate the ledger is sealed to, a line of its sha256, two spaces and its path, as `sha256sum` writes one.
RECIPIENTS = pathlib.Path(".github") / "ledger-recipients"
CERTS = pathlib.Path("config") / "ledger"
PIN = re.compile(r"([0-9a-f]{64})  (config/ledger/[a-z0-9][a-z0-9-]*\.crt)")
SEALED = "eval-ledger.cms"
OPENSSL = "/usr/bin/openssl"
# What the sealed ledger must show, read back with openssl's own reading of it: one recipient by RSA-OAEP for each
# certificate, and the content by AES-256, so that an openssl that set a padding or a cipher aside is caught.
ENVELOPED = "pkcs7-envelopedData"
RECIPIENT, OAEP, AES = "d.ktri:", "algorithm: rsaesOaep", "algorithm: aes-256-cbc"


def recipients(root: pathlib.Path, place: pathlib.Path) -> list:
    """The paths of the certificates to seal to, each a copy in `place` of the bytes whose sha256 RECIPIENTS pins, so
    that what is sealed to is what was checked. `no_recipient` where none is pinned; `recipient_unreadable` where a line
    is not a pin, names a certificate twice, or one that cannot be read under CERTS; `recipient_changed` where one is not
    the one pinned."""
    try:
        lines = (root / RECIPIENTS).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        raise Stop("no_recipient") from None
    except (OSError, UnicodeDecodeError):
        raise Stop("recipient_unreadable") from None
    if not lines:
        raise Stop("no_recipient")
    pins = [PIN.fullmatch(line) for line in lines]
    if not all(pins) or len({pin.group(2) for pin in pins}) != len(pins):
        raise Stop("recipient_unreadable")
    base, copies = os.path.realpath(str(root / CERTS)), []
    for number, pin in enumerate(pins):
        path = os.path.realpath(str(root / pin.group(2)))
        if not path.startswith(base + os.sep):
            raise Stop("recipient_unreadable")
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            raise Stop("recipient_unreadable") from None
        if hashlib.sha256(data).hexdigest() != pin.group(1):
            raise Stop("recipient_changed")
        copy = os.path.join(str(place), "recipient-%d.crt" % number)
        with open(os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
            out.write(data)
        copies.append(copy)
    return copies


def seal(plain: str, certs: list, out: str, call=subprocess.run) -> bytes:
    """The ledger at `plain` encrypted to each of `certs` into `out`, and its bytes; `ledger_not_sealed` where openssl
    fails, or what it wrote does not read back as an envelope of RSA-OAEP to each and AES-256. Nothing openssl says is
    printed."""
    asked = [OPENSSL, "cms", "-encrypt", "-binary", "-aes256", "-outform", "DER", "-in", plain, "-out", out]
    for cert in certs:
        asked += ["-recip", cert, "-keyopt", "rsa_padding_mode:oaep"]
    quiet = {"env": {"PATH": "/usr/bin:/bin"}, "stdin": subprocess.DEVNULL, "timeout": 60}
    try:
        done = call(asked, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **quiet)
        read = call([OPENSSL, "cms", "-cmsout", "-print", "-inform", "DER", "-in", out], stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, **quiet)
        with open(out, "rb") as f:
            sealed = f.read()
    except (OSError, subprocess.SubprocessError):
        raise Stop("ledger_not_sealed") from None
    shown = read.stdout.decode("utf-8", "replace") if isinstance(read.stdout, bytes) else ""
    if done.returncode != 0 or read.returncode != 0 or ENVELOPED not in shown or \
            not shown.count(RECIPIENT) == shown.count(OAEP) == len(certs) or shown.count(AES) != 1:
        raise Stop("ledger_not_sealed")
    return sealed


def step(env, root, workspace, call=subprocess.run):
    _, found, place = _planned(env, root, workspace)
    if not gate_set(found):
        return "sealed nothing: a development set has no ledger"
    try:
        with open(within(workspace, REPORT), encoding="utf-8") as f:
            written = json.load(f)
    except (OSError, ValueError, RecursionError):
        raise Stop("report_unreadable") from None
    plain = within(place, LEDGER)
    try:
        with open(plain, "rb") as f:
            data = f.read()
    except OSError:
        raise Stop("ledger_unreadable") from None
    # The ledger sealed is the one the report hashed: the report binds it, and the ciphertext's hash binds the seal.
    if not isinstance(written, dict) or written.get("schema") != AGGREGATE or not isinstance(written.get("ledger"), dict) \
            or written["ledger"].get("salted_sha256") != hashlib.sha256(data).hexdigest():
        raise Stop("ledger_not_the_reports")
    certs = recipients(root, place)
    out = os.path.join(os.path.realpath(str(workspace)), SEALED)
    sealed = seal(plain, certs, out, call)
    written["ledger"]["sealed_sha256"] = hashlib.sha256(sealed).hexdigest()
    _write(workspace, REPORT, written)
    os.remove(plain)
    return "sealed the ledger to %d recipients" % len(certs)


if __name__ == "__main__":
    exit_with(step)
