"""The mutants of `tools/trial_p50_stub.py`: tools/mutants.py runs them."""

from tools.mutants_of.common import P50_TESTS, P59_TESTS

P50_STUB = "tools/trial_p50_stub.py"

TARGETS = ("tools/trial_p50_stub.py",)
MUTANTS = [
    # P-59: the read tools alone, held to their folder, against a stand-in CLI and P-50's stub given the trial's calls.
    ("P-59's stub logs a marker's text", P50_STUB,
     'return sorted(k for k, v in marks.items() if v in text)', 'return sorted(v for k, v in marks.items() if v in text)',
     (P59_TESTS + "test_the_stub_answers_the_trials_calls_and_logs_only_the_markers_names",)),
    ("P-59's stub calls a tool where none is offered", P50_STUB,
     'return held["calls"][done] if body.get("tools") and done < len(held["calls"]) else None',
     'return held["calls"][done] if done < len(held["calls"]) else None',
     (P59_TESTS + "test_the_stub_answers_the_trials_calls_and_logs_only_the_markers_names",)),
    # Issue 287: P-50, the Linux trial of the pinned CLI's sandbox, run against a stand-in CLI and the real stub.
    ("P-50's stub asks for the tool again after its result", P50_STUB,
     'return "tool_use" if offers and not answered else "text"', 'return "tool_use" if offers else "text"',
     (P50_TESTS + "test_the_stub_answers_one_tool_call_and_keeps_no_header",)),
]
