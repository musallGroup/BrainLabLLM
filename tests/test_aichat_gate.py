"""Tests for server/aichat/aichat_gate.py: the gate between DokuWiki's aichat plugin and Ollama.

A fake Ollama runs in a thread and records what reaches it; the gate runs in front of it.
Nothing here touches the network beyond 127.0.0.1.
"""
import http.client
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server" / "aichat"))
import aichat_gate  # noqa: E402

TOKEN = "test-token"


class FakeOllama(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    seen: list
    release_stream: threading.Event

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.seen.append(("GET", self.path, None))
        self._json(200, {"version": "0.40.14"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.seen.append(("POST", self.path, body))
        if body.get("model") == "missing":
            return self._json(404, {"error": "model 'missing' not found"})
        if self.path == "/api/show":
            return self._json(200, {"model_info": {"general.architecture": "qwen35",
                                                   "qwen35.context_length": 262144,
                                                   "qwen35.embedding_length": 4096}})
        if self.path == "/api/chat" and body.get("stream"):
            # No Content-Length, like Ollama's NDJSON stream; the second line waits until
            # the test has received the first one through the gate.
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            self.wfile.write(b'{"message":{"thinking":"Let me look"},"done":false}\n')
            self.wfile.flush()
            self.release_stream.wait(5)
            self.wfile.write(b'{"message":{"content":"Answer"},"done":true}\n')
            return
        self._json(200, {"message": {"content": "ok"}, "embeddings": [[0.1, 0.2]]})

    def _json(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _serve(server):
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    return server


@pytest.fixture
def gate():
    seen, release = [], threading.Event()
    ollama = _serve(ThreadingHTTPServer(
        ("127.0.0.1", 0), type("Fake", (FakeOllama,), {"seen": seen, "release_stream": release})))
    cfg = aichat_gate.Config(token=TOKEN, host="127.0.0.1", port=0,
                             ollama_url=f"http://127.0.0.1:{ollama.server_address[1]}",
                             context_cap=32768, embed_context_cap=8192, think=False, timeout=10)
    server = _serve(aichat_gate.make_server(cfg))

    class Client:
        port = server.server_address[1]
        upstream = seen
        release_stream = release

        def request(self, method, path, body=None, token=TOKEN):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            headers = {"Content-Type": "application/json"}
            if token is not None:
                headers["Authorization"] = f"Bearer {token}"
            conn.request(method, path, body=None if body is None else json.dumps(body), headers=headers)
            return conn.getresponse()

        def json(self, method, path, body=None, token=TOKEN):
            resp = self.request(method, path, body, token)
            return resp.status, json.loads(resp.read())

    yield Client()
    release.set()
    server.shutdown()
    ollama.shutdown()


@pytest.mark.parametrize("token", [None, "wrong", ""])
def test_refuses_requests_without_the_token(gate, token):
    status, body = gate.json("POST", "/api/chat", {"model": "m", "messages": []}, token=token)
    assert status == 401 and "ollama_apikey" in body["error"]
    assert gate.upstream == []


@pytest.mark.parametrize("method, path", [
    ("POST", "/api/pull"), ("DELETE", "/api/delete"), ("POST", "/api/create"),
    ("GET", "/api/ps"), ("POST", "/api/generate"), ("GET", "/"),
])
def test_only_the_plugins_endpoints_get_through(gate, method, path):
    status, body = gate.json(method, path, {"model": "m"} if method != "GET" else None)
    assert status == 403 and path in body["error"]
    assert gate.upstream == []


def test_show_reports_the_capped_context(gate):
    status, body = gate.json("POST", "/api/show", {"model": "qwen3.5:9b"})
    assert status == 200
    assert body["model_info"]["qwen35.context_length"] == 32768
    assert body["model_info"]["qwen35.embedding_length"] == 4096  # only context lengths change


def test_chat_turns_thinking_off_unless_asked_and_caps_the_context(gate):
    gate.json("POST", "/api/chat", {"model": "m", "messages": [], "options": {"num_ctx": 262144}})
    gate.json("POST", "/api/chat", {"model": "m", "messages": [], "think": True, "options": {"num_ctx": 4096}})
    first, second = (body for _, _, body in gate.upstream)
    assert first["think"] is False and first["options"]["num_ctx"] == 32768
    assert second["think"] is True and second["options"]["num_ctx"] == 4096


def test_embed_context_is_capped_separately(gate):
    status, body = gate.json("POST", "/api/embed", {"model": "bge-m3", "input": "x", "options": {"num_ctx": 32768}})
    assert status == 200 and body["embeddings"] == [[0.1, 0.2]]
    assert gate.upstream[0][2]["options"]["num_ctx"] == 8192
    assert "think" not in gate.upstream[0][2]


def test_streamed_lines_arrive_before_the_stream_ends(gate):
    resp = gate.request("POST", "/api/chat", {"model": "m", "messages": [], "stream": True, "think": True})
    assert resp.status == 200
    first = json.loads(resp.readline())
    assert first["message"]["thinking"] == "Let me look"
    gate.release_stream.set()
    assert json.loads(resp.readline())["message"]["content"] == "Answer"


def test_ollama_errors_are_passed_on(gate):
    status, body = gate.json("POST", "/api/chat", {"model": "missing", "messages": []})
    assert status == 404 and body["error"] == "model 'missing' not found"


def test_get_routes_pass_through(gate):
    status, body = gate.json("GET", "/api/version")
    assert status == 200 and body["version"] == "0.40.14"


def test_rejects_a_body_that_is_not_json(gate):
    conn = http.client.HTTPConnection("127.0.0.1", gate.port, timeout=10)
    conn.request("POST", "/api/chat", body="not json", headers={"Authorization": f"Bearer {TOKEN}"})
    resp = conn.getresponse()
    assert resp.status == 400 and gate.upstream == []


def test_unreachable_ollama_gives_a_clear_error():
    cfg = aichat_gate.Config(token=TOKEN, host="127.0.0.1", port=0, ollama_url="http://127.0.0.1:9", timeout=2)
    server = _serve(aichat_gate.make_server(cfg))
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        conn.request("GET", "/api/version", headers={"Authorization": f"Bearer {TOKEN}"})
        resp = conn.getresponse()
        assert resp.status == 502 and "not reachable" in json.loads(resp.read())["error"]
    finally:
        server.shutdown()


def test_config_from_env():
    with pytest.raises(ValueError, match="AICHAT_GATE_TOKEN"):
        aichat_gate.config_from_env({})
    cfg = aichat_gate.config_from_env({"AICHAT_GATE_TOKEN": " t ", "AICHAT_GATE_LISTEN": "127.0.0.1:8000",
                                       "AICHAT_GATE_OLLAMA_URL": "http://h:1/", "AICHAT_GATE_THINK": "True"})
    assert (cfg.token, cfg.host, cfg.port, cfg.ollama_url, cfg.think) == ("t", "127.0.0.1", 8000, "http://h:1", True)
    assert (cfg.context_cap, cfg.embed_context_cap) == (32768, 8192)
