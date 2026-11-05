"""Gate between a DokuWiki's aichat plugin and a local Ollama, on the AI machine.

Ollama listens on localhost only; this gate is the one port the wiki server can reach.
It exists because of how the aichat plugin (cosmocode/dokuwiki-plugin-aichat) talks to
Ollama, which does not suit a 16 GB GPU:

- For a model that is not in its own list, the plugin sizes the model from /api/show and
  then sends that full trained context (128k-256k tokens for current models) as num_ctx on
  every call. A KV cache that size pushes the model partly onto the CPU. The gate caps the
  context_length that /api/show reports, so the plugin sizes its chunks and num_ctx to fit,
  and caps num_ctx on the calls themselves as well.
- The plugin never sends "think", so hybrid-thinking models (Qwen3.5) reason before every
  answer and every question rephrasing, while the plugin waits with a 60 s timeout and no
  streaming. The gate sets "think" to AICHAT_GATE_THINK when a request leaves it out, and
  keeps an explicit value (the patched plugin asks for thinking only for the streamed answer).
- Ollama has no authentication. The gate requires the token the plugin sends as
  "Authorization: Bearer <ollama_apikey>", and passes on only the endpoints the plugin needs,
  so nobody else on the network can use the GPU or pull and delete models.

Configuration comes from the environment (on the AI machine: /etc/aichat-gate.env):

    AICHAT_GATE_TOKEN              required; the plugin's ollama_apikey
    AICHAT_GATE_LISTEN             host:port, default 0.0.0.0:11435
    AICHAT_GATE_OLLAMA_URL         default http://127.0.0.1:11434
    AICHAT_GATE_CONTEXT_CAP        default 32768
    AICHAT_GATE_EMBED_CONTEXT_CAP  default 8192
    AICHAT_GATE_THINK              true/false, default false
    AICHAT_GATE_TIMEOUT            seconds Ollama may stay silent, default 600
"""
import dataclasses
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOWED = {
    ("POST", "/api/chat"),
    ("POST", "/api/embed"),
    ("POST", "/api/show"),
    ("GET", "/api/version"),
    ("GET", "/api/tags"),
    # OpenAI-style routes, for the aiagent plugin should the wiki switch to it later.
    ("POST", "/v1/chat/completions"),
    ("POST", "/v1/embeddings"),
    ("GET", "/v1/models"),
}
MAX_BODY_BYTES = 16 * 1024 * 1024
STREAM_READ_BYTES = 64 * 1024


@dataclasses.dataclass(frozen=True)
class Config:
    token: str
    host: str = "0.0.0.0"
    port: int = 11435
    ollama_url: str = "http://127.0.0.1:11434"
    context_cap: int = 32768
    embed_context_cap: int = 8192
    think: bool = False
    timeout: float = 600.0


