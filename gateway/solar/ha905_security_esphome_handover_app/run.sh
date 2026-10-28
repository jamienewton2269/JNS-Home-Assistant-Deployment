#!/command/with-contenv bashio
set -e
if [[ -z "${SUPERVISOR_TOKEN:-}" ]]; then
  echo 'JNS_ESP_HANDOVER_BLOCKED=supervisor_token_unavailable'
  exit 2
fi
exec python3 /opt/jns/flow.py
