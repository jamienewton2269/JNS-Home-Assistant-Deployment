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


## Relocation follow-up — 25 October 2026, 00:43 BST

The user confirms this TS0201 has been physically moved to an appropriate
shaded, ventilated outdoor location and explicitly requested activation.

**Activation blocked by telemetry freshness and mismatch, not by lack of user
approval for the sensor choice.**

Fresh read-only HA-General audit from
[GitHub run 40143991115](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40143991115):

- `sensor.0xa4c13880bb5cffff_temperature`: **22.6°C, last recorded ~95.6 minutes earlier**
- Humidity: 56%, also ~95.6 minutes old
- `sensor.thermostat_thermostat_outdoor_temperature`: **12.0°C, ~0.9 minutes old**
- Deviation between last recorded readings: **+10.6°C**; the readings are
  not simultaneous. The TS0201 may be holding a pre-relocation value.
- Node B CT214 (Zigbee2MQTT) and CT212 (Mosquitto) both **running**;
  Zigbee2MQTT service and MQTT broker active; bridge health published.
  [Read-only reporting audit](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40144073384).
- HA-General integration still uses Honeywell outdoor sensor; no changes
  to the config entry or live heating source were performed.

Before activation require a *new real timestamped TS0201 report after the
outdoor relocation*, preferably consistent with a separate shaded outdoor
reference (significant microclimate variation must be examined), and a
robust **stale-reading fallback**, since v0.3.4 `coordinator._number()`
accepts stale numeric Home Assistant states without an age test.
Protect existing thermal-model samples from conflating the two source
epochs. The runtime update still requires the JNS root-owned approved
release path described in `RELEASE_OPERATOR.md` / `NODEC_ROOT_GATEWAY.md`,
which has not been installed.

Zigbee2MQTT TS0201 vendor documentation warns about an OTA firmware update
that can brick this model; do **not** initiate OTA as a troubleshooting step.


### Follow-up reporting-path correction

A second read-only Zigbee2MQTT audit filtered the **friendly name**, not just
the IEEE address. It found MQTT publications at
23:23:03, 23:24:33, 23:38:02 and **23:39:33 UTC** on 24 October,
with reported linkquality **99–102**, temperature still **22.6°C**, and
humidity **56%**. Both CT214 Zigbee2MQTT and CT212 Mosquitto services
were active. This confirms *current MQTT publications*, so old HA Recorder
`last_updated_ts` reflects an unchanged temperature rather than proving a
disconnected sensor. No per-device `temperature_calibration` option was
found in the inspected Zigbee2MQTT configuration block; this limited check
does not establish calibration accuracy.

**Activation remains blocked on measurement plausibility**: the latest
device-reported temperature differs substantially from the independent outdoor
reading; it may represent pre-relocation heat soak, an incorrectly placed
sensor, or a sensor measurement fault. Confirm the TS0201's **next new
temperature measurement** after acclimatisation outdoors before selecting it,
and preserve the guarded source-history epoch switch/freshness fallback.
The device's latest published reading predates the user's relocation-
confirmation message by only a few minutes, so no proof of post-relocation
thermal equilibration is available.

Latest [link/calibration audit](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40144332976).
