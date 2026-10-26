# JNS Home Assistant Memory and Service Separation Review

**Date:** 26 October 2026  
**Status:** Live read-only analysis completed; **NO service/database migration authorised or performed** by this report.  
**Policy:** Home Assistant Core and its critical control-plane integrations stay operational when the NAS is asleep; databases, if external, must have always-on local storage. Use DNS names, not new static device IPs. Avoid guest-ID collisions and additional server sprawl.

## Three-role resource comparison

[Internal Recorder and package audit](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40335220273) and [verified Docker add-on memory audit](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40336022644).

| Metric | HA-Primary VM902 (A) | HA-General VM905 (B) | HA-Security VM906 (A) |
|---|---:|---:|---:|
| HAOS VM physical RAM limit | 2048 MiB | 1024 MiB (balloon min 768 MiB) | 2048 MiB |
| Proxmox-reported memory used | 964 MiB | 937 MiB | 1878 MiB |
| HA Core cgroup memory | 273 MiB | 393 MiB (200 MiB cgroup swap) | Unknown (QGA absent) |
| Docker stats sum across all running HAOS services | 402 MiB | 507 MiB | Unknown (QGA absent) |
| HA Core Docker RSS-style usage | ~262 MiB | ~337 MiB | Unknown |
| HA Supervisor Docker memory | ~99 MiB | ~58 MiB | Unknown |
| Other HAOS DNS, audio, CLI, observer, multicast | ~34 MiB | ~20 MiB | Unknown |
| Unclassified other running containers | 1 / ~7.5 MiB | 3 / ~91.7 MiB | Unknown |
| Default recorder DB main file | **Absent** | **274.74 MiB SQLite** | Unverified |
| Default recorder -wal | Absent | 4.33 MiB | Unverified |
| Registered entities | 1403 | 683 | Unverified |
| Registered automation entities | 11 | 57 | Unverified |
| Config entries | 8 | 24 | Unverified |
| Devices | 42 | 90 | Unverified |
| Custom component files | 27 / ~0.16 MiB | 1931 / ~8.99 MiB | Unverified |

**Interpretation:** Proxmox-reported guest RAM is NOT the sum of Docker stats, and Docker memory cannot be simply added to PVE memory. HAOS, page cache, Supervisor and guest RAM attribution overlap. HA-Security's ~1.84 GiB usage is real at PVE level, but no evidence yet points to a particular memory-heavy addon inside that VM. **Do not cut its 2 GiB allocation until per-process/core and alarm safety verification.**

HA-General VM905, despite its much larger automation workload, runs in just 1 GiB and has ~200 MiB of in-guest container swap. It is more likely to benefit from a sensible **memory increase to ~1.5–2 GiB once Node A has capacity** than from reducing its allocation. The database is only ~275 MiB **on disk**, not 275 MiB of guaranteed reclaimable RAM.

HA-Primary has no default recorder DB file, and moving its database would achieve nothing on current evidence. It has ~1403 registered entities but only a small Core RAM footprint; entity registry count alone does not imply a memory leak.

The familiar Docker `addon_core_*` prefix was initially grouped incorrectly as Core; the refined audit classifies actual `homeassistant` once, and three other live containers on VM905 are only ~92 MiB total. Neither HA902 nor HA905 shows a dedicated MariaDB, Mosquitto or Zigbee2MQTT container through the known-role classification. The previously unclassified add-ons have now been identified as Piper, Samba and SSH, with individual memory measurements below.

## Service separation decision register

| Service / area | Decision | Why | Placement / backup & gate |
|---|---|---|---|
| **HA-Primary Recorder** | **Do not move** | No local default DB found; already a lightweight controller | Keep HAOS VM902, preserve local configuration and off-host HA backups |
| **HA-General Recorder** | **Keep SQLite for now** | Only 274.74 MiB main DB; existing heating thermal learning / recorder history important; changing engine does not support migrating existing history | Apply measured retention/exclusion tuning only after preserving history, confirming entity dependencies and consistent HA backup |
| **HA-Security Recorder** | **Audit first; do not offload blindly** | No guest agent, actual DB/addon memory unknown; alarm reliability takes priority | Keep recorder local until full internal resource inventory; preserve stopped Node C VM906 and off-host recovery backup |
| **MQTT broker** | **External LXC already exists** | Live Node B CT212, Node A collision-free cold-stage CT230 already prepared | Complete final quiesced sync + Node A activation, one broker, consumer migration and rollback; back up local ZFS to NFS |
| **Zigbee2MQTT** | **External LXC already exists** | Live Node B CT214, staged Node A CT231; avoids inside-HA process | One coordinator and one active controller, test CT210 TCP bridge/device state; scheduled NFS backup |
| **Audio services** | **Review VM214 before another LXC** | Existing dedicated audio VM on Node A with USB dependencies; HAOS builtin audio container is small | Avoid duplicate MPD/Piper processes; new audio LXC only if consolidation saves more than it costs and preserves USB |
| **Camera ingest/WebRTC** | **Potential separate LXC after profiling** | Real video transcoding is a plausible CPU/RAM driver, but current Docker audit does not prove an internal media server | Dedicated lightweight local-ZFS LXC on normally-on Node A only after measured load, signed restore config, tested RTSP+two-way audio and HA controls kept on VM905 |
| **ESPHome compile/build** | **Good candidate if found on VM906** | Bursty builder load can be moved without moving the alarm itself, but it is NOT yet proven installed | Prefer existing available management services or one backed-up LXC on Node C; alarms and live device connectivity must not depend on compiler uptime |
| **Logging/diagnostics** | **Use existing CT services, no new duplicate** | JNS logger containers and Steward already exist; sprawl risk | Consolidate established logger/Steward pathways; verify namespace, retention and NFS backup |
| **Plant Manager analytics / long-term SQL** | **Optional future isolated database** | Could justify MariaDB/Postgres if workloads/queries outgrow SQLite, independent of HA Recorder | One backed-up always-on ZFS-based LXC with distinct DB/users and automatic verified SQL dumps. No need for one LXC per HA instance. |

