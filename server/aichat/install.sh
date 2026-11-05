#!/usr/bin/env bash
# AI server for a DokuWiki's aichat plugin: NVIDIA driver, Ollama (localhost only), a chat
# and an embedding model, and aichat-gate - the one port the wiki server may reach. Nothing
# else from the lab stack (no Open WebUI, bot or reminders). Idempotent - safe to re-run; the
# gate's token is created once and kept.
#
#   git clone https://github.com/musallGroup/BrainLabLLM && cd BrainLabLLM/server/aichat
#   ./install.sh --wiki-server 192.168.1.20
#
# Run it as a normal user with sudo, not as root. See README.md in this folder.
#
# Options:
#   --wiki-server IP[,IP]   the DokuWiki server(s) allowed to reach the gate (port 11435);
#                           sets up ufw: SSH as configured, the gate only from these
#   --no-firewall           leave the firewall alone (then --wiki-server is not needed)
#   --chat-model NAME       default qwen3.5:9b-mtp-q4_K_M (with multi-token prediction)
#   --embed-model NAME      default bge-m3
#   --context N             context cap in tokens, default 32768
#   --no-auto-reboot        do not let automatic updates reboot at 03:30 when they need to
#   --update                only re-copy the gate from this checkout and restart it
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE=/etc/aichat-gate.env
GATE_DIR=/opt/aichat-gate
GATE_PORT=11435
REBOOT_CONF=/etc/apt/apt.conf.d/52aichat-auto-reboot
# The -mtp model builds need the llama.cpp engine Ollama bundles since mid-2026; tested with 0.32.14.
OLLAMA_MIN_VERSION=0.32.14
MODELS_FREE_GB=15

