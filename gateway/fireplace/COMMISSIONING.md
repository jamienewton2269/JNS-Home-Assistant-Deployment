# Fireplace sensor commissioning — additive candidate only

2026-10-31. Not deployed. Source Zigbee2MQTT TS0201 IEEE `0xa4c138818d33ffff`, friendly label “Fireplace (Livingroom) thermometer”. Its HA entity IDs must be confirmed in the VM905 registry; expected candidates are `sensor.0xa4c138818d33ffff_temperature`, `_humidity`, `_battery` but are NOT confirmed. The screenshot shows Last seen **Disabled**, so enable availability monitoring and check reporting freshness.

## Key distinction
This sensor is near a heat source and should be used as a **fireplace heat indicator**, not blindly as the canonical ambient or house thermal-model training temperature. Obtain an independent living-room ambient sensor away from the fireplace and use the Honeywell control reference in the interim. Comparing two readings is not proof that a fire is lit; the classifier requires a rising gradient and emits conservative unknown status.

## Lighting integration proposal (NOT activated)
1. Inspect existing HA-General living-room automation, Lux/dusk state, light targets, manual override, and quiet/bedtime handling on VM905. Do not overwrite or duplicate existing automations.
2. Derive candidate `likely_on` from independent, fresh house reference and fire-side TS0201 with hysteresis / sustained qualification (at least 10 minutes for ON, 20 minutes for OFF). Unknown leaves lighting unchanged. Expose indicator + diagnostics on dashboard.
3. When lit **and** living-room lights are already permitted by existing dusk/manual-off logic, prefer a warm/dim scene, but NEVER turn lights on/off merely because the fireplace signal is unknown; retain explicit user override and bedtime precedence. Identify exact entities and scenes before coding integration.
4. Revert to current lighting behavior if sensors fail or after restart until fresh qualifications.

## Heating integration proposal (NOT activated)
- Add fireplace temperature, humidity and battery to monitoring and historical graphs, source attribution and event logs.
- Use a fireplace-heat flag to **exclude** fire-influenced windows from gas-heating thermal parameter estimation. Allow qualified fire heat as an explanatory *advisory* signal only.
- Do not let this fire-side sensor displace the Honeywell thermostat or adjust setpoints/optimum-start without independent room sensor calibration and the heating release gates.
- Preserve training sample schema, original history, Honeywell schedule (10:00 comfort 21°C; bedtime 18°C), away logic, and safety locks. No historical mixing of source epochs.
- Cross-check actual entity IDs and freshness using live HA-General MQTT/registry telemetry before installation.
- This is pure candidate logic. No root gateway approval or production restart is implicit.
