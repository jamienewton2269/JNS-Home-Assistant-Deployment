#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="/run/jns-management-bridge"
PIDFILE="$STATE_DIR/tunnel.pid"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

if [[ -f "$PIDFILE" ]]; then
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "Stopped temporary tunnel (PID $pid)."
  else
    echo "Tunnel is not running."
  fi
  rm -f "$PIDFILE"
else
  echo "No tunnel PID file found."
fi
