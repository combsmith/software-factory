# Runbook: trial P-13, and any run of `tools/trial_p13_cli.sh`

For "Trial P-13: the model CLI returns validated structured output on the subscription" (issue 15). The trial
ran on 2026-10-18 and its fixture is `trials/P-13.json`. This is how it is run again, or how a script copied
from it is run for P-26 or for a metered fallback. The script was hardened after that run, under
"Trial scripts: P-13's script hardened before it runs again" (issue 178): the next run is the first with the
model's tools disallowed, and shows whether structured output still works that way.

**Who does what.** **M** is the Maintainer, at his own terminal. **S** is a session. A step that logs in, logs
out, or reads what the login holds is **M's alone**: steps 1 and 4. Step 2 runs the CLI on the login under a
configuration directory of its own. The CLI reads that login; the script never does. So M or S can run step 2
once M has logged in. Step 3 is S's: it reads only what the script left in OUT.

## The pass condition, written first

S drafts it in a scratch directory (`mktemp -d`) before step 2, with `trial`, `question` and `pass` set, as
`trials/P-13.json` has them. `checked.json` in OUT gives each part of that condition, and `every_part_holds`
combines them. The verdict is still S's, against the condition.

## 1. Log the CLI in to a configuration directory of its own (M alone: this holds a credential)

The directory is outside every repo, apart from the one M's interactive sessions use, and logged in to the
Maintainer's own subscription (decision 0033). Run this once, at M's own terminal:

```
mkdir -m 700 ~/.config/sf-factory-claude
ls ~/.local/share/claude/versions/2.1.306          # the pinned build; the script runs this file
CLAUDE_CONFIG_DIR=~/.config/sf-factory-claude claude auth login --claudeai
```

On macOS the CLI may keep the login in the login Keychain rather than in the directory, and that Keychain may
be shared with M's own login (unverified). Do not copy the directory into a repo or a workflow, and do not log
it out while P-26 waits on it. The CI credential (`claude setup-token`, an environment secret) belongs to
slice 1, after P-3 and P-26.

If `versions/2.1.306` is gone because the installer pruned it, `claude install 2.1.306` brings it back. That
also moves M's own `claude` to 2.1.306, so say so before running it. Otherwise pass the path of a 2.1.306 build
as the script's third argument. The pin moves only by a run of this script at the new version, recorded as a
fixture of P-13 and a row on decision 0033, as 2.1.302 gave way to 2.1.306 when the installer pruned it.

## 2. Run the trial (M, or S once step 1 is done)

From a worktree of main. The main checkout stays on `main`.

```
git -C ~/repos/software-factory worktree add --detach ~/sf-trial-p13 origin/main
cd ~/sf-trial-p13
less tools/trial_p13_cli.sh
bash tools/trial_p13_cli.sh ~/sf-trial-p13-out ~/.config/sf-factory-claude
```

- It uses one small Task of the subscription's capacity.
- It asks three things: `claude --version`, `claude auth status --json` (keeping only `loggedIn`,
  `authMethod`, `apiProvider` and `subscriptionType`), and one `claude -p` with `--json-schema` and
  `--tools ""`, so the model has no tool.
- It runs the CLI with `env -i`, so no `ANTHROPIC_API_KEY` or other token in the shell reaches it. It also
  passes `DISABLE_AUTOUPDATER=1`, `--no-session-persistence` and `--strict-mcp-config`, and runs in an empty
  scratch directory.
- It keeps, of the Task's answer, only the fields it names: the model's text and every field it does not name
  are dropped and counted in `checked.json`. It prints the CLI's exit code, the version before and after,
  whether the CLI is logged in, whether every part holds, and where the redaction removed something. It never
  prints the answer.
- It exits 0 only when every part holds.
- It refuses, before asking anything, when OUT exists or is inside the repo or CONFIG_DIR, when CONFIG_DIR is
  missing, inside the repo, the home directory or any directory holding it, or anywhere under `~/.claude`. It
  stops after asking the version when it is not 2.1.306, and after asking the login when `auth status` exits
  non-zero or does not say it is logged in; `checked.json` then records the login's exit code and status.
- In a session, `tools/hooks/protected.py` asks about this command, or under bypass tells it, because the
  script starts Claude Code with `CLAUDE_CONFIG_DIR` set (decision 0021). That is expected.

M then pastes the OUT path, `~/sf-trial-p13-out`, to S.

## 3. Build the fixture (S)

S reads only what is in OUT: `ran_at`, `requests.json`, `checked.json`, `clean-1`, `clean-2`, `clean-3` and
`redacted-*`. OUT holds no credential and none of the model's text; of the Task's standard error only its
line and character counts are in `checked.json`. The script kept only
the fields `requests.json` lists under `kept` for exchange 3, only the tool names in `permission_denials`, and
`structured_output` only if it validated. `checked.json`'s `model_text_removed` says what was taken out.

In the scratch directory, draft the fixture from the pass-condition draft:

- `schema` `trial/1`; `repo` null and each request `as` the kind `subscription` (decision 0033); `ran_at` from
  `ran_at`.
- `exchanges`: one for each entry of `requests.json`, in order:
  - `request`: `{"as": {...}, "via": "cli", "call": <call>, "headers": {}, "body": {"env": ..., "cwd": ...,`
    plus `"prompt"` and `"json_schema"` for exchange 3`}}`. `as.name` names the subscription in words, never by
    an address.
  - `response`: `{"status": <exit code>, "headers": {}, "body": <the clean-N file, as JSON where it is JSON>}`.
    Exchange 1's body is the text of `clean-1`; exchange 2's exit code is `checked.json`'s `login.exit`, and
    exchange 3's is its `exit`.
- `removed`: each line of `redacted-3` becomes `exchanges[2].response.body.<path>`. The redaction removes by
  key name; the CLI's token counts are named harmless in `tools/check_trials.py`, so they stay.
- `verdict` against the pass condition.

Then:

```
python3 -m tools.redact_trial < "$D/P-13.json" > "$D/P-13.clean.json"   # the draft, once more
cp "$D/P-13.clean.json" trials/P-13.json
python3 -m tools.check_trials
```

- **Grounding (skill step 7).** No rule in `sim/grounding.py` names P-13, so there is nothing to ground.
- **Undo (skill step 8).** Nothing in GitHub was touched.
- **Verify.** Run `make verify` and `python3 -m tools.mutants`. The Maintainer opens the PR. Its body names
  the trial, the verdict and what was removed.
- **On a fail.** S tells M, and M opens an issue against the design before any code depends on the answer.
  Then go to step 4.

## 4. Only if the answer is no: the metered key (M alone: this holds a credential)

The issue says that if the answer is no, the metered key is tried and recorded. The script is unchanged. Only
the login differs, in a second directory:

```
mkdir -m 700 ~/.config/sf-factory-claude-metered
CLAUDE_CONFIG_DIR=~/.config/sf-factory-claude-metered claude auth login --console   # API billing
bash tools/trial_p13_cli.sh ~/sf-trial-p13-metered-out ~/.config/sf-factory-claude-metered
```

S builds the fixture P-13.metered.json from that OUT, as in step 3. The `pass` says it is the metered
fallback, under FR-73.

## 5. Afterwards (M)

- OUT holds nothing secret. Delete it once the fixture has merged: `rm -rf ~/sf-trial-p13-out`.
- The login stays under `~/.config/sf-factory-claude` for P-26 (see the issue). The metered one, if step 4
  ran, ends with `CLAUDE_CONFIG_DIR=~/.config/sf-factory-claude-metered claude auth logout`.
- `git -C ~/repos/software-factory worktree remove ~/sf-trial-p13`.
