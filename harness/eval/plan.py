"""The eval job's first step: what the run judges, or `eval_set_empty` before anything is minted."""
from harness.eval import exit_with, plan

if __name__ == "__main__":
    exit_with(plan)
