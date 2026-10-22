"""Trial P-50's stand-in for the model (issue 287): the Messages API, on 127.0.0.1, answering one scripted call.

The pinned CLI is pointed at it by ANTHROPIC_BASE_URL with a dummy key, so that its sandbox runs a tool on a GitHub
runner with no secret and no model. To a request that offers the Bash tool and carries no tool result it answers one
tool call, `sh ./probe.sh`; to every other request for a message it answers the one word done. It counts tokens as 1
and answers 404 to any other path. It reads no prompt, keeps no header and logs, a line to a request, only the path
and what kind of answer it gave, so the trial's markers never reach its log.

    python3 -I tools/trial_p50_stub.py PORT_FILE LOG_FILE

It listens on a free port, writes the port to PORT_FILE once it listens, and serves until it is killed.
"""
import http.server
import json
import os
import sys
import threading

COMMAND = "sh ./probe.sh"
lock = threading.Lock()
calls = [0]


def blocks(kind: str, n: int) -> list:
    """The content of the answer: the one tool call, or the word done."""
    if kind == "tool_use":
        return [{"type": "tool_use", "id": "toolu_p50_%d" % n, "name": "Bash",
                 "input": {"command": COMMAND, "description": "Run the trial's probe"}}]
    return [{"type": "text", "text": "done"}]


def message(kind: str, n: int, model: str) -> dict:
    return {"id": "msg_p50_%d" % n, "type": "message", "role": "assistant", "model": model,
            "content": blocks(kind, n), "stop_reason": "tool_use" if kind == "tool_use" else "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}


def events(kind: str, n: int, model: str) -> list:
    """The same answer as the stream of server-sent events the API sends for `"stream": true`."""
    whole = message(kind, n, model)
    out = [("message_start", {"type": "message_start", "message": dict(whole, content=[], stop_reason=None)})]
    for i, block in enumerate(whole["content"]):
        if block["type"] == "tool_use":
            out.append(("content_block_start", {"type": "content_block_start", "index": i,
                                                "content_block": dict(block, input={})}))
            out.append(("content_block_delta", {"type": "content_block_delta", "index": i,
                                                "delta": {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}}))
        else:
            out.append(("content_block_start", {"type": "content_block_start", "index": i,
                                                "content_block": {"type": "text", "text": ""}}))
            out.append(("content_block_delta", {"type": "content_block_delta", "index": i,
                                                "delta": {"type": "text_delta", "text": block["text"]}}))
        out.append(("content_block_stop", {"type": "content_block_stop", "index": i}))
    out.append(("message_delta", {"type": "message_delta", "delta": {"stop_reason": whole["stop_reason"], "stop_sequence": None},
                                  "usage": {"output_tokens": 1}}))
    out.append(("message_stop", {"type": "message_stop"}))
    return out


def types(message) -> list:
    """The kinds of block a message holds, never their text: "text" for a message that is a string."""
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return ["text"]
    return [str(c.get("type"))[:32] for c in content if isinstance(c, dict)] if isinstance(content, list) else []


def kind_of(body: dict) -> str:
    """tool_use when the request offers Bash and its conversation holds no tool call or result yet; text otherwise."""
    offers = any(isinstance(t, dict) and t.get("name") == "Bash" for t in body.get("tools") or [])
    messages = body.get("messages") if isinstance(body.get("messages"), list) else []
    answered = any(kind in ("tool_use", "tool_result") for m in messages for kind in types(m))
    return "tool_use" if offers and not answered else "text"


def shape(body: dict) -> dict:
    """What the log keeps of a request: how many messages, each one's role, and the kinds of block in the last two."""
    messages = body.get("messages") if isinstance(body.get("messages"), list) else []
    return {"messages": len(messages),
            "roles": "".join((m.get("role") or "?")[:1] if isinstance(m, dict) else "?" for m in messages)[-12:],
            "last": [types(m) for m in messages[-2:]]}


class Stub(http.server.BaseHTTPRequestHandler):
    log_path = None

    def log_message(self, *args):    # the server's own access log would print the request line; it is not kept
        pass

    def note(self, **line):
        with lock, open(self.log_path, "a") as log:
            log.write(json.dumps(dict(line, path=self.path.split("?", 1)[0])) + "\n")

    def send(self, status: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.note(answer=404)
        self.send(404, {"type": "error", "error": {"type": "not_found_error", "message": "the P-50 stub serves messages alone"}})

    do_HEAD = do_GET

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = None
        path = self.path.split("?", 1)[0]
        if not isinstance(body, dict):
            self.note(answer=400)
            return self.send(400, {"type": "error", "error": {"type": "invalid_request_error", "message": "not JSON"}})
        if path == "/v1/messages/count_tokens":
            self.note(answer="count")
            return self.send(200, {"input_tokens": 1})
        if path != "/v1/messages":
            return self.do_GET()
        with lock:
            calls[0] += 1
            n = calls[0]
        kind = kind_of(body)
        model = body.get("model") if isinstance(body.get("model"), str) and len(body["model"]) < 80 else "p50-stub"
        stream = body.get("stream") is True
        self.note(answer=kind, stream=stream, n=n, **shape(body))
        if not stream:
            return self.send(200, message(kind, n, model))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for name, data in events(kind, n, model):
            self.wfile.write(("event: %s\ndata: %s\n\n" % (name, json.dumps(data))).encode())
        self.wfile.flush()
        self.close_connection = True


def main(argv: list) -> int:
    port_file, log_file = argv
    Stub.log_path = log_file
    open(log_file, "w").close()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    with open(port_file + ".part", "w") as f:
        f.write(str(server.server_address[1]))
    os.replace(port_file + ".part", port_file)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
