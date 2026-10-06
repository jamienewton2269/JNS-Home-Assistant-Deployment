#!/usr/bin/env bash
# ==============================================================================
# JNS Zigbee Priority-Five Recovery Test
# ==============================================================================
# PURPOSE
#   Recovery/identification helper for the five currently confirmed non-working
#   mains-powered Zigbee lighting devices:
#     - Front Door IKEA bulb
#     - Hall IKEA bulb
#     - Living Room Pendant IKEA bulb
#     - Treehouse lamp IKEA bulb (historical identity still to confirm)
#     - Treehouse door light IKEA socket (historical identity still to confirm)
#
#   The script can run a read-oriented MQTT state probe or a short sequential
#   identification pulse. It does NOT reset, remove, re-pair or permit-join.
#
# MODES
#   probe     Ask each candidate for current state and listen for replies.
#   identify  Pulse each candidate ON for 5 seconds then OFF, one at a time,
#             so the physical device can be identified without affecting all
#             lighting simultaneously.
#   off       Send OFF to all five candidates.
#
# IMPORTANT IDENTITY NOTE
#   The first three IEEE addresses are confirmed from the recovered HA registry.
#   The two treehouse entries are current best historical candidates only:
#     old "DOWNSTAIRS TOILET" IKEA bulb -> possible relocated Treehouse lamp
#     old "Door" IKEA outlet            -> possible Treehouse door-light socket
#   Do not permanently rename those two until physical identification confirms.
#
# SAFETY
#   - No factory resets
#   - No permit-join
#   - No coordinator/PAN/network-key changes
#   - No database edits
#   - Final state after identify mode is OFF
#
# RUN LOCATION
#   Node C primary management host.
#
# USAGE
#   sudo ./jns-zigbee-priority-five-recovery-test.sh probe
#   sudo ./jns-zigbee-priority-five-recovery-test.sh identify
#   sudo ./jns-zigbee-priority-five-recovery-test.sh off
#
# DOCUMENTATION CATALOGUE DESCRIPTION
#   "Targeted recovery test for the five priority non-working IKEA Zigbee
#    lighting devices. Probes or sequentially pulses Front Door, Hall, Living
#    Room Pendant and two treehouse candidate devices without resetting,
#    re-pairing or opening the Zigbee network."
# ==============================================================================

set -euo pipefail

MODE="${1:-probe}"
case "$MODE" in
  probe|identify|off) ;;
  *) echo "Usage: $0 [probe|identify|off]" >&2; exit 2 ;;
esac

DOC_DIR="/home/github-runner/steward-web/docs"
DOC_CATALOG="$DOC_DIR/script-catalogue.txt"
DOC_LINE="jns-zigbee-priority-five-recovery-test.sh - Targeted recovery test for the five priority non-working IKEA Zigbee lighting devices. Probes or sequentially pulses Front Door, Hall, Living Room Pendant and two treehouse candidate devices without resetting, re-pairing or opening the Zigbee network."
if [[ -d "$DOC_DIR" ]]; then
  touch "$DOC_CATALOG"
  tmp="$(mktemp)"
  grep -v '^jns-zigbee-priority-five-recovery-test\.sh - ' "$DOC_CATALOG" > "$tmp" || true
  printf '%s\n' "$DOC_LINE" >> "$tmp"
  cat "$tmp" > "$DOC_CATALOG"
  rm -f "$tmp"
fi

read -r -d '' JS <<'NODEJS' || true
const fs = require("fs");
const mqtt = require("mqtt");

const mode = process.argv[2] || "probe";
const cfg = fs.readFileSync("/opt/zigbee2mqtt/data/configuration.yaml","utf8");

function value(key) {
  const re = new RegExp("^\\s*" + key + "\\s*:\\s*[\"']?([^\"'\\r\\n#]+)", "m");
  const m = cfg.match(re);
  return m ? m[1].trim() : undefined;
}

const server=value("server");
const username=value("user");
const password=value("password");
if (!server) throw new Error("MQTT server not found in Zigbee2MQTT configuration");

const devices=[
  ["Front Door IKEA bulb","0x5c0272fffe400903","confirmed"],
  ["Hall IKEA bulb","0x847127fffe2890a6","confirmed"],
  ["Living Room Pendant IKEA bulb","0x847127fffe28965b","confirmed"],
  ["Treehouse lamp IKEA bulb","0x84fd27fffe2bd920","candidate"],
  ["Treehouse door light IKEA socket","0x84fd27fffe6e0543","candidate"]
];

const client=mqtt.connect(server,{username,password});
const wait=(ms)=>new Promise(r=>setTimeout(r,ms));

client.on("error",e=>console.error("MQTT ERROR:",e.message));
client.on("message",(topic,payload)=>{
  console.log("RESPONSE",topic,payload.toString());
});

client.on("connect",async()=>{
  console.log("JNS Zigbee Priority-Five Recovery Test");
  console.log("Mode:",mode);
  for (const [name,ieee,identity] of devices) {
    console.log("DEVICE",identity,name,ieee);
    client.subscribe("zigbee2mqtt/"+ieee);
  }

  await wait(1000);

  if (mode==="probe") {
    for (const [name,ieee] of devices) {
      console.log("PROBE",name);
      client.publish("zigbee2mqtt/"+ieee+"/get",JSON.stringify({state:""}));
      await wait(1000);
    }
    console.log("Listening 20 seconds for replies...");
    await wait(20000);
  } else if (mode==="identify") {
    for (const [name,ieee,identity] of devices) {
      console.log("\nIDENTIFY",identity,name,ieee);
      client.publish("zigbee2mqtt/"+ieee+"/set",JSON.stringify({state:"ON"}));
      await wait(5000);
      client.publish("zigbee2mqtt/"+ieee+"/set",JSON.stringify({state:"OFF"}));
      await wait(3000);
    }
  } else {
    for (const [name,ieee] of devices) {
      console.log("OFF",name);
      client.publish("zigbee2mqtt/"+ieee+"/set",JSON.stringify({state:"OFF"}));
    }
    await wait(2000);
  }

  client.end();
});
NODEJS

ENCODED="$(printf '%s' "$JS" | base64 -w0)"
sudo -u jns-mcp ssh -o BatchMode=yes node-b   "pct exec 214 -- bash -lc 'cd /opt/zigbee2mqtt && echo $ENCODED | base64 -d | /opt/node22/bin/node - $MODE'"
