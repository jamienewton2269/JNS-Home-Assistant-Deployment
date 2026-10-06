#!/usr/bin/env bash
# ==============================================================================
# JNS Zigbee Single-Device Lighting Control Helper
# ==============================================================================
# PURPOSE
#   Sends an ON or OFF command to ONE approved mains-powered Zigbee lighting
#   device through the existing Node C -> Node B -> Zigbee2MQTT path.
#
#   This is the narrow control helper used by the phone walk-round tester.
#   It may also be used manually when identifying or recovering a light.
#
# SAFETY / SCOPE
#   - Only IEEE addresses in the lighting allow-list below are accepted.
#   - Only ON and OFF are accepted; no arbitrary MQTT payloads are possible.
#   - "all-off" sends OFF to every allow-listed lighting candidate.
#   - Does NOT enable permit-join, reset, remove, re-pair or interview devices.
#   - Does NOT alter PAN/channel/network-key/coordinator configuration.
#   - Water-feature, house-power, door-control and battery devices are excluded.
#
# RUN LOCATION
#   Node C primary management/jump host.
#
# USAGE
#   jns-zigbee-device-control.sh 0x5c0272fffe400903 ON
#   jns-zigbee-device-control.sh 0x5c0272fffe400903 OFF
#   jns-zigbee-device-control.sh all-off
#
# DOCUMENTATION CATALOGUE DESCRIPTION
#   "Restricted single-device Zigbee lighting control helper used by the phone
#    walk-round tester. Sends only ON/OFF to an approved lighting allow-list,
#    with an emergency all-off mode; cannot reset or re-pair devices."
# ==============================================================================

set -euo pipefail

ALLOWED=(
  0x003c84fffe1a695c
  0x5c0272fffe400903
  0x847127fffe2890a6
  0x847127fffe28965b
  0x84fd27fffe2bd920
  0x84fd27fffe7040c9
  0x84fd27fffe9ce438
  0x84fd27fffe9f52a4
  0xa4c13814ea8c8452
  0xa4c1382aab02d3bf
  0xa4c13837acc3862a
  0xa4c13837e231806e
  0xa4c13839b8995fbd
  0xa4c138807ef50f3c
  0xa4c13888eb407dfa
  0xa4c1388ba234f2e3
  0xa4c138bda6ec8ea0
)

catalogue() {
  local dir="/home/github-runner/steward-web/docs"
  local file="$dir/script-catalogue.txt"
  local line="jns-zigbee-device-control.sh - Restricted single-device Zigbee lighting control helper used by the phone walk-round tester. Sends only ON/OFF to an approved lighting allow-list, with an emergency all-off mode; cannot reset or re-pair devices."
  if [[ -d "$dir" ]]; then
    touch "$file"
    local tmp
    tmp="$(mktemp)"
    grep -v '^jns-zigbee-device-control\.sh - ' "$file" > "$tmp" || true
    printf '%s\n' "$line" >> "$tmp"
    cat "$tmp" > "$file"
    rm -f "$tmp"
  fi
}
catalogue

if [[ "\${1:-}" == "all-off" ]]; then
  TARGETS="$(IFS=,; echo "\${ALLOWED[*]}")"
  STATE="OFF"
elif [[ $# -eq 2 ]]; then
  IEEE="\${1,,}"
  STATE="\${2^^}"
  [[ "$STATE" == "ON" || "$STATE" == "OFF" ]] || {
    echo "State must be ON or OFF" >&2
    exit 2
  }
  ok=0
  for x in "\${ALLOWED[@]}"; do
    [[ "$IEEE" == "$x" ]] && ok=1 && break
  done
  [[ $ok -eq 1 ]] || {
    echo "IEEE address is not in the JNS lighting test allow-list: $IEEE" >&2
    exit 3
  }
  TARGETS="$IEEE"
else
  echo "Usage: $0 <approved-ieee> <ON|OFF> | all-off" >&2
  exit 2
fi

read -r -d '' JS <<'NODEJS' || true
const fs = require("fs");
const mqtt = require("mqtt");

const cfg = fs.readFileSync("/opt/zigbee2mqtt/data/configuration.yaml","utf8");
const targets = String(process.env.JNS_TARGETS || "").split(",").filter(Boolean);
const state = String(process.env.JNS_STATE || "").toUpperCase();

function value(key) {
  const re = new RegExp("^\\s*" + key + "\\s*:\\s*[\"']?([^\"'\\r\\n#]+)", "m");
  const m = cfg.match(re);
  return m ? m[1].trim() : undefined;
}

const server=value("server");
const username=value("user");
const password=value("password");

if (!server || !targets.length || !["ON","OFF"].includes(state)) {
  console.error("Invalid controller configuration");
  process.exit(2);
}

const client=mqtt.connect(server,{username,password});
let finished=false;
const fail=setTimeout(()=>{
  if (!finished) {
    console.error("MQTT publish timeout");
    process.exit(4);
  }
},7000);

client.on("error",e=>{
  console.error("MQTT error:",e.message);
  clearTimeout(fail);
  process.exit(5);
});

client.on("connect",()=>{
  let pending=targets.length;
  for (const ieee of targets) {
    client.publish("zigbee2mqtt/"+ieee+"/set",JSON.stringify({state}),{qos:0},err=>{
      if (err) {
        console.error("Publish failed for",ieee,err.message);
        clearTimeout(fail);
        process.exit(6);
      }
      console.log(ieee,state);
      pending--;
      if (pending===0) {
        finished=true;
        clearTimeout(fail);
        setTimeout(()=>client.end(),300);
      }
    });
  }
});
NODEJS

ENCODED="$(printf '%s' "$JS" | base64 -w0)"
sudo -u jns-mcp ssh -o BatchMode=yes node-b \
  "pct exec 214 -- env JNS_TARGETS='$TARGETS' JNS_STATE='$STATE' bash -lc 'cd /opt/zigbee2mqtt && echo $ENCODED | base64 -d | /opt/node22/bin/node -'"