WIKI_SERVERS=""; FIREWALL=1; UPDATE=0; AUTO_REBOOT=1
CHAT_MODEL="qwen3.5:9b-mtp-q4_K_M"; EMBED_MODEL="bge-m3"; CONTEXT=32768
while [ $# -gt 0 ]; do
  case "$1" in
    --wiki-server) WIKI_SERVERS="${2:?--wiki-server needs an address}"; shift 2 ;;
    --no-firewall) FIREWALL=0; shift ;;
    --chat-model) CHAT_MODEL="${2:?--chat-model needs a name}"; shift 2 ;;
    --embed-model) EMBED_MODEL="${2:?--embed-model needs a name}"; shift 2 ;;
    --context) CONTEXT="${2:?--context needs a number}"; shift 2 ;;
    --no-auto-reboot) AUTO_REBOOT=0; shift ;;
    --update) UPDATE=1; shift ;;
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die()  { printf '\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "run as a normal user with sudo, not as root"
command -v sudo >/dev/null || die "sudo is required"
[[ "$CONTEXT" =~ ^[0-9]+$ ]] || die "--context needs a number of tokens"

install_gate() {
  step "aichat-gate"
  sudo install -D -m 644 "$HERE/aichat_gate.py" "$GATE_DIR/aichat_gate.py"
  sudo install -m 644 "$HERE/aichat-gate.service" /etc/systemd/system/aichat-gate.service
  sudo systemctl daemon-reload
  sudo systemctl enable aichat-gate.service >/dev/null 2>&1
  sudo systemctl restart aichat-gate.service
  sleep 1
  sudo systemctl is-active --quiet aichat-gate.service || die "aichat-gate did not start: sudo journalctl -u aichat-gate"
  note "listening on port $GATE_PORT"
}

if [ "$UPDATE" -eq 1 ]; then
  install_gate
  exit 0
fi

if [ "$FIREWALL" -eq 1 ]; then
  [ -n "$WIKI_SERVERS" ] || die "--wiki-server IP is required (the DokuWiki server that may use this machine), or pass --no-firewall"
  for ip in ${WIKI_SERVERS//,/ }; do
    [[ "$ip" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}(/[0-9]{1,2})?$ || "$ip" =~ ^[0-9a-fA-F:]+(/[0-9]{1,3})?$ ]] ||
      die "--wiki-server takes IP addresses (or subnets), not names: '$ip'"
  done
fi

step "Checking the system"
. /etc/os-release
[ "${ID:-}" = "ubuntu" ] || note "WARNING: written for Ubuntu; this is ${PRETTY_NAME:-unknown}"
note "OS: ${PRETTY_NAME:-unknown}   user: $USER"

step "System packages"
sudo apt-get update -y
sudo apt-get install -y curl ca-certificates python3 ufw pciutils unattended-upgrades

step "NVIDIA driver"
if ! nvidia-smi >/dev/null 2>&1; then
  if grep -qi nvidia <(lspci); then
    if grep -q '^ii' <(dpkg -l 'nvidia-driver-*' 2>/dev/null); then
      die "an NVIDIA driver is installed but nvidia-smi fails - usually a driver update without a reboot. Reboot, then run this again."
    fi
    note "No driver yet - installing the recommended one (the RTX 50 series needs the open kernel module, which ubuntu-drivers picks)."
    sudo apt-get install -y ubuntu-drivers-common
    sudo ubuntu-drivers install
    printf '\n\033[1mReboot now, then run ./install.sh again with the same options.\033[0m\n'
    printf 'If the screen after the reboot asks to "Enroll MOK" (Secure Boot), choose it and enter the password set during the driver install.\n'
    exit 0
  fi
  die "no NVIDIA GPU found (lspci)"
fi
note "GPU: $(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | head -n1)"

step "Automatic updates"
# Kernel and NVIDIA updates must land together: a new kernel's NVIDIA module requires the
# matching driver libraries, so holding the driver back would leave the next kernel without a
# GPU. Until the reboot after such an update, nvidia-smi fails (Ollama kept working on the lab
# server on 2026-11-05), so a reboot at night when an update asks for one keeps them in step.
if [ "$AUTO_REBOOT" -eq 1 ]; then
  printf '// aichat AI server (server/aichat/install.sh): reboot at 03:30 when an update needs it.\nUnattended-Upgrade::Automatic-Reboot "true";\nUnattended-Upgrade::Automatic-Reboot-WithUsers "true";\nUnattended-Upgrade::Automatic-Reboot-Time "03:30";\n' |
    sudo tee "$REBOOT_CONF" >/dev/null
  note "security updates install automatically; the machine reboots at 03:30 when one needs it"
else
  sudo rm -f "$REBOOT_CONF"
  note "updates install automatically; reboot by hand after kernel or driver updates (check.sh warns)"
fi

step "Ollama"
OLLAMA_HAVE="$(ollama --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | tail -n1 || true)"
if [ -z "$OLLAMA_HAVE" ] || [ "$(printf '%s\n%s\n' "$OLLAMA_MIN_VERSION" "$OLLAMA_HAVE" | sort -V | head -n1)" != "$OLLAMA_MIN_VERSION" ]; then
  [ -n "$OLLAMA_HAVE" ] && note "Ollama $OLLAMA_HAVE is older than $OLLAMA_MIN_VERSION - updating"
  curl -fsSL https://ollama.com/install.sh | sh
fi
sudo mkdir -p /etc/systemd/system/ollama.service.d
# localhost only: the wiki server goes through the gate. KEEP_ALIVE=-1 keeps both models in
# VRAM on this dedicated machine, so no question waits for a model load. CONTEXT_LENGTH is the
# default for calls that cannot send num_ctx (the OpenAI-style /v1 routes).
printf '[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\nEnvironment="OLLAMA_KEEP_ALIVE=-1"\nEnvironment="OLLAMA_MAX_LOADED_MODELS=2"\nEnvironment="OLLAMA_CONTEXT_LENGTH=%s"\n' "$CONTEXT" |
  sudo tee /etc/systemd/system/ollama.service.d/aichat.conf >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now ollama >/dev/null 2>&1
sudo systemctl restart ollama
for _ in $(seq 1 30); do curl -fs http://127.0.0.1:11434/api/version >/dev/null && break; sleep 1; done
curl -fs http://127.0.0.1:11434/api/version >/dev/null || die "Ollama did not come up on 127.0.0.1:11434"
note "Ollama $(ollama --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | tail -n1)"

step "Models (about 10 GB - this is the slow part)"
MODELS_DIR=/usr/share/ollama; [ -d "$MODELS_DIR" ] || MODELS_DIR=/
FREE_GB="$(df --output=avail -BG "$MODELS_DIR" | tail -n1 | tr -dc '0-9')"
[ "$FREE_GB" -ge "$MODELS_FREE_GB" ] || grep -q "^$CHAT_MODEL " <(ollama list 2>/dev/null) ||
  die "only ${FREE_GB} GB free on $MODELS_DIR; the models need about $MODELS_FREE_GB GB"
for model in "$CHAT_MODEL" "$EMBED_MODEL"; do note "ollama pull $model"; ollama pull "$model"; done

step "Gate configuration ($ENV_FILE)"
if sudo test -f "$ENV_FILE"; then
  note "kept the existing token"
else
  TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  (umask 077; printf 'AICHAT_GATE_TOKEN=%s\n' "$TOKEN" | sudo tee "$ENV_FILE" >/dev/null)
  note "created a new token"
fi
set_env() { # key value - replace or append one line, keeping the token and anything else
  sudo sed -i "/^$1=/d" "$ENV_FILE"
  printf '%s=%s\n' "$1" "$2" | sudo tee -a "$ENV_FILE" >/dev/null
}
set_env AICHAT_GATE_LISTEN "0.0.0.0:$GATE_PORT"
set_env AICHAT_GATE_CONTEXT_CAP "$CONTEXT"
set_env AICHAT_GATE_EMBED_CONTEXT_CAP 8192
set_env AICHAT_GATE_THINK false
# Not read by the gate - check.sh and the summary below take the model names from here.
set_env AICHAT_CHAT_MODEL "$CHAT_MODEL"
set_env AICHAT_EMBED_MODEL "$EMBED_MODEL"
sudo chmod 600 "$ENV_FILE"

install_gate

if [ "$FIREWALL" -eq 1 ]; then
  step "Firewall (ufw): SSH as now, the gate only from $WIKI_SERVERS"
  # Open the port sshd really listens on; guessing wrong would lock out whoever administers this.
  SSH_PORTS="$(sudo ss -ltnpH 2>/dev/null | awk '/"sshd"/ {n = split($4, a, ":"); print a[n]}' | sort -u)"
  [ -n "$SSH_PORTS" ] || { SSH_PORTS=22; note "WARNING: sshd is not running - allowing port 22 for when it is"; }
  for port in $SSH_PORTS; do sudo ufw allow "$port/tcp" >/dev/null; note "SSH port $port open"; done
  for ip in ${WIKI_SERVERS//,/ }; do
    sudo ufw allow from "$ip" to any port "$GATE_PORT" proto tcp >/dev/null
  done
  sudo ufw --force enable >/dev/null && note "ufw enabled"
fi

step "Self-test"
"$HERE/check.sh" || note "check.sh reported problems - see above and README.md, 'Troubleshooting'"

HOST_IP="$(hostname -I | awk '{print $1}')"
step "Done - settings for the wiki's aichat plugin (Admin -> Configuration Manager -> aichat)"
note "ollama_apiurl   http://${HOST_IP}:${GATE_PORT}/api   (or use this machine's DNS name)"
note "ollama_apikey   $(sudo sed -n 's/^AICHAT_GATE_TOKEN=//p' "$ENV_FILE")"
note "chatmodel       Ollama $CHAT_MODEL"
note "rephrasemodel   Ollama $CHAT_MODEL"
note "embedmodel      Ollama $EMBED_MODEL"
note "The token is stored only in $ENV_FILE (show it again: sudo grep TOKEN $ENV_FILE)."
