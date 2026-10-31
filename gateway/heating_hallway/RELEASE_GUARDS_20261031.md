# JNS HA-General — Hallway Authority, Fireplace Heat Guard and Temperature Trends
**31 October 2026 — source-only implementation. NOT LIVE.**

## Explicit requirements
- **Authoritative thermal reference:** the Hallway Thermometer device from HA-General
  `3fc0d19af1ae3fad19d67ae05b4ccb0f` (Tuya TS0201 via MQTT).
- **Fireplace heat detector:** earlier identified Zigbee IEEE `0xa4c138818d33ffff`
  (temperature entity must be resolved from HA-General's current device registry).
- **Bathroom:** graph/history display only; remove from *all* heating learner
  inputs; do not promote the earlier 0.3.6 bathroom advisory candidate unchanged.
- **Honeywell:** `climate.thermostat_thermostat` continues to actuate heating.
  18°C night, 21°C comfort **by 10:00** when no fire override, away minimum and
  manual override preserved.
- When sustained fire heat is detected and **hallway + validated 60m forecast
  + fresh weather** prove it is safe, use a guarded 18°C setpoint setback.
  Restore scheduled 21°C if hallway is below 19°C, forecast below 18.5°C,
  or a key reading/model becomes stale. The 19/18.5°C levels are initial
  engineering safety thresholds, not an established measurement of the house.
- Testing → **Temperature Trends** view: live and Recorder history for hallway,
  fireplace, bathroom, Honeywell indoor/outdoor/setpoint and available plant
  probe temperatures; overlay *only genuinely available/validated* next-hour
  predictions as dashed segments. Plant entities on separate VM903 may not be
  mirrored in VM905; do not fabricate data or change VM903.

## Files in this development branch
- `heating_source_resolver.py` uniquely resolves the hallway by exact HA
  device ID and fireplace by Zigbee IEEE, and checks the known Honeywell
  entities and VM905-visible plant entities. It must be run privately inside
  an approved read-only VM905 audit. This repo must NOT contain the device
  registries or API credentials. The screen's 23.9°C is a point-in-time report,
  **not** proof of current sensor freshness.
- `jns_hallway_fireplace_package.yaml.template` is an inert package template:
  unresolved placeholders make it **unsafe for direct installation**.
  Includes house temperature + fire heat + setpoint aliases and a default
  fail-closed fireplace forecast gate. Suppression is unavailable until the
  hallway-only model reports validated `source_epoch=hallway-precision-v1`
  and `weather_forecast_fresh=true`.
- `fireplace_policy.py` pure offline policy function for tests/review; NOT a
  running engine and NOT a service that sends thermostat commands.
- `gateway/heating_presence/jns_predictive_schedule.yaml` on this branch
  switches scheduler references from legacy `sensor.jns_house_temperature`
  to `sensor.jns_hallway_house_temperature`, chooses 18°C only when the
  protected fireplace gate is ON, and excludes fire-lit cycles from morning
  warm-up timing calibration. Existing ready flags for the legacy Honeywell
  thermal model no longer grant trustworthy hallway predictions.
- `build_temperature_view.py` adds a NEW Testing view in memory while
  proving existing tabs unchanged. Native history cards remain usable without
  the optional custom graph. Custom `jns-temperature-timeline-card.js` uses
  authenticated HA frontend Recorder API access with no extra token, updates
  live values on dashboard refresh, polls 24h/7d history at 60s cadence and
  visually distinguishes measured vs validated 60-minute predictions.

## BLOCKING production prerequisites
1. Check live VM905/HA-General status and match exact **current** device and
   entity registries. Verify hallway and fireplace reports, supported
   `last_reported` timestamp behaviour and retained Recorder data. Ensure
   hallway placement is representative of the house and not overheated by
   sunlight/doors/radiator. Confirm MQTT freshness and divergence to Honeywell.
2. Check and preserve `/config/packages/jns_house_temperature.yaml` *as
   actually installed*; it may have other consumers. The new alias alone does
   **not** change every consumer of the older canonical entity. Audit each
   heating control/forecast consumer before switching the public authority.
3. **Supersede** staged bathroom 0.3.6 release with a new hall-only learner
   release. Do not re-label the bathroom model or reuse its samples. Design
   source-specific `hallway-precision-v1` store, fresh report filtering,
   heating-call sampling, weather input and new validated 60-minute forecast.
   Preserve original legacy learning samples in cold backup; no mixed epochs.
   Only a properly tested learner can produce the prediction consumed by
   `binary_sensor.jns_fireplace_override_safe`; until then, fire suppression
   must remain off and original heating protection unchanged.
4. The Lyric Honeywell uses its **own** internal temperature to actually call
   for heat. A setpoint increase may NOT cause heating when the hallway is
   colder but Honeywell's internal temperature is warmer; verify this case
   physically. Do not introduce unsupervised `hvac_mode` toggling or falsely
   claim independent hallway-driven burner control.
5. Back up relevant packages, integration code, dashboards, Recorder and
   configuration. Check current configs and duplicate IDs. The dedicated Node
   C root-installed allowlisted deployment handler, authenticated live heating
   idle, short-lived single-use permit and rollback must all be proven. Do
   not substitute GitHub code commits or a public workflow for local approval.
6. Test source switches, stale MQTT, missing outdoor forecast, manually toggled
   override, alarm away, bedtime, fireplace detected/on/off delays, and cold
   hallway at 18.5°C with fresh sensor readings. Test HA Core config check and
   guard scheduled heating restart; only then promote VM905.
7. Install the optional card resource through reviewed Lovelace resource
   registration at `/local/jns-temperature-timeline-card.js` (resource type
   JavaScript module) and add the new Testing view **without rewriting old
   dashboards**. No extra third-party services or custom graph dependency.
   If a resource is not installed, render just native `history-graph` cards.

**Current status:** code and offline tests proposed; exact current entity IDs
and deployment permissions have not been authenticated. Do not claim live.
