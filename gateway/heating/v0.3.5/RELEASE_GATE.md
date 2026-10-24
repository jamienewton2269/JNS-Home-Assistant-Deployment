# JNS Heating Zones v0.3.5 — Candidate Release Gate

**Status: STAGED / NOT DEPLOYED.** This directory is an isolated candidate,
not an installed Home Assistant custom component. `manifest.json` on VM905
remains v0.3.4, and Home Assistant has not been restarted.

## Why this version exists

VM905 had 292 persisted readings (24 Oct 2026 shadow backtest). The old
five-minute regression accepted 161 adjacent intervals but estimated zero
heat-loss, heat-gain and drift, and did not validate.

A discrete Honeywell indoor sensor reported only 20.0/21.0°C, so adjacent
changes were mostly zero. Those observations do not justify a forecast.

## Candidate behaviour

- Keeps the exact `Sample(at, indoor, outdoor, duty, valid=True)` storage schema.
- Builds **nonoverlapping** time-weighted 30-minute windows for fine-resolution
  sensors or 50-minute windows for quantised sensors.
- Integrates heating duty over the complete window, not just the final sample.
- Accepts scheduler jitter and excludes gaps, time reversals, invalid values
  and implausible large instantaneous temperature jumps.
- Requires 48 independent windows, at least ten predominantly heated and ten
  unheated windows, sufficient room/outdoor/heat variation, and the existing
  physical coefficient limits.
- Exposes learner diagnostics through the existing `learned` status dict,
  which the `sensor.lyric_home_heating_thermal_learning` entity already
  exposes as attributes.
- Returns `None` instead of inventing a 60-minute prediction if the model,
  duty, forecast, or sample freshness is inadequate.
- Makes **no heating commands**. Honeywell remains authoritative. Any future
  optimum-start / predictive heating control must be a separately approved
  workstream with safety interlocks.

## Tests

GitHub Actions, on this development branch:

- Eight isolated deterministic Python tests PASS; synthetic multi-day 1°C
  sensor measurements can eventually identify plausible coefficients.
- The real VM905 shadow-backtest PASS: code loaded in a separate guest Python
  process, no HA reload or writes; saved sample JSON checksum unchanged.
- Live shadow result: 292 stored samples, 28 independent windows, only one
  nonzero indoor-change window; `ready=false`, prediction withheld.
- Live v0.3.4 source SHA256, to enforce during guarded deployment:
  `44054f9172e3c9e2e944240b5369b49d9735d8349fb7ca2dd0a2a782d7c8a4f8`.

## Private staging record — 24 October 2026

- [Backup-only staging workflow](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40111495234): **SUCCESS**.
- 16 isolated tests, current historical-data backtest and VM905 source preflight passed before staging.
- VM905 stage identifier: `v035-20261024T162546Z-43b0f6ec`.
- The private staging directory lives only inside VM905:
  `/config/.jns_heating_backups/v035-20261024T162546Z-43b0f6ec/`.
- Staged originals include the integration manifest, thermal module and one Home Assistant learning Store containing 296 samples at staging time. The candidate code and JSON transaction metadata are also staged.
- The backup tree is restricted to private mode 0700 directories / 0600 files and copy digests are checked.
- **Production `thermal.py` and `manifest.json` were NOT changed**. Active v0.3.4 remains authoritative.
- An independent post-stage integrity workflow is required before any promotion.
- The public self-hosted workflows expose preflight, backup staging and read-only verification only; there is deliberately **no production commit/rollback GitHub workflow**.
- The `transaction.py` apply/rollback primitives are tested against a synthetic filesystem, but must not be used on production until a distinct root-owned allowlisted gateway capability, a thermal-safety availability window and an approved reload/rollback check exist. Its `--gateway-authorised` flag is an acknowledgement only, not an authorization system.

## Required before production promotion

1. Confirm the current runtime version and source digest; **block** if they
   differ. Audit any concurrent changes first.
2. Re-run unit tests and live shadow backtest against **current** stored data.
3. Preflight disk free space and capture **private** backup snapshots of:
   `custom_components/jns_heating_zones/thermal.py`, `manifest.json`,
   `.storage/jns_heating_zone_*`, and checksums of the unchanged coordinator,
   entity config, and dashboards. Backup directory must be mode 0700 and files
   0600, never committed or uploaded to GitHub.
4. Use the existing JNS trusted gateway and root-owned audited deployment
   capability. No generic SSH commands or privileged arbitrary payloads.
5. Apply only the thermal learner and approved version metadata on VM905, as
   an atomic transaction; leave authentication, dashboards, config entries,
   coordinator, HA900 and VM903 untouched.
6. Compile/import the updated module and run configuration checks before
   controlled integration reload / HA restart. Do not restart during active
   heating control without a safe rollback and availability check.
7. Confirm existing Lyric entity IDs, learning persistence and sensors.
   Sample count must not decrease except through the existing 2016 cap.
8. On verification failure: restore original source/version atomically and
   verify the pre-change learning storage is still intact.
9. Initially monitor learning **in advisory mode**; do not enable any new
   forecast-driven heating action until long-term field validation.

## Operator promotion boundary — 24 October, later development

- A narrow **audit-only** root gate has been drafted in
  `nodeb_root_gate.py`. It is intended for root ownership on Node B,
  never for execution from an arbitrary GitHub payload.
- It binds to exact VM ID 905, stage ID
  `v035-20261024T162546Z-43b0f6ec`, and candidate digest
  `43b0f6ec0229d15dc137bbf3c52cd41b4bb125072fbcc49202e744ba8a19bc6c`.
- The operator approval file belongs under `/etc/jns/` with mode 0600,
  root ownership and `intent: assess_only`. There is no approved
  activation/restart command in this gate.
- Explicitly **not installed** on Node B, not added to sudoers, and not
  connected to GitHub Actions for activation.
- No runtime promotion until an independently verified HA integration
  reload/restart + health checks and rollback are available.
- The offline root-gate tests cover absent/wrong approvals, permissions,
  unexpected input and non-root callers; check their CI run before relying
  on the draft.

## Run links

- Candidate green CI / live shadow:
  https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40109868058
- Previous diagnosed state:
  https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/blob/main/gateway/heating/CONTINUATION_20261024.md
