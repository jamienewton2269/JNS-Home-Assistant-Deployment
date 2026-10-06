#!/usr/bin/env bash
# ==============================================================================
# JNS Zigbee Rain/Lux Sensor Readiness Check
# ==============================================================================
# PURPOSE
#   Verifies whether the external Zigbee rain sensor currently registered as
#   IEEE 0xa4c1383917c90309 (historical HA name: RainSensor, model ZG-223Z)
#   is ready to be used in Home Assistant automations.
#
#   The check reports:
#     - whether Zigbee2MQTT still has the device registered;
#     - the Zigbee2MQTT "exposes" list for the device;
#     - whether rain/wet/dry and illuminance/lux-related properties exist;
#     - the latest retained/current MQTT state seen for the device;
#     - recent Zigbee2MQTT log activity for this IEEE address.
#
# SAFETY / SCOPE
#   - Read-only diagnostic.
#   - Does NOT reset, remove, re-pair or interview the device.
#   - Does NOT enable permit-join.
#   - Does NOT alter Zigbee coordinator/network configuration.
#   - Does NOT change Home Assistant configuration.
#
# RUN LOCATION
#   Node C primary management/jump host.
#
# USAGE
#   sudo ./jns-zigbee-rain-lux-readiness-check.sh
#
# DOCUMENTATION CATALOGUE DESCRIPTION
#   "Read-only readiness check for the external Zigbee rain/lux sensor
#    (0xa4c1383917c90309 / ZG-223Z). Shows Zigbee2MQTT exposed properties,
#    current MQTT state and recent activity to confirm whether rain and lux
#    values are available for Home Assistant automations."
# ==============================================================================

set -euo pipefail

DOC_DIR="/home/github-runner/steward-web/docs"
DOC_CATALOG="$DOC_DIR/script-catalogue.txt"
DOC_LINE="jns-zigbee-rain-lux-readiness-check.sh - Read-only readiness check for the external Zigbee rain/lux sensor (0xa4c1383917c90309 / ZG-223Z). Shows Zigbee2MQTT exposed properties, current MQTT state and recent activity to confirm whether rain and lux values are available for Home Assistant automations."
if [[ -d "$DOC_DIR" ]]; then
  touch "$DOC_CATALOG"
  tmp="$(mktemp)"
  grep -v '^jns-zigbee-rain-lux-readiness-check\.sh - ' "$DOC_CATALOG" > "$tmp" || true
  printf '%s\n' "$DOC_LINE" >> "$tmp"
  cat "$tmp" > "$DOC_CATALOG"
  rm -f "$tmp"
fi

read -r -d '' JS <<'NODEJS' || true
const fs = require("fs");
const mqtt = require("mqtt");

const ieee="0xa4c1383917c90309";
const cfg=fs.readFileSync("/opt/zigbee2mqtt/data/configuration.yaml","utf8");

function value(key) {
  const re=new RegExp("^\\s*"+key+"\\s*:\\s*[\"']?([^\"'\\r\\n#]+)","m");
  const m=cfg.match(re);
  return m ? m[1].trim() : undefined;
}

const server=value("server");
const username=value("user");
const password=value("password");
if (!server) throw new Error("MQTT server not found");

const client=mqtt.connect(server,{username,password});
let gotDevices=false;
let gotState=false;

function flattenExpose(ex, out=[]) {
  if (!ex) return out;
  if (Array.isArray(ex)) {
    for (const x of ex) flattenExpose(x,out);
    return out;
  }
  if (typeof ex==="object") {
    if (ex.property) out.push({
      property:ex.property,
      name:ex.name,
      type:ex.type,
      unit:ex.unit,
      access:ex.access
    });
    if (ex.features) flattenExpose(ex.features,out);
  }
  return out;
}

client.on("connect",()=>{
  console.log("=== RAIN/LUX SENSOR READINESS CHECK ===");
  console.log("IEEE:",ieee);
  client.subscribe("zigbee2mqtt/bridge/devices");
  client.subscribe("zigbee2mqtt/"+ieee);
  setTimeout(()=>{
    if (!gotDevices) console.log("No bridge/devices payload received.");
    if (!gotState) console.log("No retained/current device state received.");
    client.end();
  },12000);
});

client.on("message",(topic,payload)=>{
  if (topic==="zigbee2mqtt/bridge/devices") {
    gotDevices=true;
    let arr;
    try { arr=JSON.parse(payload.toString()); } catch(e) {
      console.log("Unable to parse bridge/devices:",e.message); return;
    }
    const d=arr.find(x => String(x.ieee_address||x.ieeeAddr||"").toLowerCase()===ieee.toLowerCase());
    if (!d) {
      console.log("REGISTERED: NO");
      return;
    }
    console.log("REGISTERED: YES");
    console.log("friendly_name:",d.friendly_name);
    console.log("model_id:",d.model_id||d.definition?.model||"");
    console.log("manufacturer:",d.manufacturer||d.definition?.vendor||"");

    const props=flattenExpose(d.definition?.exposes||d.exposes||[]);
    console.log("\nEXPOSED PROPERTIES:");
    for (const p of props) {
      console.log(" -",JSON.stringify(p));
    }

    const names=props.map(p=>String(p.property||p.name||"").toLowerCase());
    const lux=names.filter(n=>n.includes("illumin")||n.includes("lux"));
    const rain=names.filter(n=>n.includes("rain")||n.includes("wet")||n.includes("dry"));
    console.log("\nAUTOMATION CAPABILITIES:");
    console.log(" lux/illuminance:",lux.length ? lux.join(", ") : "NOT EXPOSED");
    console.log(" rain/wet/dry:",rain.length ? rain.join(", ") : "NOT EXPOSED");
  } else if (topic==="zigbee2mqtt/"+ieee) {
    gotState=true;
    console.log("\nCURRENT/RETAINED STATE:");
    console.log(payload.toString());
  }
});

client.on("error",e=>{
  console.error("MQTT ERROR:",e.message);
  process.exitCode=1;
});
NODEJS

ENCODED="$(printf '%s' "$JS" | base64 -w0)"
sudo -u jns-mcp ssh -o BatchMode=yes node-b   "pct exec 214 -- bash -lc 'cd /opt/zigbee2mqtt && echo $ENCODED | base64 -d | /opt/node22/bin/node -'"

echo
echo "=== RECENT Z2M LOG ACTIVITY FOR RAIN SENSOR ==="
sudo -u jns-mcp ssh -o BatchMode=yes node-b   "pct exec 214 -- journalctl -u zigbee2mqtt --since '2026-10-06 07:38:00' --no-pager | grep -i 'a4c1383917c90309' | tail -30 || true"
