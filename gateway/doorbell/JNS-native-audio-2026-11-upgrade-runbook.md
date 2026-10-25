# JNS native Home Assistant camera intercom — Core 2026.11 release-gated deployment

Updated: 2026-10-25. Status: read-only preflight workflow published, no VM updated, no new camera/sounder control enabled.

## Decision

Adopt the **native Home Assistant 2026.11 Labs two-way audio interface** on compatible camera entities instead of immediately building a separate mobile talkback UI. **Do not deploy beta/nightly software onto HA-Primary VM902 or HA-General VM905.** The expected stable date is 2026-11-04 (first Wednesday).

**Do not assume an ordinary ONVIF or Tapo C210 camera automatically supports the new feature.** Core's camera entity must declare `CameraEntityCapabilities(two_way_audio=True)`, the camera must receive a WebRTC backchannel, and the Labs option must be on. As of Oct 2026, Reolink's RTSP integration is the initial supported native path. The known JNS C210 is the Kitchen Dog Camera, NOT yet verified as the front-door camera.

## Read-only readiness automation

- Node C self-hosted runner: `.github/workflows/jns-native-two-way-2026-11-preflight.yml`
- Trigger: change `gateway/doorbell/native-two-way-2026-11-preflight.request`.
- Script: `gateway/doorbell/native-two-way-2026-11-preflight.py`.
- Uses the existing runner's trusted Node A/Node B SSH and QEMU guest-agent read capabilities.
- Reads current versions, resource allocation, backups inventory, HA Core camera registry/integration platforms, and storage. All commands are read-only; logs avoid credentials and secrets.
- On runner or VM not reachable, **do not extrapolate** readiness. Report status inconclusive.

## Upgrade prerequisites — all must pass

1. Stable HA Core 2026.11.0 or approved stable patch published; complete read of official breaking changes.
2. Separate, restorable Home Assistant backups for each target; backup volume locally accessible without depending on an offline NAS. Verify actual backup availability and rollback steps, not just a backup record.
3. Sufficient CPU/RAM/disk on target and Proxmox node during upgrade and subsequent stream activity. Do not consume scarce RAM on HA-Primary.
4. Existing MQTT services and HA-Security VM906 doorbell independent; maintain physical press → siren Y01 even if both other HA instances are unavailable.
5. Confirm the physical **front-door camera** model and hostname, integration choice, WebRTC provider, RTSP speaker/backchannel behaviour, suitable speaker output level, and HTTPS for microphone permissions.
6. Establish the mobile notification test: HA-Primary `automation.jns_primary_doorbell_phone_notification_v1` staged; it still needs an **automations-only reload** on HA-Primary and a real doorbell push test.
7. Establish a named rollback checkpoint with version, backup, config SHA, time and human approval. Avoid implicit Core restart while household automations are running.

## Deployment sequence once stable

A. **Before any upgrade:** test the current physical bell (HA-Security X15 → Y01) and HA-General `jns/security/doorbell/press` lighting. Preserve the automations and their identifiers.

B. **HA-General VM905 only:** back up and perform an approved, guarded HA Core stable-version upgrade. HA-General owns ingest and all WebRTC provider or talkback media processing, never HA-Primary. Check the native camera capabilities; an ONVIF camera might report `two_way_audio: false` until appropriate integration support is available. Do not fake `two_way_audio=True` without a genuine send-audio path.

C. **Stream readiness:** choose correct front-door camera source. Use authenticated, certificate-valid HTTPS. Configure a go2rtc WebRTC provider in a supported arrangement that does not require HA-Primary to transcode/record audio or video. Verify smooth live view before enabling microphone. Only show Talk on camera entity after WebRTC mic-to-speaker path succeeds.

D. **HA-Primary VM902:** only upgrade if required by native viewer/frontend compatibility and after a separate backup/approval. Keep control plane lightweight (mobile notification, dashboard/view routing). No FFMPEG/HLS/go2rtc server/recording on VM902.

E. **Notification user experience:** once a correct front-door view exists, change the HA-Primary mobile notification to include authenticated deep link to that view. Tap-to-open is safe cross-platform. Do not forcibly pop up the app or open microphone without opt-in.

F. **External camera speaker acknowledgement:** separate short audio clip played through verified front-door camera talkback, via HA-General only; must be disabled unless speaker codec/backchannel confirmed, never play during active conversation, cap duration/volume, configure repeat suppression. Preserve independent physical Y01 chime and existing light response.

## Rollback strategy

- If the upgrade or camera UI fails, restore the checked target snapshot/backup and previous HA Core version using the supported Home Assistant restore path. Do not roll back HA-Security or unrelated HA nodes.
- Verify MQTT and mobile notifications after any restore.
- Never make a snapshot on host storage without checking available space and its suitability (especially stand-alone A/B Proxmox).
- Camera speaker output must not remain latched if Home Assistant restarts, a stream disconnects, or phone navigation is cancelled. Obtain device-level cutoff wherever possible.

## Official references

- https://contributors.home-assistant.io/blog/2026/10/24/camera-two-way-audio/
- https://contributors.home-assistant.io/core/entities/camera/
- https://contributors.home-assistant.io/releases/how-it-works/
- https://www.home-assistant.io/integrations/go2rtc/
- https://www.home-assistant.io/integrations/web_rtc

## Live preflight audit — 2026-10-25 (Node C runner)

Source: `JNS Native Two-Way Audio 2026.11 Preflight` run `40144089485` and `JNS Native Intercom Backup Recovery Preflight` run `40144266820`. Both succeeded as **read-only** probes, not as upgrades or backup-restore tests.

