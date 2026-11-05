#!/usr/bin/env bash
# Self-test of the AI server for DokuWiki's aichat plugin. Run it on that machine:
#
#   ./check.sh                  all checks below
#   ./check.sh --bench MODEL..  only the decode-speed test, for these models (they must be pulled)
#
# Checks that Ollama and the gate run, the gate refuses requests without the token, the
# context is capped, embeddings come back, an answer arrives without reasoning and a streamed
# one with it, both models sit fully in GPU memory, and whether multi-token prediction (MTP)
# speeds up decoding. Exit code 1 if anything failed.
set -euo pipefail
ENV_FILE="${AICHAT_ENV_FILE:-/etc/aichat-gate.env}"

BENCH_ONLY=""
if [ "${1:-}" = "--bench" ]; then shift; BENCH_ONLY="$*"; [ -n "$BENCH_ONLY" ] || { echo "--bench needs model names" >&2; exit 2; }; fi
GATE_ENV="$(cat "$ENV_FILE" 2>/dev/null || sudo cat "$ENV_FILE" 2>/dev/null || true)"
[ -n "$GATE_ENV" ] || [ -n "$BENCH_ONLY" ] || { echo "cannot read $ENV_FILE - run install.sh first" >&2; exit 1; }
STARTED="$(date '+%Y-%m-%d %H:%M:%S')"

set +e
GATE_ENV="$GATE_ENV" BENCH_ONLY="$BENCH_ONLY" python3 - <<'PY'
import json, os, sys, time, urllib.error, urllib.request

env = dict(line.split("=", 1) for line in os.environ["GATE_ENV"].splitlines() if "=" in line and not line.startswith("#"))
OLLAMA = "http://127.0.0.1:11434"
GATE = "http://127.0.0.1:" + env.get("AICHAT_GATE_LISTEN", "0.0.0.0:11435").rpartition(":")[2]
TOKEN = env.get("AICHAT_GATE_TOKEN", "")
CHAT, EMBED = env.get("AICHAT_CHAT_MODEL", ""), env.get("AICHAT_EMBED_MODEL", "")
CAP = int(env.get("AICHAT_GATE_CONTEXT_CAP", "32768"))
failed = 0


def report(kind, text):
    global failed
    failed += kind == "FAIL"
    colour = {"OK": "32", "WARN": "33", "FAIL": "31"}[kind]
    print(f"  \033[{colour}m{kind:4}\033[0m {text}", flush=True)


def call(base, path, body=None, token=TOKEN, timeout=300):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, None if body is None else json.dumps(body).encode(), headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def decode_rate(model, prompt, temperature):
    # num_ctx must match what the plugin sends: Ollama reloads a model whenever it changes.
    body = {"model": model, "stream": False, "think": False, "messages": [{"role": "user", "content": prompt}],
            "options": {"num_predict": 300, "temperature": temperature, "seed": 7, "num_ctx": CAP}}
    _, d = call(OLLAMA, "/api/chat", body, token=None)
    return d["eval_count"] / (d["eval_duration"] / 1e9)


def bench(models):
    predictable = "Count from 1 to 300, separated by commas, nothing else."
    creative = "Invent a surreal 250-word story about an unlikely animal, using unusual vocabulary."
    print(f"  {'model':28} {'predictable':>12} {'creative':>12} {'ratio':>6}")
    for model in models:
        decode_rate(model, predictable, 0)  # warm-up: loads the model
        p, c = decode_rate(model, predictable, 0), decode_rate(model, creative, 1)
        verdict = "MTP active" if p / c >= 1.4 else "plain decoding"
        print(f"  {model:28} {p:9.1f} t/s {c:9.1f} t/s {p / c:6.2f}  {verdict}", flush=True)
        if "mtp" in model and p / c < 1.4:
            report("WARN", f"{model} is an MTP build but does not speculate here - compare with "
                           f"'./check.sh --bench {model.replace('-mtp', '').split('-q')[0]}' (README, 'Speed')")


if os.environ["BENCH_ONLY"]:
    bench(os.environ["BENCH_ONLY"].split())
    print("  (the configured models load again with the next question)")
    sys.exit(0)

print("Services")
try:
    _, v = call(OLLAMA, "/api/version", token=None, timeout=5)
    report("OK", f"Ollama {v.get('version')} on 127.0.0.1:11434")
except OSError as exc:
    report("FAIL", f"Ollama does not answer on 127.0.0.1:11434 ({exc}) - sudo systemctl status ollama")
    sys.exit(1)
try:
    status, _ = call(GATE, "/api/version", token=None, timeout=5)
    report("OK" if status == 401 else "FAIL", f"gate refuses requests without the token (HTTP {status})")
    status, _ = call(GATE, "/api/version", timeout=5)
    report("OK" if status == 200 else "FAIL", f"gate answers with the token on {GATE} (HTTP {status})")
except OSError as exc:
    report("FAIL", f"gate does not answer on {GATE} ({exc}) - sudo journalctl -u aichat-gate")
    sys.exit(1)

print("Models")
dims = None
for model in (CHAT, EMBED):
    status, show = call(GATE, "/api/show", {"model": model})
    if status != 200:
        report("FAIL", f"{model}: {show.get('error', status)} - pull it: ollama pull {model}")
        continue
    info = show.get("model_info", {})
    ctx = next((v for k, v in info.items() if k.endswith(".context_length")), None)
    report("OK" if ctx and ctx <= CAP else "FAIL", f"{model}: context reported to the plugin = {ctx} (cap {CAP})")
    if model == EMBED:
        dims = next((v for k, v in info.items() if k.endswith(".embedding_length")), None)
