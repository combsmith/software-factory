"""The `run` job: one Task, one call of the Engine, one Result (design sections 2.3 and 3.10, issue 194).

    python3 -m harness.run RECORD RUN FACTS TEXTS ROLE FINDINGS OUT

RECORD is the pass record the Run was admitted in, RUN its Run id, FACTS the item's facts as the Run reads them, TEXTS
the texts read for it, each with who wrote it, ROLE the Role's manifest, FINDINGS the Finding ids the Task names, as
JSON files, and OUT a directory that does not exist yet. The job writes OUT/result.json and OUT/result.sha256, and
nothing else of the model: the log carries the digest alone, never a field of the Result, since nothing is handed from
job to job through the log (section 3.10). The CLI is the one at the path the job's environment names, CLAUDE_CLI, and
the credential the one under CLAUDE_CODE_OAUTH_TOKEN. A Run whose Task cannot be built writes no Result and fails.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import uuid

from harness import engine, task

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = "CLAUDE_CLI"


def configuration(root: pathlib.Path = ROOT) -> dict:
    """What the Task and the Engine are told beside the pass record: the Maintainer, the names the Factory's Roles act
    under, and config/harness.json. The Release is the pass record's: one Release, one path (decision 0006)."""
    hooks = json.loads((root / "config" / "hooks.json").read_text())
    apps = json.loads((root / "config" / "apps.json").read_text())
    defaults = json.loads((root / "config" / "defaults.json").read_text())
    roles = sorted({app["name"] + "[bot]" for app in apps["apps"].values()} | set(defaults["required_lenses"]["model"]))
    return {"maintainer": hooks["maintainer"]["login"], "roles": roles, "approver": defaults["approver"], "harness": json.loads((root / "config" / "harness.json").read_text())}


def cli_call(args: list, env: dict, timeout: float):
    """The CLI, started in an empty directory of its own, with nothing on its input and its answer captured."""
    with tempfile.TemporaryDirectory() as empty:
        return subprocess.run(args, env=env, timeout=timeout, cwd=empty, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, check=False)


def job(paths: list, job_env: dict, config: dict, call=None, clock=time.monotonic, session=None) -> str:
    """Build the Task, run the Engine, and write the Result and its digest into OUT. Returns the digest."""
    record, run, facts, texts, role, findings, out = paths
    out = pathlib.Path(out)
    if out.exists():
        raise task.Refused("%s exists; the Result is written into a new directory" % out)

    def read(path):
        return json.loads(pathlib.Path(path).read_text())
    admitted = read(record)
    if not isinstance(admitted, dict) or not isinstance(admitted.get("release"), str):
        raise task.Refused("the pass record is no pass/1")
    config = dict(config, release=admitted["release"])
    the_task = task.build(admitted, run, read(facts), read(texts), read(role), read(findings), config)
    result = engine.run(the_task, job_env.get(CLI, ""), job_env, config["harness"], call or cli_call, clock,
                        session or str(uuid.uuid4()))
    data = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    out.mkdir(parents=True)
    (out / "result.json").write_bytes(data)
    (out / "result.sha256").write_text(digest + "\n")
    return digest


def main(argv: list, job_env: dict) -> int:
    if len(argv) != 7:
        print("usage: python3 -m harness.run RECORD RUN FACTS TEXTS ROLE FINDINGS OUT", file=sys.stderr)
        return 2
    try:
        digest = job(argv, job_env, configuration())
    except (task.Refused, OSError, ValueError) as err:
        print("harness.run: %s" % type(err).__name__, file=sys.stderr)
        return 1
    print("result.json %s" % digest)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], dict(os.environ)))
