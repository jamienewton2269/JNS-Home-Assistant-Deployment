#!/bin/sh
# JNS HA-Security VM906 guarded doorbell recovery installer (run in core-ssh).
# Modes: audit (read-only) or install (backed up, validated; NO reload/restart).
set -eu
umask 077

BASE=/homeassistant
[ -f "$BASE/configuration.yaml" ] || BASE=/config
REGISTRY="$BASE/.storage/core.entity_registry"
ENTRIES="$BASE/.storage/core.config_entries"
AUTOS="$BASE/automations.yaml"
PACKAGE_DIR="$BASE/packages"
TARGET="$PACKAGE_DIR/jns_security_doorbell_recovery.yaml"
BACKUPS="$BASE/.jns_doorbell_backups"
SOURCE="https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/563d6cf84c1b847bd3621119c4df0cb0f0592da0/gateway/doorbell/jns_ha_security_doorbell_recovery.yaml"
MODE="${1:-audit}"

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "REFUSE: missing required tool $1" >&2
    exit 2
  }
}
require jq
require grep
require curl
require ha

registered() {
  jq -e --arg eid "$1" '.data.entities | any(.entity_id == $eid and .disabled_by == null)' "$REGISTRY" >/dev/null
}

preflight() {
  [ -f "$REGISTRY" ] || { echo "REFUSE: HA-Security entity registry missing"; exit 2; }
  [ -f "$ENTRIES" ] || { echo "REFUSE: HA-Security integration registry missing"; exit 2; }
  [ -f "$AUTOS" ] || { echo "REFUSE: automations.yaml missing"; exit 2; }
  [ -d "$PACKAGE_DIR" ] || { echo "REFUSE: HA-Security packages directory missing"; exit 2; }

  for eid in \
    binary_sensor.alarmpanel_kc868_a16_x15 \
    siren.alarmpanel_kc868_a16_y01 \
    schedule.daytime \
    automation.doorbell_sounder_on_schedule \
    automation.jns_security_publish_doorbell_press; do
    if registered "$eid"; then
      echo "REGISTERED $eid"
    else
      echo "REFUSE: missing or disabled $eid" >&2
      exit 3
    fi
  done
  echo "=== HA-SECURITY INTEGRATIONS (non-secret) ==="
  jq -r '.data.entries[]? | select(.domain=="mqtt" or .domain=="esphome") |
    [.domain, (.title // ""), (.disabled_by // "enabled")] | @tsv' "$ENTRIES"
  if jq -e '[.data.entries[]? | select(.domain=="mqtt" and .disabled_by==null)] | length > 0' "$ENTRIES" >/dev/null; then
    echo "MQTT_INTEGRATION_ENABLED=yes"
  else
    echo "MQTT_INTEGRATION_ENABLED=no"
    echo "REFUSE: MQTT publish integration not configured on HA-Security" >&2
    exit 4
  fi
  echo "AUTOMATIONS_YAML_BYTES=$(wc -c < "$AUTOS" | tr -d ' ')"
  if [ -s "$AUTOS" ]; then
    echo "REFUSE: automations.yaml is no longer empty; inspect before restoring" >&2
    exit 5
  fi
  for id in 1792316952337 1792512302559 jns_security_doorbell_siren_safety_off_v1; do
    if grep -R -F -q -- "$id" "$PACKAGE_DIR" "$AUTOS" 2>/dev/null; then
      echo "REFUSE: automation $id is already defined in YAML" >&2
      exit 6
    fi
  done
  if [ -e "$TARGET" ]; then
    echo "REFUSE: target package file already exists" >&2
    exit 7
  fi
  echo "DOORBELL_RECOVERY_PREFLIGHT_OK"
}

case "$MODE" in
  audit)
    preflight
    echo "READ_ONLY_AUDIT_COMPLETE: no files or HA state changed"
    ;;
  install)
    preflight
    require mktemp
    require cp
    require mv
    [ ! -e "$TARGET" ] || { echo "REFUSE: package target exists"; exit 7; }
    mkdir -p "$BACKUPS"
    STAMP=$(date -u +%Y%m%dT%H%M%SZ)
    BK="$BACKUPS/automations.yaml.before-recovery.$STAMP"
    [ ! -e "$BK" ] || { echo "REFUSE: backup name collision"; exit 8; }
    cp -p "$AUTOS" "$BK"
    STAGED=$(mktemp "$PACKAGE_DIR/.jns-security-doorbell.XXXXXX")
    trap 'rm -f "$STAGED"' EXIT HUP INT TERM
    echo "Retrieving commit-pinned YAML package..."
    curl -fsSL --connect-timeout 10 --max-time 40 "$SOURCE" -o "$STAGED"
    [ -s "$STAGED" ] || { echo "REFUSE: empty package"; exit 9; }
    for id in 1792316952337 1792512302559 jns_security_doorbell_siren_safety_off_v1; do
      grep -Fq "$id" "$STAGED" || { echo "REFUSE: invalid payload missing $id"; exit 10; }
    done
    mv "$STAGED" "$TARGET"
    trap - EXIT HUP INT TERM
    echo "Running HA-Security config check — no restart..."
    if ha core check; then
      echo "JNS_DOORBELL_CONFIG_VALIDATED"
      echo "PACKAGE=$TARGET"
      echo "AUTOMATIONS_BACKUP=$BK"
      echo "NOT_ACTIVE_UNTIL_AUTOMATION_RELOAD"
      echo "Use HA-Security Developer Tools > YAML > Reload Automations."
    else
      echo "VALIDATION_FAILED: removing new package, leaving original config intact" >&2
      rm -f "$TARGET"
      echo "ROLLBACK_SUCCEEDED"
      exit 11
    fi
    ;;
  *)
    echo "Usage: sh $0 audit|install" >&2
    exit 2
    ;;
esac
