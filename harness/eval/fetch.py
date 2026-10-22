"""The eval job's fetch: each case from the private home, with the Maintainer's own token for it, read-only on the home
alone (decision 0053), and nothing else. The token is used for reads alone: a request that is not a GET is refused
before it is sent, so no change to this step's code can write with it."""
from harness.eval import Stop, exit_with, fetch


class ReadOnly:
    """A transport that sends GETs alone, through the one it wraps."""

    def __init__(self, transport):
        self._transport = transport

    def send(self, req: dict) -> dict:
        from adapters import github
        if not isinstance(req, dict) or req.get("method") != "GET" or req.get("body") is not None:
            raise github.Unanswered("the held-out home is read, never written")
        return self._transport.send(req)


def transport(env: dict):
    from adapters import github
    try:
        return ReadOnly(github.Live(env.get("HELDOUT_TOKEN")))
    except github.Unanswered:
        raise Stop("token_unreadable") from None


def step(env, root, workspace):
    return fetch(env, root, workspace, transport(env))


if __name__ == "__main__":
    exit_with(step)
