"""The mutants of `.github/workflows/run-jobs.yml`: tools/mutants.py runs them."""

from tools.mutants_of.common import NEEDED

TARGETS = (".github/workflows/run-jobs.yml",)
MUTANTS = [
    # Issue 388: each run: step stops under a limit of its own, the steps together below their job's.
    ("the Engine's step is cut before its call can end", ".github/workflows/run-jobs.yml",
     "        timeout-minutes: 20\n", "        timeout-minutes: 15\n", NEEDED),
    # Issue 757: the run record says whether a Run's Engine step started, from the outcome apply writes.
    ("the run job hands on nothing of its Engine step", '.github/workflows/run-jobs.yml',
     '      engine: ${{ steps.engine.outcome }}\n', '', ('tests.test_steps.Apply.test_apply_says_whether_the_engine_step_started',)),
    ("the Run's first job checks out the tag again", '.github/workflows/run-jobs.yml',
     '          ref: ${{ job.workflow_sha }}\n', '          ref: factory/v0-next\n',
     ('tests.test_tools.Workflows.test_the_commit_a_later_job_checks_out_is_the_releases_own',)),
    # Decision 0239 (issue 952): no Run is given a tool that runs code or writes, and no job of a Run runs the item's code.
    ("the run job runs the item's tests beside the model's credential", '.github/workflows/run-jobs.yml',
     '        run: python3 -m harness.run\n',
     '        run: python3 -m harness.run\n      - name: Test\n        run: python3 -m unittest\n',
     ('tests.test_tools.Workflows.test_no_job_of_a_run_runs_the_items_code',)),
    ("the Run's first job checks out the item", '.github/workflows/run-jobs.yml',
     '          ref: ${{ job.workflow_sha }}\n', '          ref: ${{ inputs.item }}\n',
     ('tests.test_tools.Workflows.test_no_job_of_a_run_runs_the_items_code',)),
    ("the Engine step runs from the head's folder", '.github/workflows/run-jobs.yml',
     '        id: engine\n', '        id: engine\n        working-directory: task/head\n',
     ('tests.test_tools.Workflows.test_no_job_of_a_run_runs_the_items_code',)),
    ("the CLI's install runs a command after an allowed start", '.github/workflows/run-jobs.yml',
     '-o /tmp/claude "${url}"\n', '-o /tmp/claude "${url}"; make\n',
     ('tests.test_tools.Workflows.test_no_job_of_a_run_runs_the_items_code',)),
    ("the Engine runs a CLI from the head's folder", '.github/workflows/run-jobs.yml',
     '          CLAUDE_CLI: /usr/local/bin/claude\n', '          CLAUDE_CLI: task/head/claude\n',
     ('tests.test_tools.Workflows.test_no_job_of_a_run_runs_the_items_code',)),
    ("the Run's first job checks out with no ref", '.github/workflows/run-jobs.yml',
     '          ref: ${{ job.workflow_sha }}\n', '',
     ('tests.test_tools.Workflows.test_no_job_of_a_run_runs_the_items_code',)),
    ("the run job hands on the item as its commit", '.github/workflows/run-jobs.yml',
     '      commit: ${{ steps.commit.outputs.commit }}\n', '      commit: ${{ inputs.item }}\n',
     ('tests.test_tools.Workflows.test_no_job_of_a_run_runs_the_items_code',)),
    ("the run job runs on a runner of its own", '.github/workflows/run-jobs.yml',
     '    runs-on: ubuntu-24.04\n    timeout-minutes: 33\n', '    runs-on: self-hosted\n    timeout-minutes: 33\n',
     ('tests.test_tools.Workflows.test_no_job_of_a_run_runs_the_items_code',)),
    ("the Result is uploaded from the harness's folder", '.github/workflows/run-jobs.yml',
     '          path: result/\n', '          path: harness/\n',
     ('tests.test_tools.Workflows.test_no_job_of_a_run_runs_the_items_code',)),
    ("the Result is downloaded into the Release's folder", '.github/workflows/run-jobs.yml',
     '          artifact-ids: ${{ needs.run.outputs.artifact }}\n          path: result\n      - name: Verify the Result\n',
     '          artifact-ids: ${{ needs.run.outputs.artifact }}\n      - name: Verify the Result\n',
     ('tests.test_tools.Workflows.test_no_job_of_a_run_runs_the_items_code',)),
]
