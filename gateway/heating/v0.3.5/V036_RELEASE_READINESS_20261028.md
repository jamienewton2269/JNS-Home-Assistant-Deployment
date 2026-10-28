# JNS Heating v0.3.6 — 28 October 2026 live continuation and root release readiness

**Production: BLOCKED. Installed VM905 heating integration remains v0.3.4.** This is a factual status record, not an activation instruction.

## New read-only results

- [VM905 protected-source and Node C gateway audit, 10:59 UTC](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40676413006): PASS.
- VM905 on Node B running HA Core 2026.10.1 (API configured port 80), integration v0.3.4; protected original coordinator, sensor, thermal and manifest match exact SHA-256 fingerprints.
- Recorder-only readings at audit: bathroom 22.93°C, humidity 46.43%, Honeywell indoor 22°C. These **do not establish live heat-idle permission**.
- Existing thermal learning still reports "Learned values outside safe bounds"; no separate bathroom store yet.
- **No** heating root handler installation, heating dispatcher case or root permit directory on Node C.
- [Independent private-stage integrity and SHA-256 attestation](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40676574781): PASS, all six candidates and original private backup unchanged, Core not restarted.

## Candidate stage: exact pinned files

Private stage ID: `v036-20261028T103734Z-a6babd0e`

| Candidate | SHA-256 |
|---|---|
| coordinator.py | `6efba63422429a0871784024eff0fb08956b82012d431949c19e700bf6130abc` |
| sensor.py | `4c414892b141308113f08d54a49445dd7e70a7cd61f7f80d8d606dc14aff84d1` |
| thermal.py | `43b0f6ec0229d15dc137bbf3c52cd41b4bb125072fbcc49202e744ba8a19bc6c` |
| bathroom_reference.py | `d227e6f5cc2113b8fd8af9e2958c50a3d408a22156ad671ddee0c9ef2f97389d` |
| bathroom_runtime.py | `786f0a8d938976e5e86945441dbb75d2fdbb6526b486edfa2f1a7de1720567f8` |
| manifest.json | `deabac235df69398d8a9eaff7dfef0ef0ca3977ffb98af4c6ab48b429d903ab9` |

Original backup SHA-256 values are pinned in `v036_release_policy.py`; the separate learning-store backup has 1,350 preserved pre-stage samples. **Do not overwrite a growing live history with its saved copy.**

## New reviewed source on development branch

- `v036_release_policy.py`: strict fixed-stage and six-file digest attestation, immutable three-field job, ten-minute local root permit, fail-closed live authenticated heating-safety and protected thermostat target/mode verification, all three advisory entity labels.
- `test_v036_release_policy.py`: seven regression tests for the above.
- `v036_root_operator.py`: NEW, dormant **root-local-only** Node C candidate with fixed Node B VM905 identity, protected six-file transaction, authenticated Home Assistant REST state, repeat heat-idle checks, Core process restart proof, independent HAOS host-volume recovery and no setpoint commands. **SOURCE ONLY: NOT INSTALLED, NOT ROOT-REVIEWED, NOT EXPOSED BY THE GATEWAY WRAPPER.**
- `v036_local_approval.py`: NEW, local interactive root-only eight-minute, one-use job/approval generator requiring explicit heating interruption and quiet consolidation confirmation. Not installed.
- `test_v036_root_operator.py`: NEW, offline root safety and fallback shell regression tests. These exercise synthetic scenarios; passing them is not proof of production-safe installation or rollback.
- [Candidate CI run 40676825952](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40676825952): **75 tests pass**; private historical shadow-backtest and live read-only prerequisite audit pass.

**Important:** The source-level, root-only v0.3.6 operator is not an installed privileged promotion handler. There is NO approved executable six-file commit/restart/host-rollback handler installed on Node C. Review its installer, exact root ownership, pinned source and end-to-end rollback in an isolated environment before installation. Do not reuse the old v0.3.5 handler or treat a branch push as local root approval.

## Remaining transactional promotion gates (all mandatory)

1. An administrator separately reviews and installs **narrow, root-owned v0.3.6-only** code on Node C, preserving the existing gateway wrapper's other cases, with a hard-coded Node B VM905 identity and pinned stage hashes. Operator approval must be short-lived, single-use, local root-created and not available to the GitHub runner.
2. An administrator provisions a valid Home Assistant administrator API token **privately on the authorised host**, with root-only file permissions. Existing Supervisor/SSH add-on Core API requests returned HTTP 401. Never paste tokens into chat, GitHub, logs or queued jobs.
3. Recheck live HA state from **authenticated** Core GET responses, not Recorder: climate target and hvac_action, heating call off, Honeywell indoor, current bathroom temperature/humidity, sensor freshness, working Core, no recorder migration or concurrent HA consolidation Core operation. The VM906 security fallback/timer and exclusive controller ownership may be changing around this window; defer Core restart until verified quiescent.
4. Confirm exact backups and HAOS host-volume recovery, and perform a **six-file** confined apply. Pass `ha core check`; repeat live heating idle attestation before restarting **HA Core only**. Do not power-cycle the Proxmox guest or other infrastructure.
5. Prove a **new** HA Core process loaded the 0.3.6 candidate, verify all six live hashes, all three advisory entities, separate bathroom learning store after sufficient fresh samples, preserved old learning store, unchanged Honeywell setpoint and mode, and absence of new broken automations.
6. On failure, restore **four** original files, remove the **two** newly added modules through the HAOS host volume even if the Core container cannot start; restart original Core and verify live heating. If that cannot be proven, raise critical operator intervention instead of reporting success.
7. Keep the existing projected-house-temperature and dashboard consumer unchanged until the new bathroom model reports valid quality-gated coefficients. The 60-minute bathroom projected entity may legitimately be unavailable initially. Only promote numbers to the UI when mathematically valid; never fabricate them.

## Operational prohibition

No production custom component files were replaced in this continuation; no Core restart was attempted for heating v0.3.6, and no Honeywell setpoints were issued. **Next authorised action is a root-local installation and authenticated live interlock, not another backup-only staging job.**
