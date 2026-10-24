# JNS Heating Zones — Summer House TS0201 external temperature candidate

**Recorded:** 24 October 2026. **Status: identity verified, source switch NOT applied.**

## Verified HA-General identity

- Device name: Summer House Sensor
- Zigbee IEEE: `0xa4c13880bb5cffff`
- Model: Tuya TS0201, Temperature & humidity sensor with display
- Transport: Zigbee2MQTT / MQTT; registered and enabled on HA-General VM905.
- Temperature entity: `sensor.0xa4c13880bb5cffff_temperature`
- Humidity: `sensor.0xa4c13880bb5cffff_humidity`
- Battery: `sensor.0xa4c13880bb5cffff_battery`
- Recorder temperature: 18.6°C, updated ~1.3 min before the audit.
- Humidity: 74%, updated ~1.3 min before the audit.
- Existing configured outdoor source: `sensor.thermostat_thermostat_outdoor_temperature`, 11.5°C, updated ~14.8 min before audit.
- Difference at audit: **+7.1°C** (TS0201 warmer).
- Audit: https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40132207743

## Selection safety

User designated Summer House TS0201 as the external temperature sensor.
Its physical installation location has not been verified. A temperature
difference >7°C from the Honeywell outdoor source suggests different
microclimates, solar loading, indoor summerhouse conditions or calibration
offset. Do not treat the Summer House reading as outdoor ambient for heating
identification unless physically mounted outdoors, away from sunlight and
heat sources, and observed alongside a known local outdoor reference.

Current `ZoneCoordinator._outdoor()` prefers
`entry.options[CONF_OUTDOOR]` over `entry.data[CONF_OUTDOOR]` by its
configuration merge, but existing `config_flow.py` has **no OptionsFlow**.
Therefore it cannot currently be changed safely via the UI.

## Proposed additive implementation, no production write

1. Add a temperature-source selector to a future integration release:
   **Summer House TS0201 / Honeywell outdoor / weather fallback**. Keep
   weather entity `weather.ha_general` available.
2. Validate source presence, unit `°C`, freshness (e.g. <=30min for TS0201),
   plausible physical range, and persistent divergence from backup/weather.
   Never use last-known Zigbee state indefinitely when the device is offline.
3. Protect thermal learning from source mixing: on an approved source switch,
   preserve the old samples privately, create a new learning series for the
   selected source, and withhold predictions until the new series validates.
   The model should not fit indoor/outdoor deltas across mixed sensors.
4. Since Python module changes require Home Assistant Core restart,
   implement in the next guarded release with a private backup/rollback.
   Do not mutate `.storage/core.config_entries` while Core is running.
5. Display current temperature source, timestamp, divergence against the
   Honeywell sensor and weather fallback separately in the dashboard.
6. Do not change Honeywell setpoints, heating demand, existing automations,
   HA900 or VM903.

**Production status:** original v0.3.4 still configured to the Honeywell
outdoor-temperature entity. v0.3.5 thermal learner remains staged and pending
separate authenticated release approval. This note does not change either.
