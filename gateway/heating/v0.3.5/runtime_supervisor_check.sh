#!/bin/sh
# Read-only VM905 heating runtime attestation from existing SSH add-on.
# SUPERVISOR_TOKEN stays solely inside its existing privileged container.
set -e
[ -n "$SUPERVISOR_TOKEN" ] || { echo JNS_HEATING_SUPERVISOR_DENIED; exit 2; }
command -v curl >/dev/null 2>&1 || { echo JNS_HEATING_CURL_MISSING; exit 2; }
command -v jq >/dev/null 2>&1 || { echo JNS_HEATING_JQ_MISSING; exit 2; }
BASE='http://supervisor/core/api/states'
AUTH="Authorization: Bearer $SUPERVISOR_TOKEN"
climate='climate.thermostat_thermostat'
indoor='sensor.thermostat_thermostat_indoor_temperature'
call='binary_sensor.lyric_home_heating_heating_call'
learner='sensor.lyric_home_heating_thermal_learning'
check_entity() {
    ent="$1"
    data="$(curl -fsS -m 8 -H "$AUTH" "$BASE/$ent" 2>/dev/null)" || return 1
    printf '%s' "$data" | jq -e --arg e "$ent" '.entity_id == $e' >/dev/null 2>&1 || return 1
    case "$ent" in
      "$climate")
        printf '%s' "$data" | jq -e '.state != "unavailable" and .state != "unknown" and .state != "" and .state != null' >/dev/null 2>&1
        ;;
      "$indoor")
        printf '%s' "$data" | jq -e '(.state | tonumber) | . > -30 and . < 60' >/dev/null 2>&1
        ;;
      "$call")
        printf '%s' "$data" | jq -e '.state=="on" or .state=="off"' >/dev/null 2>&1
        ;;
      "$learner")
        return 0
        ;;
      *) return 2 ;;
    esac
}
for entity in "$climate" "$indoor" "$call" "$learner"; do
    if ! check_entity "$entity"; then
        case "$entity" in
          "$climate") label=climate ;;
          "$indoor") label=indoor_sensor ;;
          "$call") label=heating_call ;;
          "$learner") label=learner ;;
          *) label=unknown ;;
        esac
        echo "JNS_HEATING_RUNTIME_BLOCKED essential_entity_unverified:$label"
        exit 2
    fi
done
echo 'JNS_HEATING_RUNTIME_AUTHENTICATED_READY'