status, emb = call(GATE, "/api/embed", {"model": EMBED, "input": "Wie verbinde ich mich mit dem VPN?",
                                       "options": {"num_ctx": int(env.get("AICHAT_GATE_EMBED_CONTEXT_CAP", "8192"))}})
vector = (emb.get("embeddings") or [[]])[0]
report("OK" if vector and len(vector) == dims else "FAIL", f"embedding: {len(vector)} dimensions (expected {dims})")

print("Answers")
question = [{"role": "user", "content": "Was ist ein Wiki? Antworte in einem Satz."}]
started = time.monotonic()
status, reply = call(GATE, "/api/chat", {"model": CHAT, "stream": False, "messages": question})
message = reply.get("message", {})
rate = reply.get("eval_count", 0) / max(reply.get("eval_duration", 1) / 1e9, 1e-9)
if status == 200 and message.get("content", "").strip() and not message.get("thinking"):
    report("OK", f"answer without reasoning in {time.monotonic() - started:.1f} s ({rate:.0f} tokens/s): "
                 f"{message['content'].strip()[:80]}")
else:
    report("FAIL", f"answer without reasoning: HTTP {status}, {json.dumps(reply)[:200]}")

req = urllib.request.Request(GATE + "/api/chat", json.dumps(
    {"model": CHAT, "stream": True, "think": True, "messages": question}).encode(),
    {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
started, first_thought, first_word, thinking, answer = time.monotonic(), None, None, "", ""
try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        for line in resp:
            piece = json.loads(line).get("message", {})
            if piece.get("thinking"):
                thinking += piece["thinking"]
                first_thought = first_thought or time.monotonic() - started
            if piece.get("content"):
                answer += piece["content"]
                first_word = first_word or time.monotonic() - started
    if thinking and answer.strip():
        report("OK", f"streamed reasoning: first thought after {first_thought:.1f} s, {len(thinking)} characters, "
                     f"answer from {first_word:.1f} s, done after {time.monotonic() - started:.1f} s")
    else:
        report("FAIL", f"streamed reasoning: {len(thinking)} characters of reasoning, answer {answer[:80]!r}")
except (OSError, ValueError) as exc:
    report("FAIL", f"streamed reasoning: {exc}")

print("Speed (multi-token prediction)")
bench([CHAT])

print("GPU and CPU")
_, ps = call(OLLAMA, "/api/ps", token=None)
loaded = {m["name"].removesuffix(":latest") for m in ps.get("models", [])}
for model in (CHAT, EMBED):
    report("OK" if model.removesuffix(":latest") in loaded else "WARN", f"{model} loaded" if model.removesuffix(
        ":latest") in loaded else f"{model} is not loaded (it loads with the next question)")
for m in ps.get("models", []):
    if m.get("size_vram", 0) < m.get("size", 0) * 0.995:
        report("FAIL", f"{m['name']}: Ollama reports part of it outside GPU memory - slow; lower --context")


def ollama_cpu_ticks():
    total = 0
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/comm") as f:
                if not f.read().strip().startswith(("ollama", "llama")):
                    continue
            with open(f"/proc/{pid}/stat") as f:
                fields = f.read().rsplit(")", 1)[1].split()
            total += int(fields[11]) + int(fields[12])  # utime + stime
        except (OSError, IndexError, ValueError):
            pass
    return total


# An open Ollama report says idle runners keep CPU cores busy since 0.32.14.
time.sleep(2)
before = ollama_cpu_ticks()
time.sleep(3)
idle = 100 * (ollama_cpu_ticks() - before) / (3 * os.sysconf("SC_CLK_TCK"))
report("OK" if idle < 50 else "WARN", f"Ollama uses {idle:.0f}% of a CPU core while idle"
       + ("" if idle < 50 else " - see README, 'Troubleshooting'"))
sys.exit(1 if failed else 0)
PY
RESULT=$?
set -e

if [ -z "$BENCH_ONLY" ]; then
  if MEM="$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader 2>/dev/null)"; then
    printf '  \033[32mOK  \033[0m GPU memory used: %s\n' "$MEM"
  else
    printf '  \033[31mFAIL\033[0m nvidia-smi fails - after a driver update the machine needs a reboot\n'; RESULT=1
  fi
  # Ollama's /api/ps sizes are unreliable with its llama-server engine; the load log is not.
  LOG="$(sudo journalctl -u ollama --since "$STARTED" --no-pager 2>/dev/null || true)"
  OFFLOAD="$(printf '%s\n' "$LOG" | grep -oE 'offloaded [0-9]+/[0-9]+ layers to GPU' | sort -u || true)"
  PARTIAL="$(printf '%s\n' "$OFFLOAD" | awk -F'[ /]' 'NF && $2 != $3' | tr '\n' ' ')"
  if [ -z "$OFFLOAD" ]; then
    echo "       (no model was loaded during this check, so the Ollama log has no offload line)"
  elif [ -n "$PARTIAL" ]; then
    printf '  \033[31mFAIL\033[0m some layers run on the CPU (%s) - lower --context or pick a smaller model\n' "$PARTIAL"; RESULT=1
  else
    printf '  \033[32mOK  \033[0m all layers on the GPU (%s)\n' "$(printf '%s\n' "$OFFLOAD" | tr '\n' ' ')"
  fi
  ACCEPT="$(printf '%s\n' "$LOG" | grep -oE 'draft acceptance = [0-9.]+' | tail -n 3 | tr '\n' ' ' || true)"
  [ -n "$ACCEPT" ] && echo "       MTP in the Ollama log: $ACCEPT"
  if [ -f /var/run/reboot-required ]; then
    printf '  \033[33mWARN\033[0m an update is waiting for a reboot (%s)\n' "$(tr '\n' ' ' < /var/run/reboot-required.pkgs 2>/dev/null | cut -c1-80)"
  fi
fi
exit "$RESULT"
