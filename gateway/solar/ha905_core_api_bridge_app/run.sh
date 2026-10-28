#!/command/with-contenv bashio
set -e
if [[ -z "${SUPERVISOR_TOKEN:-}" ]]; then
    echo 'JNS_HA905_CORE_PREFLIGHT=supervisor_token_missing'
    exit 2
fi
exec python3 /opt/jns/probe.py