| Gate | HA-General VM905 / Node B | HA-Primary VM902 / Node A |
|---|---|---|
| Core / HAOS | 2026.10.1 / 18.3 | 2026.9.4 / 18.3 |
| Supervisor | 2026.10.3 healthy and supported | 2026.10.3 healthy and supported |
| RAM allocated | **1024 MB** with balloon floor 768 MB | 2048 MB |
| HA data disk available | 21.3 GiB | 24.1 GiB |
| HA backup inventory | **empty** | **empty** |
| Proxmox snapshots | multiple; latest 2026-10-23 (before subsequent changes) | **none** |
| Host available RAM | ~2002 MB | ~1728 MB |
| Host swap used | 1824 MB | 4051 MB |
| HA backup CLI | `ha backups new` available | `ha backups new` available |
| Backup NAS | NAS active, separate WD-BACKUP target offline | NAS and WD-BACKUP targets offline |
| Current cameras | ONVIF Tapo C210 `camera.c210_mainstream` (Kitchen Dog Camera) | generic/remote C210 camera; no identified front-door camera |
| HA Core SSL flag | false | false |

**HARD HOLD**: no upgrade until new, verified/restorable, appropriately stored backups exist (including off-VM copy), host/guest memory and swap risks have been assessed, a correct front-door camera is identified, and secure HTTPS/WebRTC/backchannel support is verified. The existing Proxmox snapshots are historical, not current recovery points. Investigate Node A pve-recovery missing-PV warning independently before selecting backup storage; do not alter disk configuration as part of camera work.

`/dev/root` reporting 100% inside HAOS is the immutable OS system volume, not the Home Assistant writable data disk; data disk free space above is the relevant capacity metric.

No home-assistant backup was created by these audits; no microphone, camera speaker, VM memory, SSL, Core versions, restarts or reloads were changed.

## Refresh: 2026-10-25 11:43 UTC — read-only mobile and camera audit

- Node A/B/C 2026-10-25 03:33–03:47 UTC host and guest-purpose audits reviewed from `JNS-Steward-Diagnostics/inbox/nodea`, `nodeb`, `nodec`. Active: Node A VM900 and VM902; Node B VM905 and CT212 MQTT / CT214 Zigbee2MQTT; Node C VM906 and the deployment GitHub Actions runner. Duplicate standby VM IDs on other hosts must not be mistaken for these active guests.
- Refreshed **read-only** job [40190017309](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40190017309) succeeded on the Node C runner. No HA Core reload/restart, configuration changes, camera speaker action, or device actuation.
- HA-Primary VM902 `/config/automations.yaml` contains `jns_primary_doorbell_phone_notification_v1`: MQTT `jns/security/doorbell/press` payload `pressed` -> `notify.send_message` targeting `notify.sm_s721b`. Mobile-app SM-S721B and MQTT entries are enabled. **This proves configuration presence only**, not current runtime activation, push delivery or successful handset receipt.
- HA-General VM905 confirms the night security-lighting automations `jns_doorbell_security_mqtt_20261020` and `jns_doorbell_security_release_20261020`; their existing behaviour is preserved. Camera inventory is an enabled ONVIF `camera.c210_mainstream` identified as Tapo C210 / Kitchen Dog Camera. No positively identified front-door camera in VM902/VM905 integrations; do not repurpose the kitchen camera.
- HA-Primary's generic `camera.c210_home_arpa` and remote `camera.c210_mainstream` provide no evidence of a distinct front-door camera or a working audio backchannel. No go2rtc add-on was identified in the audited VM905 add-on list.
- Official [Home Assistant contributor post (24 October 2026)](https://contributors.home-assistant.io/blog/2026/10/24/camera-two-way-audio/) confirms Core 2026.11 native two-way audio requires integration-advertised capability, WebRTC path, Labs opt-in and HTTPS for browser microphone access. Planned stable date 4 November 2026. Do not install beta Core on these production nodes.

**Next guarded action:** plan automations-only reload of HA-Primary at a suitable idle moment (no HA Core restart) and press the *real* physical button once to confirm phone receipt and unchanged HA-Security Y01 response. If not observed, inspect a specific trace and notify delivery before retrying. Do not publish a camera deep link or chime playback until front-door camera identity and bidirectional audio route have been verified. Resolve missing Supervisor backups and HA-General 1024 MiB / host swap risk separately before any stable Core upgrade. Keep two-way audio and camera speaker acknowledgement disabled meanwhile.

### Additional legacy/security camera discovery (25 October 2026)

The new read-only workflow [40190496560](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40190496560) validated and ran `doorbell-camera-legacy-discovery-v1.py` through Node C's trusted runner. Its **camera inventory result is inconclusive**, not a finding that no cameras exist:

- Proxmox Node A **VM900 is running**, but its `homeassistant` Docker container returned **not running**. `ha core info` returned Core version 2026.9.4, `boot: false`, and `ssl: false`. This is an observed legacy Core state, **not an instruction to start it**; preserve its current role and investigate separately if needed.
- The runner has no local `qm` executable. Switching to strict SSH for Node C returned `No route to host` at `nodec`, so HA-Security VM906's camera registry was **not read**. This host resolution/reachability concern must not be confused with a loss of the working HA-Security physical doorbell.
- No third-party camera source, microphone, speaker, PTZ setting, sounder or automation was changed. The actual physical front-door camera remains **unidentified**; do not route the kitchen camera or enable any audio backchannel until positively identified.

Follow-up discovery should use an audited, currently routable Node C host management name or its established management bridge and should not weaken SSH host-key checking or introduce fixed IP dependencies. Do not infer host accessibility from the GitHub runner's own label.
