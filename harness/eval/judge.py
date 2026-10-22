"""The eval job's last step: the run passes only if its report passes the gate's own test."""
from harness.eval import exit_with, judge

if __name__ == "__main__":
    exit_with(judge)
