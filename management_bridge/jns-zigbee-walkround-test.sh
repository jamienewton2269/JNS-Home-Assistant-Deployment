#!/usr/bin/env bash
# ==============================================================================
# JNS Zigbee Walk-Round Identification Test
# ==============================================================================
# PURPOSE
#   Performs a supervised one-minute identification test of the mains-powered
#   Zigbee lighting, relay and extractor/fan devices currently registered in
#   Zigbee2MQTT. Selected devices are commanded ON and OFF together every
#   10 seconds so a person can walk around the property and identify which
#   physical devices are responding and where historically renamed devices
#   are now located.
#
# BEHAVIOUR
#   Sequence: ON -> OFF -> ON -> OFF -> ON -> OFF
#   Interval: 10 seconds
#   Duration: approximately 1 minute
#   Final commanded state: OFF
#
# SAFETY / SCOPE
#   - Does NOT enable permit-join.
#   - Does NOT reset, remove, re-pair or interview devices.
#   - Does NOT alter coordinator/PAN/network-key configuration.
#   - Excludes battery sensors/remotes and deliberately excluded outlets such
#     as water-feature/door control and the house power monitor.
#   - Ctrl-C aborts immediately; use --off-only afterwards if required.
#
# RUN LOCATION
#   Node C primary management/jump host.
#
# DEPENDENCIES
#   Node C -> Node B SSH alias "node-b" for jns-mcp.
#   Node B CT214 running Zigbee2MQTT.
#
# USAGE
#   sudo ./jns-zigbee-walkround-test.sh
#   sudo ./jns-zigbee-walkround-test.sh --off-only
#
# DOCUMENTATION CATALOGUE DESCRIPTION
#   "One-minute supervised Zigbee walk-round test. Pulses selected mains-powered
#    lights, relays and extractor/fan devices ON/OFF every 10 seconds to identify
#    which physical Zigbee devices are online and where they are located,
#    without resetting or re-pairing anything."
# ==============================================================================

set -euo pipefail

DOC_DIR="/home/github-runner/steward-web/docs"
DOC_CATALOG="$DOC_DIR/script-catalogue.txt"
DOC_LINE="jns-zigbee-walkround-test.sh - One-minute supervised Zigbee walk-round test. Pulses selected mains-powered lights, relays and extractor/fan devices ON/OFF every 10 seconds to identify which physical Zigbee devices are online and where they are located, without resetting or re-pairing anything."

if [[ -d "$DOC_DIR" ]]; then
  touch "$DOC_CATALOG"
  tmp="$(mktemp)"
  grep -v '^jns-zigbee-walkround-test\.sh - ' "$DOC_CATALOG" > "$tmp" || true
  printf '%s\n' "$DOC_LINE" >> "$tmp"
  cat "$tmp" > "$DOC_CATALOG"
  rm -f "$tmp"
fi

MODE="${1:-run}"
if [[ "$MODE" != "run" && "$MODE" != "--off-only" ]]; then
  echo "Usage: $0 [--off-only]" >&2
  exit 2
fi

NODE_B="node-b"
CT=214

read -r -d '' JS <<'NODEJS' || true
const fs = require("fs");
const mqtt = require("mqtt");

const mode = process.argv[2] || "run";
const text = fs.readFileSync("/opt/zigbee2mqtt/data/configuration.yaml","utf8");

function value(key) {
  const re = new RegExp("^\\s*" + key + "\\s*:\\s*[\"']?([^\"'\\r\\n#]+)", "m");
  const m = text.match(re);
  return m ? m[1].trim() : undefined;
}

const server = value("server");
const username = value("user");
const password = value("password");
if (!server) {
  console.error("Unable to read MQTT server from Zigbee2MQTT configuration.");
  process.exit(1);
}

const devices = {
  "Tripod bulb":            "0x003c84fffe1a695c",
  "Front Door bulb":        "0x5c0272fffe400903",
  "Hall bulb":              "0x847127fffe2890a6",
  "Pendant bulb":           "0x847127fffe28965b",
  "Unknown IKEA bulb":      "0x84fd27fffe2bd920",
  "Corner light":           "0x84fd27fffe7040c9",
  "Garage security light":  "0x84fd27fffe9ce438",
  "Worktop downlight":      "0x84fd27fffe9f52a4",
  "Bathroom1":              "0xa4c13814ea8c8452",
  "Garage interior lights": "0xa4c1382aab02d3bf",
  "Summerhouse exterior":   "0xa4c13837acc3862a",
  "Downstairs WC relay":    "0xa4c13837e231806e",
  "AwoX pendant":           "0xa4c13839b8995fbd",
  "Garage wall lights":     "0xa4c138807ef50f3c",
  "Radiator downlight":     "0xa4c13888eb407dfa",
  "Street lamp":            "0xa4c1388ba234f2e3",
  "WC extractor fan":       "0xa4c138999d9f23eb",
  "SecurityLight1":         "0xa4c138bda6ec8ea0",
  "ExtractorFan1":          "0xa4c138e3738a2d28"
};

const client = mqtt.connect(server, {username, password});

function publish(state) {
  console.log("=== " + state + " ===");
  for (const [name, ieee] of Object.entries(devices)) {
    console.log("  " + name);
    client.publish("zigbee2mqtt/" + ieee + "/set", JSON.stringify({state}));
  }
}

client.on("connect", () => {
  if (mode === "--off-only") {
    publish("OFF");
    setTimeout(() => client.end(), 2000);
    return;
  }

  console.log("JNS Zigbee walk-round test started.");
  console.log("Six pulses at 10-second intervals; final state OFF.");

  let pulse = 0;
  const run = () => {
    pulse += 1;
    const state = pulse % 2 ? "ON" : "OFF";
    console.log("\nPULSE " + pulse + "/6");
    publish(state);
    if (pulse === 6) {
      clearInterval(timer);
      setTimeout(() => {
        console.log("\nTEST COMPLETE - final command OFF.");
        client.end();
      }, 2000);
    }
  };

  run();
  const timer = setInterval(run, 10000);
});

client.on("error", (e) => {
  console.error("MQTT ERROR:", e.message);
  process.exitCode = 1;
});
NODEJS

ENCODED="$(printf '%s' "$JS" | base64 -w0)"
ssh -o BatchMode=yes jns-mcp@"$NODE_B"   "pct exec $CT -- bash -lc 'cd /opt/zigbee2mqtt && echo $ENCODED | base64 -d | /opt/node22/bin/node - $MODE'"
