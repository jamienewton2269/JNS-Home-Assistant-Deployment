# JNS Shark RV2820 — local-only command research

## Objective
Replace the broken Shark IQ Home Assistant cloud integration with verified **LAN-only** start,
pause, dock, vacuum/mop and room/spot-selection controls for the RV2820. Do not assume
`sharklocal` mappings are compatible. Never claim captured TLS packets can simply be replayed.

## Ground truth so far
- The homeowner identified the model as **RV2820** (PowerDetect family).
- JNS October 25 read-only discovery found **zero** Shark integration entries and robot vacuum
  entities on HA902/HA905.
- The previously identified robot's LAN identity was confirmed by MAC-neighbour verification.
  Probes saw no open inbound listener on the tested HTTP(S)/MQTT ports.
- These port results do **not** identify the protocol of its **outbound** cloud connections.
- The existing SharkClean app may still operate the robot; do not reset the robot or break
  account pairing before making an independent local-control demonstration.

## Phase 1 — passive capture readiness (no traffic collection)
Run `.github/workflows/jns-rv2820-capture-readiness.yml`. It records only packet-capture
tool presence and interface names on Node C/A/B. It **cannot** prove visibility of switched
Wi-Fi traffic. Choose an authorised capture vantage at the AP, WAN gateway/router, or a
mirror/SPAN of the AP uplink. Do not place the vacuum in an unnecessary isolated VLAN or
change its DHCP/DNS as a shortcut. Respect JNS DNS-name-first policy.

## Phase 2 — observed packet captures (separate authorised step)
- Keep capture files **local and access-restricted** (e.g. `0700` directory, `0600` files);
  **never commit raw PCAPs or Shark account/robot identifiers to this public repository**.
- Capture robot traffic at an AP/gateway/SPAN interface that has proven actual packet
  visibility. Optionally collect phone traffic at the same boundary; phone and robot may
  be on different WLAN paths.
- Short, isolated commands with timestamp marks and a quiet baseline:
  1. Idle (no commands) and status refresh.
  2. Start dry/whole-house clean; pause; resume; dock.
  3. Start wet/mop (only when safely prepared), stop, dock.
  4. Select one mapped room, then a *different* room, then a multi-room mission.
  5. Select a spot/target (where supported).
- Capture entire connection setup around one run so TLS/DNS/SNI/ALPN and TCP sequence data
  are observable (metadata only without decryption). Avoid publishing credentials,
  home floor-plan coordinates, personal location identifiers and private room maps.

## Analysis decision
1. **Direct phone/controller → robot LAN flow**: determine whether the robot exposes an
   authenticated local endpoint; decode the command framing and reproduce the session
   legitimately. Replay only commands shown to work after a fresh session.
2. **Robot → Shark cloud only**: look for a client-initiated persistent TLS/MQTT or HTTPS
   session. Packet replay over the LAN cannot inject a cloud command into an already
   authenticated TLS session. Reproducing direct offline control may require a supported
   local interface or a replacement on-premises protocol/server; may be infeasible without
   firmware work. Clearly label this as unproven.
3. Validate a command with WAN access blocked in a controlled experiment **only after**
   identifying the actual transport and ensuring the robot can return to its dock.

## Intended JNS deployment architecture (pending proof)
- A lightweight RV2820 control service on an always-on JNS infra guest, **not** inside
  HA-Primary VM902 or on Node B if Solar Economy parks it.
- Expose a constrained localhost/LAN control API and MQTT discovery to HA-General,
  with DNS-name addressing, status/timeout handling and anti-repeat safeguards.
- Teach Steward the protocol and its validated repairs; deployments through the authorised
  GitHub gateway with backups, test/rollback and opt-in on-device commands.
- Never install a cloud bridge and label it `local`. The community shark2mqtt project
  is a **cloud** connector and therefore not the required end state.

## Operator safety
Capture readiness is non-invasive. Do not activate a span/mirror, change routing,
block the Internet, restart the robot, begin room cleaning, or send replayed messages
as part of preflight. All live tests require a later explicit operation.
