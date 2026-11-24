"""The mutants of `.claude/settings.json`: tools/mutants.py runs them."""

TARGETS = (".claude/settings.json",)
MUTANTS = [
    # The stop-hook review, 2026-11-05: each hook runs the main checkout's copy, and checks are not run twice at one state.
    # The stop-hook review, 2026-11-05: each hook runs the main checkout's copy, and checks are not run twice at one state.
    ('a hook whose main checkout has no copy runs nothing', '.claude/settings.json',
     '[ -f \\"$d/tools/hooks/identity.py\\" ] || d=$CLAUDE_PROJECT_DIR; ', '', ('tests.test_hooks.Settings.test_every_hook_runs_the_main_checkouts_copy_wherever_the_session_started',)),
    ("a hook runs the project folder's own copy", '.claude/settings.json',
     'worktree list --porcelain 2>/dev/null | sed -n \'1s/^worktree //p\'); [ -n \\"$d\\" ] && [ -f \\"$d/tools/hooks/identity.py', 'rev-parse --show-toplevel 2>/dev/null); [ -n \\"$d\\" ] && [ -f \\"$d/tools/hooks/identity.py', ('tests.test_hooks.Settings.test_every_hook_runs_the_main_checkouts_copy_wherever_the_session_started',)),
    ("a hook with no main checkout's copy refuses", '.claude/settings.json',
     'project folder.\\"}\'; exit 0; }; python3 -I \\"$d/tools/hooks/identity.py', 'project folder.\\"}\'; exit 2; }; python3 -I \\"$d/tools/hooks/identity.py', ('tests.test_hooks.Settings.test_every_hook_runs_the_main_checkouts_copy_wherever_the_session_started',)),
    ('a hook that fails is let through', '.claude/settings.json',
     'python3 -I \\"$d/tools/hooks/identity.py\\" || exit 2"', 'python3 -I \\"$d/tools/hooks/identity.py\\""', ('tests.test_hooks.Settings.test_every_hook_runs_the_main_checkouts_copy_wherever_the_session_started',)),
]
