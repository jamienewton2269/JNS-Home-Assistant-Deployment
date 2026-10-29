# Bathroom precision learner — HA-General activation status

**25 October 2026. Source code prepared. NOT ACTIVE ON VM905.**

## Requested operational behavior

Use the Bathroom Sensor temporarily for independent *advisory* thermal
learning. Reject shower-related temperature/humidity changes, data gaps,
stale repeated Zigbee values and readings inconsistent with the house
thermostat. Keep Honeywell as the sole house heating controller.
Do not change the original 60-minute forecast entity until validation.

## Exact integration files in this branch

- `bathroom_extension/coordinator.py` — starts an optional, isolated
  `BathroomAdvisory` sub-coordinator but does not replace Honeywell indoor
  reference or existing heater/response methods.
- `bathroom_extension/sensor.py` — adds three new advisory entities:
  filtered bathroom temperature, 60-minute bathroom model projection and
  bathroom learning quality. Leaves all original sensors unchanged.
- `bathroom_runtime.py` — quality-controlled ingest and a separate
  Home Assistant Store `jns_heating_bathroom_zone_<entry_id>` with
  `bathroom-precision-v1` epoch.
- `bathroom_reference.py` — quality gate with ≥3 distinct accepted
  observations spanning ≥10 minutes, humidity and heat-spike suppression,
  30-minute shower quarantine and ≤15-minute report freshness.
- `thermal.py` — quantization-aware v0.3.5 learner for separately
  accumulated precision samples.
- `test_bathroom_reference.py` and `test_bathroom_extension.py` —
  offline filtering tests and AST checks that the existing heater-control
  methods and original forecast sensors remain unchanged.
- `bathroom_extension/baseline/*` — exact currently installed
  coordinator and sensor source, for reproducible safety checking.

This is an additive release, provisionally labelled **0.3.6 bathroom**,
not the already staged **0.3.5 learner-only** release. Do not install
0.3.5 and claim it activates bathroom input; the old stage includes only
`thermal.py` and `manifest.json`.

## Why production cannot be changed through GitHub yet

The existing approved JNS Node C root wrapper only dispatches allowlisted
operation types; the heating promotion extension was source-only when
last audited. The privileged promotion handler is fixed to the old
0.3.5 learner-only stage and its digests. It does **not** accept the
0.3.6 bathroom candidate, and cannot be reused for this purpose.

Known Core API credentials in the HA add-on returned HTTP 401 to fixed
heating entity checks. Live heating inactivity therefore could not be
independently authenticated. Before promoting, a root-installed, dedicated
0.3.6 handler and locally authorised Home Assistant state-read capability
must verify a safe maintenance window, exact source hashes, and rollback
availability. GitHub code submission is *not* root-local approval.

A custom Python integration update requires a guarded Home Assistant Core
restart (VM905 only), not merely a config-entry reload. This will briefly
affect all HA-General automations and must not be triggered unattended
while heating availability is unknown.

## Acceptance criteria before promotion

1. Verify installed `jns_heating_zones` v0.3.4 and original SHA256
   fingerprints of coordinator, sensor and thermal modules. If any
   differ, STOP and update the baseline.
2. Read-only check that the bathroom TS0201 is live and the last genuine
   Zigbee report is within 15 minutes; the thermostat is usable and
   heating is not actively calling for heat.
3. Privately back up full integration files, dashboard and all
   `jns_heating_zone_*` learning stores; do not overwrite any of them.
4. Stage `coordinator.py`, `sensor.py`, `bathroom_reference.py`,
   `bathroom_runtime.py`, `thermal.py`, and version metadata as one
   all-or-nothing transaction.
5. Verify `ha core check`; perform a controlled Core-only restart under
   a root-owned locally authorised handler. Never use arbitrary SSH shell
   payloads or patch `.storage/core.config_entries` directly.
6. Confirm the three **new** bathroom advisory entities become
   available, original Lyric sensors and thermostat remain available,
   no setpoint has changed, and the old learning store is intact.
7. If any check fails, restore original component files through the
   HAOS host filesystem and verify a second Core startup.
8. Predictions may initially be `unavailable` until enough *filtered*
   precision observations exist. Do not advertise a fitted forecast
   before the learner reports ready.
9. Keep the original dashboard forecast unchanged until downstream
   `packages/jns_house_temperature.yaml` is audited and a separate
   dashboard transition is approved.

**No Home Assistant files, dashboards, learning stores, thermostat
setpoints or existing automations have been changed by preparing this
candidate.**
