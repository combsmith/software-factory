"""The mutants of `tools/machine_user_drift.sh`: tools/mutants.py runs them."""

TARGETS = ("tools/machine_user_drift.sh",)
MUTANTS = [
    # Issue 89: the machine user's role, held to the configuration and compared with GitHub by hand.
    ('an answer is kept unredacted', 'tools/machine_user_drift.sh',
     '(cd "$root" && python3 -m tools.redact_trial < "$dir/raw" >> "$dir/answers") 2> /dev/null ||', 'cat "$dir/raw" >> "$dir/answers" ||', ('tests.test_tools.Apps.test_the_machine_users_script_keeps_each_answer_redacted_and_compares_them',)),
    ('the script leaves its scratch directory', 'tools/machine_user_drift.sh',
     'trap \'rm -rf "$dir"\' EXIT\n', '', ('tests.test_tools.Apps.test_the_machine_users_script_keeps_each_answer_redacted_and_compares_them',)),
    ("the machine user's script may scratch inside the repo", 'tools/machine_user_drift.sh',
     'case "$real/" in "$root"/*) echo "the scratch directory $real is inside the repo; set TMPDIR elsewhere" >&2; exit 2;; esac\n', '', ('tests.test_tools.Apps.test_the_machine_users_script_refuses_a_scratch_directory_inside_the_repo',)),
    ('a scratch directory reached through a link may be inside the repo here', 'tools/machine_user_drift.sh',
     'real=$(cd "$dir" && pwd -P)\n', 'real=$dir\n', ('tests.test_tools.Apps.test_the_machine_users_script_refuses_a_scratch_directory_inside_the_repo',)),
]
