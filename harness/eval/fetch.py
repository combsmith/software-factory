"""The eval job's fetch: each case from the private home, with the token the job minted for it, and nothing else."""

from harness.eval import Stop, exit_with, fetch


def transport(env: dict):
    from adapters import github
    try:
        return github.Live(env.get("HELDOUT_TOKEN"))
    except github.Unanswered:
        raise Stop("token_unreadable") from None


def step(env, root, workspace):
    return fetch(env, root, workspace, transport(env))


if __name__ == "__main__":
    exit_with(step)
