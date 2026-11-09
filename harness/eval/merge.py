"""The merge job's step of a split run (issue 611): the one report, from what the preflight and each shard wrote."""
from harness.eval import exit_with, merge

if __name__ == "__main__":
    exit_with(merge)
