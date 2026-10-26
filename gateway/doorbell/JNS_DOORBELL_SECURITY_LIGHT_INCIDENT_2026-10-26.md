# JNS Doorbell / Security Lighting Incident — 26 October 2026

**Reported approximately 19:28 UTC:** physical doorbell no longer functioning and security light triggering reportedly failing after the HA-Security VM906 diagnostic cold start / memory optimisation work.

**Status:** Both HA application-side chains are recording inputs and output state transitions. Physical sounder operation and physical exterior illumination have **NOT** been verified. Do not dismiss the user report solely on recorded entity states. The actual failure mechanism remains unresolved. No relay outputs or MQTT commands were artificially actuated during the incident audit.

## Verified telemetry

Sources: [read-only main incident audit](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40387476298), [causal timeline audit](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40387855422), [Zigbee2MQTT device survey](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40388174931).

- At **19:11:55–19:11:57 UTC** KC868 X15 `binary_sensor.alarmpanel_kc868_a16_x15` reported fresh OFF→ON button presses.
- At **19:11:55.410–19:11:58.394 UTC** `switch.alarmpanel_kc868_a16_y01` and its `siren.alarmpanel_kc868_a16_y01` wrapper reported ON for approximately 3 seconds, then OFF.
- HA-Security's `Doorbell DingDong 7am till 11pm`, `Publish Doorbell Press`, and sounder safety-off automation entities are registered and enabled. Their YAML exists in `packages/jns_security_doorbell_recovery.yaml`. HA-Security configuration includes packages and automation. MQTT integration is enabled.
- HA-Security is running and its configured ESPHome native API host **accepts TCP 6053** (the speculative `alarmpanel.home.arpa` alias did **not** resolve from Nodes A and B, but this did not block the configured endpoint during this audit).
- On HA-General, MQTT doorbell security lighting automation entity updated at **19:11:55–19:11:59 UTC**. The Garage Security Light Zigbee switch `switch.0x84fd27fffe9ce438` reported ON at 19:11:55. The Front Door Exterior `switch.0xa4c138bda6ec8ea0` reported ON at 19:11:55.
- Porch PIR `binary_sensor.0xa4c138b3446c34e1_occupancy` reported ON at **19:21:01 UTC**, with Garage Security Light reporting ON at 19:21:01. Both exterior light switch entities returned OFF at approximately **19:23:36 UTC**, consistent with automation timeouts.
- CT212 Mosquitto and CT214 Zigbee2MQTT services were active; all three target Zigbee routers were interviewed and present in the Z2M database, with last recorded linkquality 66 (garage), 75 (front exterior), 69 (front door light). Last known Z2M states were OFF / OFF / ON, respectively. Zigbee event journal has corresponding timestamps.
- HA-Security's recorder and automation data were inspected **read-only**. No files, device entities, pairings, relays, broker topics or automations were changed during incident audits.

## Interpretation and next non-invasive verification

The software event chain is not wholly broken. Recorded switch state is not proof of electrical relay contact closure, sounder power or bulb illumination; likewise, Zigbee target status may be optimistic or delayed. Need distinguish **physical sounder failure or wrong KC868 Y01 mapping** from **Zigbee relay / power supply / light hardware** and from missed edge cases or premature auto-off. This requires a supervised human observation of the physical chime and specific lights during a fresh press; do not trigger alarm/siren relays remotely without a safe controlled test.

Before making a physical fix: ask which component fails at the site (audible doorbell sounder, mobile alert, porch exterior lamp, Garage/Dogs Run lamp). While observer presses once, check whether sounder/relay clicks and whether both exterior lights illuminate. If no chime despite Y01 state ON, inspect relay mapping, low-voltage sounder supply and wiring using appropriate electrical safety rather than blindly altering automation IDs. If lights are not physically on despite reported Zigbee ON, verify Z2M acknowledgements, power and fixture connectivity without any automatic re-pairing.

## Safety

Preserve HA-Security's alarm and KC868 tamper functionality, HA-General lighting and MQTT/Zigbee ownership, all Home Assistant recorder databases and history. Do not restart VM906 or CT212/214 or remove device entries as speculative troubleshooting. Legacy Guardian01 CT115 and Guardian02 CT116 are retired, but the above automation paths do not depend on the old monolithic Guardian promotion system.
