# CURRENT DIRECTIVE — LOCAL ONLY (25 October 2026)

The Tuya/Smart Life sign-in does not work and is **no longer a
precondition** for this JNS project. Stop proposing cloud-assisted setup.
Never attempt the Tuya cloud login, create developer API keys, or depend
on Tuya's servers for routine device functionality. The user accepts
losing Tuya cloud features but requires preservation of existing local
Home Assistant, Zigbee2MQTT, MQTT, security and lighting operation.

The canonical active guide is the **private**, live-generated file on
HA-General:
`/config/.jns_tuya_freedom/CLOUDLESS_RECOVERY_STATUS.md`.

Confirmed on 25 October:
- Five existing `tuya_local` config entries have stored local keys.
- Three have at least one available local entity; two have none.
- One unavailable device was matched by **exact native Tuya device ID**
  to a newly discovered IP; a Host-only correction is appropriate,
  preferably to a verified `.home.arpa` DNS name via its supported
  Configure/options flow. Do not edit `.storage` while Core runs.
- The other unavailable local device was not found by LAN discovery.
- Seven other cloud-associated physical devices have **no known local
  key** and none appeared in the Tuya LAN UDP scan; their transport
  types require physical/model verification.
- A check of legacy VM900 was inconclusive because its guest registry
  was unavailable through the authorised path.
- CT214 Zigbee2MQTT currently lists 21 routers, 10 end devices and
  one coordinator. Moving Tuya Zigbee devices from a different Zigbee
  network requires a physical reset and new pairing; preserve existing
  network devices.
- No Tuya or Smart Life account login, config-entry disablement, live
  Host mutation, key extraction, device reset or pairing was performed.

Keep local key secrecy, transactional rollback and working local
automation as hard requirements. Do not confuse **cloud-offline** with
**LAN-operational**. Some Tuya Wi-Fi devices require an existing local
key or supported local firmware replacement; a discovered IP alone is
insufficient. The older cloud-assisted onboarding instructions below
are retained as historical context and **superseded** by this section.

---
# Follow-up diagnostic and repair status — 25 October 2026

The following live, safeguarded actions were performed through the Node C
GitHub runner **without** an HA token, HA restart, or configuration mutation.

- Two devices with zero available local entities: both configured LAN addresses
  did **not** accept a TCP connection on Tuya's local port 6668.
  [Targeted TCP diagnostic](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40144286534).
- The installed `tinytuya.find_device(dev_id=...)` discovery found **one**
  of the two at a **different** current IP, and did not discover the other.
  [Discovery run](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40144449217).
- A private repair checklist with the device name, old IP and discovered
  IP is stored at
  `/config/.jns_tuya_freedom/LOCAL_REPAIR_INSTRUCTIONS.md`.
  [Checklist workflow](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40144607539).
- Seven not-yet-local devices: none identified in one
  noninvasive native Tuya UDP broadcast sweep.
  This **does not** prove Zigbee, BLE, sleeping battery devices, or
  incompatibility. [LAN scan](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40144677615).
  Names, device IDs and any detected metadata are retained privately at
  `/config/.jns_tuya_freedom/PENDING_SEVEN_LAN.md`.
- All five existing local entries still hold keys and hard-coded IP hosts;
  the HA-native observer shows one fully available device, two partly
  available devices and two devices with no available entities.
- No cloud config entry, local key, host setting, HA entity ID, or automation
  was changed; **no device is marked repaired or migrated**.

## Safe supported recovery

Use **HA-General** Settings → Devices & Services → Tuya Local → select
the device shown in `LOCAL_REPAIR_INSTRUCTIONS.md` → **Configure**.
Tuya Local's options flow exposes Host, Local Key and Protocol Version.
Use the discovered host from the private report *only when the returned
native Tuya ID is verified to match*; preserve local key, type and entity IDs.
The undiscovered device cannot be assigned a guessed address. Check power,
Wi-Fi or hub association before deciding whether a new pairing is needed.

