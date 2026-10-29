# JNS Heating v0.3.6 — bathroom precision advisory release state

**Updated: 28 October 2026. BACKED UP AND STAGED ON VM905. NOT ACTIVE.**

This record is a production-state attestation, not a claim of a successful
activation.

## Verified candidate

The following six candidate files were privately staged on HA-General
VM905 through the JNS Node C GitHub runner and established Node B QGA path:

- `coordinator.py`: additive isolated bathroom advisory learner
- `sensor.py`: three **new** advisory entities, original house sensors intact
- `thermal.py`: nonoverlapping-window precision learner
- `bathroom_reference.py`: bathroom heat/humidity/shower exclusion filter
- `bathroom_runtime.py`: separate `jns_heating_bathroom_zone_<entry_id>`
  store and source epoch `bathroom-precision-v1`
- `manifest.json`: v0.3.6 candidate

Live v0.3.4 files were checked against exact protected module digests
immediately before staging; no live source changes were made.

**Private stage ID:** `v036-20261028T103734Z-a6babd0e`
**Private directory:** `/config/.jns_heating_backups/v036-20261028T103734Z-a6babd0e/`

The stage includes original versions of the four overwritten files, a
checksum-verified private snapshot of existing heating learning history,
all six candidate files, and release metadata. It does **not** overwrite
Recorder or active heating data.

- [Successful private backup-only staging](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40673576217):
  68 automated tests passed; 1,350 existing samples privately preserved.
- [Independent post-stage integrity verification](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40673720815):
  original files unchanged, candidate/backup checksums verified, Core not restarted.

## Current production snapshot

At the final staging preflight:
- VM905 HA-General, Core 2026.10.1, integration **0.3.4** remains active.
- Temperature `sensor.0xa4c1382471d2ed23_temperature`: 23.04°C,
  humidity `sensor.0xa4c1382471d2ed23_humidity`: 45.97% RH.
- Honeywell indoor reference `sensor.thermostat_thermostat_indoor_temperature`
  was **22°C**, having been `unavailable` at an earlier preflight.
  Transient availability requires a fresh *authenticated* live-state
  check before restart.
- Last recorded heating call was `off`; an old Recorder entry is
  not adequate proof of live idle heating.
- `nodec_heating_privileged_code_installed=false`,
  `nodec_root_handler_hook_present=false`,
  `nodec_heating_approval_directory_exists=false`.
  The existing JNS root wrapper does not expose the required
  v0.3.6 commit / rollback operation.

## Release prerequisites that remain BLOCKING

1. **Separately reviewed and installed root-owned v0.3.6 gateway
   capability** on Node C, fixed to this stage, six source digests,
   and VM905 only. Do not reuse the old v0.3.5 two-file promotion.
   An immutable GitHub queue job is not local operator approval.
2. **Authentic HA-General administrator-authorised live state read**,
   able to confirm thermostat, Honeywell sensor, heating call, and
   Core health. Existing Supervisor token was HTTP 401; do not
   bypass authentication or trust old Recorder state as a substitute.
3. **Local, short-lived, single-use maintenance approval** and an
   availability-safe Home Assistant Core-only restart window, coordinated
   with active heating/nighttime schedules and current HA consolidation.
4. A v0.3.6 root promotion handler must apply the six staged files
   atomically, perform `ha core check`, then restart **Core only**;
   after restart verify the three new advisory entities, untouched
   Honeywell setpoint/logic and learning store, and real sensor freshness.
   If verification fails, restore original files through the
   HAOS host volume and restart original Core.
5. Predictions begin **unavailable until enough fresh quality-gated
   bathroom measurements exist**. Do not invent predicted values or
   silently substitute them for the existing house forecast.

## Why the public workflow stops at staging

The staging tool itself is not a root authorization system.
The public GitHub Actions workflows intentionally expose **no** command
that replaces live custom Python modules or restarts VM905.
The lack of a privileged release handler is an architectural safety
constraint, not a missing argument to the staging command.

The user has approved this feature and requested activation, but that
chat-level instruction is not a machine-issued Node C root permit.
Do not suppress these production safety gates.

HA900, VM903 Plant Manager, other consolidated Home Assistant nodes,
Honeywell credentials, heat setpoints, dashboards, automations and
original thermal learning remain untouched.
