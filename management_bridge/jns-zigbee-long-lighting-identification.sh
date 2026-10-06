#!/usr/bin/env bash
# ==============================================================================
# JNS Zigbee Long Lighting Identification Test
# ==============================================================================
# PURPOSE
#   Performs a slow, sequential identification test of the mains-powered Zigbee
#   lighting devices currently registered in Zigbee2MQTT. Each candidate light
#   is switched ON individually for 20 seconds, then switched OFF for 5 seconds
#   before moving to the next device. This gives enough time to physically walk
#   around the property and identify which fitting corresponds to each Zigbee
#   IEEE address and whether that device is responding.
#
#   This extended version specifically includes the previously missed areas:
#     - Hall and Front Door IKEA bulbs
#     - Living Room Pendant IKEA bulb
#     - Treehouse lamp / treehouse door-light candidates
#     - Dogs-run / front security-light candidates
#     - Garage security light
#     - Garage interior lights
#     - Garage wall lights
#     - Summerhouse exterior wall lights
#     - Street lamp / external-light candidate
#     - Kitchen worktop and snug corner IKEA outlets
#     - Other known lighting relays from the recovered HA registry
#
# BEHAVIOUR
#   - One device at a time.
#   - ON for 20 seconds.
#   - OFF for 5 seconds.
#   - Approximate duration: 8 minutes for the full list.
#   - Every candidate receives an OFF command after its test.
#   - A final OFF sweep is sent to every candidate at the end.
#
# SAFETY / SCOPE
#   - Does NOT enable permit-join.
#   - Does NOT factory-reset, remove, re-pair or interview devices.
#   - Does NOT alter PAN/channel/network-key/coordinator settings.
#   - Excludes battery sensors/remotes, house-power monitor and water-feature
#     outlet.
#   - Door-control outlet is excluded from this lighting test.
#   - Ctrl-C aborts; rerun with "off" to send OFF to the complete test set.
#
# RUN LOCATION
#   Node C primary management/jump host.
#
# USAGE
#   sudo ./jns-zigbee-long-lighting-identification.sh
#   sudo ./jns-zigbee-long-lighting-identification.sh off
#
# DOCUMENTATION CATALOGUE DESCRIPTION
#   "Slow sequential Zigbee lighting identification test. Switches each known
#    mains-powered lighting candidate ON for 20 seconds and OFF for 5 seconds,
#    one device at a time, covering hall/front-door/living-room/treehouse,
#    garage, summerhouse and security lights without resetting or re-pairing."
# ==============================================================================

set -euo pipefail

MODE="${1:-run}"
case "$MODE" in
  run|off) ;;
  *) echo "Usage: $0 [off]" >&2; exit 2 ;;
esac

DOC_DIR="/home/github-runner/steward-web/docs"
DOC_CATALOG="$DOC_DIR/script-catalogue.txt"
DOC_LINE="jns-zigbee-long-lighting-identification.sh - Slow sequential Zigbee lighting identification test. Switches each known mains-powered lighting candidate ON for 20 seconds and OFF for 5 seconds, one device at a time, covering hall/front-door/living-room/treehouse, garage, summerhouse and security lights without resetting or re-pairing."
if [[ -d "$DOC_DIR" ]]; then
  touch "$DOC_CATALOG"
  tmp="$(mktemp)"
  grep -v '^jns-zigbee-long-lighting-identification\.sh - ' "$DOC_CATALOG" > "$tmp" || true
  printf '%s\n' "$DOC_LINE" >> "$tmp"
  cat "$tmp" > "$DOC_CATALOG"
  rm -f "$tmp"
fi

read -r -d '' JS <<'NODEJS' || true
const fs = require("fs");
const mqtt = require("mqtt");

const mode = process.argv[2] || "run";
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
  ["Tripod / colour bulb","0x003c84fffe1a695c"],
  ["Front Door IKEA bulb","0x5c0272fffe400903"],
  ["Hall IKEA bulb","0x847127fffe2890a6"],
  ["Living Room Pendant IKEA bulb","0x847127fffe28965b"],
  ["Unknown/Treehouse IKEA bulb candidate","0x84fd27fffe2bd920"],
  ["Kitchen Worktop IKEA socket","0x84fd27fffe9f52a4"],
  ["Snug Corner IKEA socket","0x84fd27fffe7040c9"],
  ["Garage Security IKEA socket","0x84fd27fffe9ce438"],
  ["Bathroom relay/light candidate","0xa4c13814ea8c8452"],
  ["Garage Interior Lights","0xa4c1382aab02d3bf"],
  ["Summerhouse Exterior Wall Lights","0xa4c13837acc3862a"],
  ["Downstairs WC relay","0xa4c13837e231806e"],
  ["AwoX / Treehouse lamp candidate","0xa4c13839b8995fbd"],
  ["Garage Wall Lights","0xa4c138807ef50f3c"],
  ["Kitchen Radiator Downlight","0xa4c13888eb407dfa"],
  ["Street Lamp / external security candidate","0xa4c1388ba234f2e3"],
  ["WC Extractor Fan relay","0xa4c138999d9f23eb"],
  ["Front/Dogs-run Security Light candidate","0xa4c138bda6ec8ea0"],
  ["ExtractorFan1 / lighting relay candidate","0xa4c138e3738a2d28"]
];

const client=mqtt.connect(server,{username,password});
const wait=(ms)=>new Promise(r=>setTimeout(r,ms));

function setState(ieee,state) {
  client.publish("zigbee2mqtt/"+ieee+"/set",JSON.stringify({state}));
}

client.on("error",e=>console.error("MQTT ERROR:",e.message));

client.on("connect",async()=>{
  console.log("JNS Zigbee Long Lighting Identification");
  console.log("Devices:",devices.length);

  if (mode==="off") {
    console.log("Sending OFF to every lighting candidate...");
    for (const [name,ieee] of devices) {
      console.log("OFF",name,ieee);
      setState(ieee,"OFF");
    }
    await wait(2500);
    client.end();
    return;
  }

  console.log("Each device: ON 20 sec, OFF 5 sec.");
  console.log("Approximate duration:",Math.ceil(devices.length*25/60),"minutes.");
  console.log("");

  let n=0;
  for (const [name,ieee] of devices) {
    n++;
    console.log("============================================================");
    console.log("DEVICE "+n+"/"+devices.length+": "+name);
    console.log("IEEE: "+ieee);
    console.log("ON for 20 seconds NOW");
    setState(ieee,"ON");
    await wait(20000);
    console.log("OFF: "+name);
    setState(ieee,"OFF");
    await wait(5000);
  }

  console.log("");
  console.log("Final OFF sweep...");
  for (const [,ieee] of devices) setState(ieee,"OFF");
  await wait(2500);

  console.log("TEST COMPLETE - all candidates commanded OFF.");
  client.end();
});
NODEJS

ENCODED="$(printf '%s' "$JS" | base64 -w0)"
sudo -u jns-mcp ssh -o BatchMode=yes node-b   "pct exec 214 -- bash -lc 'cd /opt/zigbee2mqtt && echo $ENCODED | base64 -d | /opt/node22/bin/node - $MODE'"