To investigate the seven, start [Add Tuya Local integration](https://my.home-assistant.io/redirect/config_flow_start/?domain=tuya_local)
while logged into **HA-General** and select **Cloud-assisted**.
Authorise with Smart Life/Tuya app once; choose unconfigured devices
one by one. The cloud-assisted setup fills in local IDs and keys for
eligible Wi-Fi devices. If a device is a battery sensor without a hub
or a Zigbee subdevice, prefer Zigbee2MQTT with the existing JNS broker
if it can pair there, preserving old cloud entities until tested.
No blind entity rename or deletion.

After each successful options change or new onboarding, this integration's
observer updates `/config/.jns_tuya_freedom/latest-live.json` at five-minute
intervals. Re-run `gateway/tuya_freedom/repair_diagnostic.py` through GitHub
to verify the new available entities. Availability alone isn't proof of
operation with WAN blocked.

---
# Verified activation — 24 October 2026

**LIVE on HA-General VM905.** User-authorised transactional Core-only
restart completed successfully, with baseline and post-install
`ha core check` both passing. The protected original
`configuration.yaml` backup is stored privately on HA-General
under `/config/.jns_tuya_freedom/observer-activation/`.
The token-free observer is now enabled at
`/config/custom_components/jns_tuya_freedom/` and
`jns_tuya_freedom:` is configured in `configuration.yaml`.

- Deployment: https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40132581822
- In-memory observer report: `/config/.jns_tuya_freedom/latest-live.json` (0600)
- Private device-by-device checklist:
  `/config/.jns_tuya_freedom/ONBOARDING_STATUS.md` (0600)
- Private checklist workflow: https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40133378677
- 12 unique physical cloud devices; 5 have local entries; 7 still need
  local onboarding.
- 33 enabled local entities, all 33 loaded, **23 available**.
  Three of the five local devices have one or more available entities;
  one has every enabled entity available; **two have no available
  entities**. Diagnose these before any entity-ID cutover.
- No device command, cloud disablement, entity migration, WAN denial or
  additional VM/Node restart was performed. Available states by themselves
  **do not** prove cloud independence.
- The separate Home Assistant API token route was abandoned; revoke any
  token previously exposed in chat.

**Future changes:** do not deploy the activation request a second time;
the transaction folder intentionally blocks a duplicate deployment.
The observer updates its private `latest-live.json` every five minutes.

---
# 24 October 2026 — tokenless path (preferred)

The earlier manually pasted Home Assistant long-lived token route was unreliable
in the user's terminal. The user's previously pasted token must be revoked in
Home Assistant; **do not reuse or paste tokens into GitHub or chat**.

Instead use a **Home Assistant native, read-only observer**, with no token and no
API bridge. The source and manifest are in
`gateway/tuya_freedom/component/`. It uses Home Assistant's own in-process
`hass.states` and device/entity registries. No Tuya control commands,
second device connection, cloud API or account authentication is made.

Status: the observer has been syntax-checked and privately staged in
`/config/.jns_tuya_freedom/staged_observer/jns_tuya_freedom/`.
Neither the active `custom_components` directory nor
`configuration.yaml` was modified, and there has been no restart.
The existing system has no active Pyscript, Python Script or MQTT
statestream integration that would expose live HA states without a reload.

**Pending activation:** following explicit approval for a controlled
HA-General Core restart, securely back up `configuration.yaml`, install
the staged module at `/config/custom_components/jns_tuya_freedom/`,
append `jns_tuya_freedom:` to configuration, run `ha core check`,
restart **Core only** (not VM/Proxmox), verify a recent private
`/config/.jns_tuya_freedom/latest-live.json` report, and auto-rollback
if unsuccessful. Do not disable native cloud integration, change entity IDs,
or send device commands during this observation phase.

Token-free findings: all five locally configured hosts resolve; a passive
three-sample socket inspection saw no established TCP connection to their
exact resolved addresses, but did see three other Tuya TCP peers. This is
inconclusive because Tuya connections can be short-lived or use different
endpoints. Private details are on HA-General, not in public Actions logs.

For the seven unconfigured devices, the existing **Tuya Local Add
Integration** UI can acquire local connection keys through a one-time
authorised Smart Life/Tuya app login; it does not require the JNS observer
token or admin REST token. This is not a promise every device supports
Tuya Local or will remain operable with WAN denied. See
https://github.com/make-all/tuya-local for device-specific limitations.

---
# JNS Tuya Freedom — VM905 operator handoff

## Verified preflight (2026-10-24)

- Target: `ha-general.home.arpa`, HA-General VM905, Node B.
- 12 unique cloud Tuya device IDs across 36 Tuya registry records (three copies per native device ID).
- Five have Tuya Local 2026.9.2 config entries and keys; five local device hosts resolve.
- Seven native IDs are not onboarded. Their cloud entries expose no reusable local keys in the HA config.
- Existing cloud integrations remain operational; zero entity IDs changed.
- Private plan and readiness records: `/config/.jns_tuya_freedom/` with mode 0700 directory/0600 files.
- Live state validation remains blocked because no dedicated local admin token has been provided.
- A heavier recorder query timed out and was reverted; the lightweight readiness check passed afterward.

## One-time authenticated HA API setup (must be done locally by operator)

Create a **dedicated** Home Assistant Administrator user `jns-tuya-freedom`
under HA-General Settings > People > Users (never HA-Primary). Sign in
as that user and create a long-lived access token at Profile > Security.
Do not paste the token in chat, GitHub, commit history, or a workflow log.

On the trusted HA-General Terminal & SSH add-on terminal (using a root
shell with `id -u` returning 0), enter the following. The token is
entered only at a hidden interactive prompt, not as a command argument:

```bash
umask 077
test "$(id -u)" -eq 0 || { echo "Root terminal required"; exit 1; }
test -d /config/.jns_tuya_freedom || { echo "Private plan directory missing"; exit 1; }
test ! -L /config/.jns_tuya_freedom || { echo "Unsafe symlink"; exit 1; }
chmod 700 /config/.jns_tuya_freedom
read -r -s -p "Paste JNS Tuya Freedom API token (hidden): " JNS_TUYA_TOKEN
echo
( umask 077; printf '%s' "$JNS_TUYA_TOKEN" > /config/.jns_tuya_freedom/ha_general_api.token )
unset JNS_TUYA_TOKEN
chmod 600 /config/.jns_tuya_freedom/ha_general_api.token
```

The privileged token must remain inside VM905. This file provides
specific credentials for Tuya Freedom; never reuse the narrowly scoped
JNS Steward automation-reload credential.

Once created, run Node C workflow
`.github/workflows/jns-tuya-freedom-live-health.yml` or update
`gateway/tuya_freedom/live_validation.request`. The read-only report
is saved privately on HA-General as `live-health-*.json`. The public
workflow logs show only aggregated availability counts.

## One-time Tuya account authorisation

Tuya Local 2026.9.2 supports its own cloud-assisted setup, described
upstream at https://github.com/make-all/tuya-local . In HA-General,
open Settings > Devices & Services > Add Integration > **Tuya Local**,
choose the Tuya / Smart Life app-assisted path and complete the
account authentication on your phone. This is onboarding only.
Authentication tokens are short lived and not saved by Tuya Local.

After first-device authorisation, cloud-assisted setup can normally
reuse its short-lived session to add multiple devices until HA restarts.
Do not delete or re-pair a Tuya device in the phone app, which would
rotate its local key and break any existing integrations.

## Conversion guardrails

1. Back up all HA settings and verify restore viability before any live
   reconfiguration.
2. Use private plan `physical_devices` records to select the seven
   missing native IDs; check whether each is WiFi-local or a battery,
   Bluetooth or hub-dependent device.
3. Acquire local keys on VM905 using Tuya Local's supported one-time
   assisted flow; never publish local keys or credentials.
4. Add each to Tuya Local with its own device type and data-point mapping.
5. Verify read-only entity state in HA. Test switching or commands only
   after impact review; **never actuate a lock, heater, security device
   or protected IT socket automatically**.
6. After successful normal and WAN-blocked device testing (including
   restart), approve exact entity-ID migrations with JNS transaction
   and rollback journal. Cloud integrations remain enabled until every
   device in each cloud config entry is accounted for.
7. To prove independence, block WAN egress for one device at a time
   on the router (not LAN-to-HA access), and verify functionality and
   return from power cycle. Undo blocks for any broken device.

## Current control plane

Read-only and staging:
- `gateway/tuya_freedom/readonly_audit.py`
- `gateway/tuya_freedom/private_plan_stage.py`
- `gateway/tuya_freedom/readiness.py`
- `gateway/tuya_freedom/live_validation.py`

Portable community cutover candidate (not production deployed):
- draft PR https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/pull/25

**No automated enrolment of seven devices has been completed yet.**
There is no safe route to infer the seven missing local keys from
existing cloud configuration, and the HA API token is absent.
