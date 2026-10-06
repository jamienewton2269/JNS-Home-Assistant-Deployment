#!/usr/bin/env bash
set -euo pipefail

BRIDGE_URL="${JNS_BRIDGE_URL:-http://127.0.0.1:8765}"
BIN="${CLOUDFLARED_BIN:-/usr/local/bin/cloudflared}"
STATE_DIR="/run/jns-management-bridge"
HOME_DIR="/var/lib/jns-management-bridge/cloudflared"
LOG="$STATE_DIR/tunnel.log"
PIDFILE="$STATE_DIR/tunnel.pid"
TOKEN_FILE="/etc/jns-management-bridge/token"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

install -d -m 0700 "$STATE_DIR" "$HOME_DIR"

if [[ ! -x "$BIN" ]]; then
  command -v curl >/dev/null || { apt-get update && apt-get install -y curl; }
  case "$(uname -m)" in
    x86_64|amd64) asset="amd64" ;;
    aarch64|arm64) asset="arm64" ;;
    armv7l|armhf) asset="arm" ;;
    *)
      echo "Unsupported architecture: $(uname -m)" >&2
      exit 1
      ;;
  esac
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' EXIT
  echo "Installing cloudflared from Cloudflare's GitHub release..."
  curl -fL --retry 3     "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${asset}"     -o "$tmp"
  install -m 0755 "$tmp" "$BIN"
fi

if [[ -f "$PIDFILE" ]]; then
  oldpid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "$oldpid" ]] && kill -0 "$oldpid" 2>/dev/null; then
    kill "$oldpid" || true
    sleep 1
  fi
fi

: > "$LOG"
HOME="$HOME_DIR" nohup "$BIN" tunnel --no-autoupdate --url "$BRIDGE_URL" >"$LOG" 2>&1 &
pid=$!
echo "$pid" > "$PIDFILE"

url=""
for _ in $(seq 1 30); do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "Tunnel process exited unexpectedly:" >&2
    cat "$LOG" >&2
    exit 1
  fi
  url="$(grep -Eo 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$LOG" | head -n1 || true)"
  [[ -n "$url" ]] && break
  sleep 1
done

if [[ -z "$url" ]]; then
  echo "Tunnel started but no public URL was found yet. Check:" >&2
  echo "  $LOG" >&2
  exit 1
fi

echo
echo "Temporary management URL:"
echo "$url"
echo
echo "Access token:"
cat "$TOKEN_FILE"
echo
echo
echo "Tunnel PID: $pid"
echo "Stop it with:"
echo "  sudo $(dirname "$0")/stop_temp_tunnel.sh"