def config_from_env(env=os.environ) -> Config:
    token = env.get("AICHAT_GATE_TOKEN", "").strip()
    if not token:
        raise ValueError("AICHAT_GATE_TOKEN is not set - refusing to run without a token")
    host, _, port = env.get("AICHAT_GATE_LISTEN", "0.0.0.0:11435").rpartition(":")
    return Config(
        token=token,
        host=host or "0.0.0.0",
        port=int(port),
        ollama_url=env.get("AICHAT_GATE_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
        context_cap=int(env.get("AICHAT_GATE_CONTEXT_CAP", "32768")),
        embed_context_cap=int(env.get("AICHAT_GATE_EMBED_CONTEXT_CAP", "8192")),
        think=env.get("AICHAT_GATE_THINK", "false").strip().lower() in ("1", "true", "yes", "on"),
        timeout=float(env.get("AICHAT_GATE_TIMEOUT", "600")),
    )


def _cap_num_ctx(body: dict, cap: int):
    options = body.get("options")
    if isinstance(options, dict) and isinstance(options.get("num_ctx"), (int, float)):
        options["num_ctx"] = min(int(options["num_ctx"]), cap)


def rewrite_request(path: str, body: dict, cfg: Config) -> dict:
    if path == "/api/chat":
        body.setdefault("think", cfg.think)
        _cap_num_ctx(body, cfg.context_cap)
    elif path == "/api/embed":
        _cap_num_ctx(body, cfg.embed_context_cap)
    return body


def rewrite_show(body: dict, cfg: Config) -> dict:
    model_info = body.get("model_info")
    if isinstance(model_info, dict):
        for key, value in model_info.items():
            if key.endswith(".context_length") and isinstance(value, int):
                model_info[key] = min(value, cfg.context_cap)
    return body


class GateHandler(BaseHTTPRequestHandler):
    # HTTP/1.0: a streamed answer simply ends when the connection closes, which every
    # client (DokuWiki's HTTP client, cURL, browsers) understands without chunked encoding.
    protocol_version = "HTTP/1.0"
    server_version = "aichat-gate"
    cfg: Config

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_DELETE(self):
        self._handle("DELETE")

    def do_PUT(self):
        self._handle("PUT")

    def log_message(self, format, *args):
        pass

    def _handle(self, method: str):
        started = time.monotonic()
        path = urllib.parse.urlsplit(self.path).path
        model, status = "", 0
        try:
            status, model = self._serve(method, path)
        except (BrokenPipeError, ConnectionResetError):
            status = 499
        finally:
            print(f"{method} {path} model={model or '-'} status={status} "
                  f"{time.monotonic() - started:.1f}s client={self.client_address[0]}", flush=True)

    def _serve(self, method: str, path: str) -> tuple[int, str]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            return self._send_error(413, "request too large"), ""
        # Read the body before answering even a refusal: replying while the client is still
        # sending can reset the connection before it sees the reason.
        raw = self.rfile.read(length) if length else b""
        given = self.headers.get("Authorization", "")
        if not hmac.compare_digest(given.encode(), f"Bearer {self.cfg.token}".encode()):
            return self._send_error(401, "missing or wrong token (the aichat setting ollama_apikey)"), ""
        if (method, path) not in ALLOWED:
            return self._send_error(403, f"{method} {path} is not available through this gate"), ""

        data, model = None, ""
        if method == "POST":
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                return self._send_error(400, "request body is not JSON"), ""
            if not isinstance(body, dict):
                return self._send_error(400, "request body must be a JSON object"), ""
            model = str(body.get("model", ""))
            data = json.dumps(rewrite_request(path, body, self.cfg)).encode()

        request = urllib.request.Request(
            self.cfg.ollama_url + path, data=data, method=method,
            headers={"Content-Type": "application/json"} if data is not None else {},
        )
        try:
            upstream = urllib.request.urlopen(request, timeout=self.cfg.timeout)
        except urllib.error.HTTPError as exc:
            return self._send(exc.code, exc.headers.get("Content-Type", "application/json"), exc.read()), model
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            return self._send_error(502, f"Ollama is not reachable at {self.cfg.ollama_url}: {reason}"), model

        with upstream:
            content_type = upstream.headers.get("Content-Type", "application/json")
            if path == "/api/show":
                try:
                    payload = json.dumps(rewrite_show(json.loads(upstream.read()), self.cfg)).encode()
                except ValueError:
                    return self._send_error(502, "Ollama sent an unreadable /api/show answer"), model
                return self._send(upstream.status, content_type, payload), model
            if upstream.headers.get("Content-Length") is not None:
                return self._send(upstream.status, content_type, upstream.read()), model
            # No length means Ollama is streaming (NDJSON): pass each piece on as it arrives,
            # so the reasoning reaches the wiki live.
            self.send_response(upstream.status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            while chunk := upstream.read1(STREAM_READ_BYTES):
                self.wfile.write(chunk)
                self.wfile.flush()
            return upstream.status, model

    def _send(self, status: int, content_type: str, payload: bytes) -> int:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        return status

    def _send_error(self, status: int, message: str) -> int:
        # Ollama's own error shape: the plugin shows the "error" text instead of a bare failure.
        return self._send(status, "application/json", json.dumps({"error": message}).encode())


def make_server(cfg: Config) -> ThreadingHTTPServer:
    handler = type("BoundGateHandler", (GateHandler,), {"cfg": cfg})
    server = ThreadingHTTPServer((cfg.host, cfg.port), handler)
    server.daemon_threads = True
    return server


def main():
    try:
        cfg = config_from_env()
    except ValueError as exc:
        sys.exit(str(exc))
    server = make_server(cfg)
    print(f"aichat-gate on {cfg.host}:{cfg.port} -> {cfg.ollama_url} "
          f"(context cap {cfg.context_cap}, embed cap {cfg.embed_context_cap}, think {cfg.think})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
