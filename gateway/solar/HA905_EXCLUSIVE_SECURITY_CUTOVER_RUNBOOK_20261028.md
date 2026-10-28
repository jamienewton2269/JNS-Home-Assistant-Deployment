# JNS HA905 — exclusive VM906 security cutover and Proxmox post-merge gate

**State:** prepared, not authorised for execution. As at 28 October 2026,
all three HA Core instances are online and VM906 remains the ESPHome security
owner. This document is an operational runbook, NOT evidence of production
acceptance.

## 1. Why the ESPHome API route was blocked

[Official Home Assistant app documentation](https://contributors.home-assistant.io/apps/supervisor-api/core/)
requires `homeassistant_api: true` for the app's Supervisor-issued token to
access the Core REST/config flow API proxy. Existing VM905 app inventory
[40681972031](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40681972031)
confirmed **3 installed apps, 0 Core-API-enabled**. An app's
`hassio_role: admin` alone does NOT authorize the Core proxy.
Never extract/reuse another app's token, copy `.storage/core.config_entries`,
or place ESPHome encryption secrets in the repo, workflow logs, or HA dashboard.

## 2. Preprepared safe probe

- Four reviewed local app source files
  `gateway/solar/ha905_core_api_bridge_app/{config.yaml,Dockerfile,probe.py,README.md}`.
- App is `boot: manual_only`, `startup: once`, with no host network,
  port forwarding, mounted HA configuration, Docker socket or full access.
- It has **`homeassistant_api: true`**, an administrator-equivalent privilege:
  separate operator authorisation is mandatory for installation and startup.
- v0.1 probe performs only two fixed GETs; it does **not** enrol ESPHome.
- Local policy/offline fake-auth tests passed
  [40682285628](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40682285628).
- Private Node B host stage
  `/var/lib/jns-solar/consolidation/ha905-core-api-bridge-probe-20261028-v1`
  has manifest and four hash-attested source files, verified by
  [40682433617](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40682433617).
  **Not installed on VM905; no API grants activated.**

## 3. Source/target migration baselines

| Item | Existing verified state |
|---|---|
| VM906 source | HA Core responding; 1 ESPHome entry, 35 ESPHome-platform entities |
| VM905 target | HA Core responding; 0 ESPHome entries, 2 mobile-app registrations |
| Native security v2 | Manual alarm + 64 template binary sensors + 6 initial-disabled automations on VM905 |
| Security YAML IDs | All 64 original source template names/unique IDs already represented in VM905's staged package |
| Deferred input_number | Source definition privately staged on Node B; not yet activated |
| Dashboards | 2 missing VM902 views + 1 VM906 view staged privately, not imported |
| Lux priority | 20 required entities independently registered (40678077784) |
| Node A destination | VM905 stopped definition with two disks; production VM905 currently runs on Node B |
| Recovery | Backup manifests exist for 902/905/906; **isolated full restore boot-test outstanding** |

The old VM906 security dashboard contains 64 binary-sensor references, 48 of
which are unregistered even on the original source, and does not match names
derived from the already migrated 64 template definitions. **Never bulk-import
the security dashboard or duplicate the template sensors.**

## 4. Execution gates — MUST ALL pass before source stop or Core config flow

- [ ] User/onsite operator explicitly approves a **new** maintenance interval
      and VM906 interruption. Authorisation on 28 October at ~10:01 UTC was
      time-limited and has expired. No inferred extension.
- [ ] Provide physical alarm monitoring, manual key/access and working
      fall-back during the window; arrange on-site doorbell/tamper/siren tests.
- [ ] Freeze unrelated HA-General Core deployments (heating, Lux, fans).
- [ ] Verify current VM905 and VM906 backups/checksums, Node B healthy,
      Node A QGA reachable, device ESPHome TCP reachable from Node B.
- [ ] Verify VM905 manual alarm v2 and six native automations are still
      staged **disabled**; verify no other owner is commanding the same
      security inputs/outputs.
- [ ] Obtain separate approval to install and once-run the restricted,
      admin-equivalent local API probe; install through a new **guarded**
      Node C transaction only (no generic root runner permissions).
- [ ] Confirm read-only GET Core API status 200 via probe. If 401 or any other
      failure: do not use ad hoc tokens or proceed.
- [ ] Build a **separate**, reviewed and explicit-permit native ESPHome
      config-flow execution, using existing host-private encryption metadata
      and Home Assistant's supported flow endpoints. Do not modify registry
      files or make speculative endpoint calls.
- [ ] Arm/verify a fresh Node A local timed VM906 recovery interlock.
      Then and only then fence VM906 as the source **before enabling any
      competing VM905 ESPHome control**. Do not assume source retirement.
- [ ] Enrol ESPHome on VM905 using native configuration flow. Verify exactly
      one target entry, target connection and expected usable entities.
- [ ] Activate, test and document security automation behaviour one by one.
      Check arm/disarm, door contact, bell/tamper inputs and siren with the
      on-site operator; no destructive or unexpected alarm testing.
- [ ] Remap and verify security dashboard entities; review the deferred
      input_number definition for live activation; keep 64 templates singular.
- [ ] Disable/retire temporary admin-capable app immediately after use.
- [ ] Confirm no duplicate alarm/device controllers before cancelling the
      recovery interlock and retiring VM906. Obtain explicit acceptance.

## 5. Automatic or manual rollback

If the interval expires, ESPHome enrolment fails, source isolation cannot be
proved, alarms behave unexpectedly or target health degrades:

1. Leave/restore VM906 as the exclusive operational security controller using
   the local timed recovery path; verify its Core and source ESPHome health.
2. Keep VM905 migrated security automations inactive. Avoid both controllers
   simultaneously commanding physical outputs.
3. Do not copy VM906 `.storage` entries, blindly change IP addresses, remove
   the old backup, delete original configuration or start a cluster join.
4. Record failure type, state transitions and checksum comparison in issue #1.
5. Investigate failure after confirming the source alarm is live.

**Source recovery proof does not by itself prove exclusivity**; inspect both
instances' active automation/device ownership after an aborted trial.

## 6. After successful single-HA merge only

1. Verify mobile clients, camera/WebRTC/PTZ/two-way audio, heating,
   fans, Zigbee2MQTT/MQTT, local Tuya, Lux priority and dashboards.
2. Create a fresh consolidated VM905 backup; checksum and **isolation-restore
   and boot-test** it. WDNAS is only a backup/shared file target, not live HA
   storage.
3. Reconcile Node A's stopped/stale VM905 definition (do not overwrite),
   capacity and NIC/DNS identity; fence Node B source before Node A recovery.
4. Preserve VM903 Plant Manager separately and verify Node C evacuated LXC
   headroom/ID scope, including Node B’s infrastructure and Node A/B VMID
   collisions 210, 212, 213, 214, 900, 902, 903, 905.
5. After Node B becomes guest-free and recoverability proven, create the
   Proxmox cluster from Node A, join empty Node B, verify quorum/QDevice
   policy and test Proxmox replication with one active HA controller.
