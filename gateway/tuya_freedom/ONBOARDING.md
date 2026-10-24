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