### Confirmed non-core services and actual memory

[Sanitised service classification](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40336820968) and [individual live memory check](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40337072916) identify the formerly unclassified Docker services:

| HA instance | Service | Docker memory at sample |
|---|---|---:|
| HA-Primary VM902 | SSH management | **7.5 MiB** |
| HA-General VM905 | **Piper TTS** | **51.1 MiB** |
| HA-General VM905 | **Samba shares** | **30.4 MiB** |
| HA-General VM905 | SSH management | **3.1 MiB** |

These are independent instantaneous samples and need not total exactly to the first Docker-stat aggregate. **None represents a hundreds-of-MiB always-on service that obviously merits a new LXC solely for RAM.**

**Precise decisions:**
- Piper can run on an external LAN-hosted [Wyoming Protocol server](https://www.home-assistant.io/integrations/wyoming/), leaving HA-General automations and voice responses intact. But the measured idle footprint is only ~51 MiB. Prefer relocating to the **existing** production audio environment (VM214) **only if** the target has voice model storage, adequate CPU/latency and no conflicting Piper instance. Otherwise defer until Node A capacity is upgraded. Test existing bedtime TTS phrase, volume, 750 ms delay, MPD output, and HA restarts in a staged fallback sequence.
- Samba consumes ~30 MiB. It could potentially be removed if a checked Samba-share access audit confirms no live client, file deployment, recordings or backup workflow depends on it. Keep SSH until an authorised remote management replacement is tested.
- HA-Primary's ~7.5 MiB SSH service should not be targeted for RAM savings; it provides recovery access.
- Do NOT remove Piper or SSH automatically. No changes in HA runtime have been applied.

### Reasons to avoid immediately moving HA Recorder into a MariaDB LXC

Home Assistant [official Recorder documentation](https://www.home-assistant.io/integrations/recorder/) states that **SQLite is its default recommended database**, is optimised, and warns **history migration when changing database engines is unsupported**. A database LXC incurs its own RAM, OS, backup, permissions, storage, and start-order overhead, while Core still keeps live state/automation logic in memory. Moving a 275 MiB *disk* file to a remote database is not a credible ~275 MiB *RAM* saving.

If a dedicated SQL LXC becomes justified later:
- Use local ZFS on an always-on Proxmox host. Do **not** place a live SQLite DB on NFS; the large NAS is supposed to sleep.
- Keep an individual database/user per HA instance, TLS/ACLs, DNS-first service endpoint, and a rollback plan.
- Back up **both** HA configuration and SQL transaction-consistent dumps or physical snapshots. Home Assistant's normal HAOS backup cannot be assumed to contain an external recorder DB.
- Plan an explicit *new* history cutover; do not promise old history automatically survives unsupported SQLite→SQL conversion. Keep immutable old archive readable for audit.
- Test restart, unavailable DB, automatic recovery and retention policy before production rollout.

## Measurable next actions, in order

1. **Resolve HA-Security blind spot**: obtain *read-only* cgroup/add-on/recorder stats from VM906 through an authorised guest access method (HAOS console/credentialed Supervisor diagnostic); distinguish Home Assistant Core, Supervisor, OS cache and memory used by any ESPHome/audio/other apps. Do not reduce security VM memory until alarm readiness tests and a protected backup.
2. **Identify the 3 unclassified VM905 and 1 VM902 service containers** by service role via an authorised metadata-only audit, to determine if redundant before removing anything. Their collective cost is limited (~92 MiB/~8 MiB).
3. **Protect HA-General history** with HA-consistent encrypted backup to off-host storage and record the recovery key; capture Recorder's effective purge/exclude settings (potentially imported packages) and its use by the JNS heating/thermal learner.
4. **Prioritise moving already-external MQTT and Zigbee2MQTT** to their staged Node A LXCs, not creating another server. Make sure A has sufficient RAM and only one active broker/adapter.
5. Complete Node A RAM capacity change plan (at least 16 GiB if hardware supports it) and validate current swap under representative overnight load before moving HA-General and Plant Manager from B. The VM905 source remains live until coordinated cutover.
6. Implement automated, off-host **full guest and app-consistent backups** in scheduled NAS-wake windows, with verified restore rehearsals. Since NAS sleeps, maintain at least one always-available local recovery path for alarm-critical services.

**Operational change status:** no recorder engine changes, no VM resizing, no new LXCs and no service migrations in this audit.
