"""The mutants of `tools/environments_drift.sh`: tools/mutants.py runs them."""

TARGETS = ("tools/environments_drift.sh",)
from tools.mutants_of.common import ISOLATED, ISOLATED_TEST, UNISOLATED  # noqa: E402
MUTANTS = [
    # Issue 463: each factory environment is main alone, read by hand.
    ('an answer is kept unredacted here', 'tools/environments_drift.sh',
     'python3 -I "$root/tools/redact_trial.py" < "$dir/raw-$1" > "$dir/$1" 2> /dev/null ||', 'cat "$dir/raw-$1" > "$dir/$1" ||', ('tests.test_tools.EnvironmentsDrift.test_the_script_reads_each_environment_redacts_it_and_compares',)),
    ('this script leaves its scratch directory', 'tools/environments_drift.sh',
     'trap \'rm -rf "$dir"\' EXIT\n', '', ('tests.test_tools.EnvironmentsDrift.test_the_script_reads_each_environment_redacts_it_and_compares',)),
    ('this script may scratch inside the repo', 'tools/environments_drift.sh',
     'case "$real/" in "$root"/*) echo "the scratch directory $real is inside the repo; set TMPDIR elsewhere" >&2; exit 2;; esac\n', '', ('tests.test_tools.EnvironmentsDrift.test_a_scratch_directory_inside_the_repo_is_refused_however_it_is_reached',)),
    ("a link may take this script's scratch inside the repo", 'tools/environments_drift.sh',
     'real=$(cd "$dir" && pwd -P)\n', 'real=$dir\n', ('tests.test_tools.EnvironmentsDrift.test_a_scratch_directory_inside_the_repo_is_refused_however_it_is_reached',)),
    ('a read gh refuses stops the script', 'tools/environments_drift.sh',
     '> "$dir/raw-$1" 2>/dev/null || true\n', '> "$dir/raw-$1" 2>/dev/null\n', ('tests.test_tools.EnvironmentsDrift.test_the_script_reads_each_environment_redacts_it_and_compares',)),
    ('a raw answer is left behind', 'tools/environments_drift.sh',
     '  rm -f "$dir/raw-$1"\n', '', ('tests.test_tools.EnvironmentsDrift.test_the_script_reads_each_environment_redacts_it_and_compares',)),
    # Issue 458: a signal becomes a script's exit, the same in each.
    ("the drift script's clean-up leaves a signal to its shell", 'tools/environments_drift.sh',
     "trap 'exit 1' HUP INT TERM\n", '', ('tests.test_tools.SignalTraps.test_every_script_turns_a_signal_into_its_exit',)),
    ('a signal ends a drift script as if it had passed', 'tools/environments_drift.sh',
     "trap 'exit 1' HUP INT TERM\n", "trap 'exit 0' HUP INT TERM\n", ('tests.test_tools.SignalTraps.test_every_script_turns_a_signal_into_its_exit',)),
    # Issue 1300: its redaction runs as a file under -I.
    ("environments_drift.sh runs a redaction the shell's modules can steer", "tools/environments_drift.sh", ISOLATED + ' < "$dir/raw-$1"', UNISOLATED + ' < "$dir/raw-$1"',
     ISOLATED_TEST),
]
