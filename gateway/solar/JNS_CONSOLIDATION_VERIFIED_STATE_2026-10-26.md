# JNS Home Intelligence — verified consolidation state (2026-10-26)

**Scope:** HA-Primary VM902, HA-General VM905, HA-Security VM906; Plant Manager
VM903 cold retention; ESPHome tools VM991; Guardian/Lunar CT115/116/117.
Use DNS names and the existing Node C GitHub Actions gateway. No unrestricted
Node C runner root assumed. **Leave all Home Assistant recorder databases, history,
integrations, dashboards, automations and credentials unchanged.**

## Verified work completed

1. **VM906 host-side QGA enabled**, with a private original Proxmox config backup
   and successful post-change comparison. VM906 remains running; QGA ping is still
   unsuccessful because the guest has not undergone a cold start after the
   virtual agent channel was enabled. No alarm service restart or guest-file
   changes performed.
   - [Agent config workflow](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40347166620)
   - [Resource restart readiness](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40351523693)

2. **Plant Manager VM903 preserved as cold offline backup.** Originally found
   running on Node B with onboot=1. A full live safety archive was verified,
   the VM shut down gracefully, onboot was changed to 0, and a second full cold
   archive was produced and verified. Original VM config and disk remain intact
   on Node B. Both archives passed zstd integrity checks and SHA-256 hashing.
   The manifest remains stored with the backups. VM903 is now **stopped,
   onboot=0**, independently confirmed after the backup.
   - [Original archive and shutdown](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40348349032)
   - [Independent VM state verification](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40350349297)
   - [Second backup replication](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40350824031)

3. **Both VM903 archives and manifest also replicated to Node C's mounted NFS
   backup storage**, independently SHA-256 verified. No VM903 guest created or
   started on Node C, and the Node C local thin-pool capacity is preserved.
   **An actual restore test has not yet been performed.** Backup storage ACL,
   encryption-at-rest and full NAS-wake restore rehearsal remain outstanding.

4. **HA-Security network triangulation:** all three nodes can resolve its DNS
   name and establish TCP connection to port 80, but not 8123/443.
   HA-Primary and HA-General likewise did not answer on direct port 8123.
   Treat direct 8123 failure as an exposure/proxy question, NOT proof that Core
   or alarm functions are down. No application-authenticated health test yet.
   - [Three-node network check](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40351917475)

## Outstanding safety gates

- **VM906 QGA completion:** The HAOS virtual-machine image includes
  qemu-guest-agent; enabling the Proxmox guest-agent option alone does not
  hot-add the required virtio-serial channel to the currently running QEMU
  process. Cold shutdown/start is pending a fresh, verified recovery backup,
  resource capacity and alarm-state/health confirmation. At audit, Node A had
  ~2042 MiB available RAM and ~3470 MiB swap in use. Do not force an
  unguarded outage. Once active, rerun the three-role resource and addon audit
  and determine if an ESPHome Device Builder really exists inside VM906.
- **VM991 on Node C:** Latest private diagnostics (03:38 UTC) showed the
  stopped 3 GiB guest named ha-tools-esphome with 32 GiB disk. The ordinary
  Node C runner cannot read VM991 Proxmox configuration or offline disks.
  The installed privileged JNS gateway does not expose a scoped VM991 read-only
  inspection handler. Do not start/delete VM991 or circumvent that permission
  boundary. Add/approve a narrowly scoped offline inspection capability,
  then inspect VM config, firmware builder service and data without booting.
- **Guardian/Consul/Lunar:** No Corosync cluster configuration on Node A/B/C.
  Live Node A CT116 has active Consul and Lunar. Live Node B CT115 has active
  Lunar but Consul stuck in 'activating' at repeated checks. Latest saved Node C
  inventory shows running CT117 with Consul/Lunar; runner lacks privileged
  read access to interrogate it live. Existing Consul CLI/raft probes were
  unavailable, so quorum/dependencies are unverified. No Guardian changes
  authorised by these findings. Before any retirement, map consumers and
  replace quorum-dependent behaviour with the desired two-node/self-monitoring
  design; ensure essential Node A services work while Node B is off.
- **Databases:** NO recorder engine conversion, SQL migration, purge, archive
  deletion, or retention adjustment. Preserve existing history and thermal
  learning references.

## Independent current role placements

- HA-Primary VM902: **Node A, running**
- HA-General VM905: **Node B, running**
- HA-Security VM906: **Node A, running**
- Plant Manager VM903: **Node B, stopped, onboot=0, cold archives on two NAS-backed locations**
- Legacy HA900: **stopped**
- VM991 ESPHome tools candidate: **Node C, last inventory stopped; contents unverified**

Node B must not be powered off solely on this report while HA-General
and other live Node B services remain active.

## Follow-up architectural correction — 2026-10-26

The production architecture now explicitly has only three HA roles:
- VM902 HA-Primary: lightweight presence/control/dashboard
- VM905 HA-General: lighting/heating/fans/bedtime/normal automations
- VM906 HA-Security: alarm, doorbell and security ESPHome device integration

Guardian/Consul/Lunar CT115/116/117 originated with the **retired HA900/HA901
monolithic active/hot standby** architecture. They are *not* quorum members
of a Proxmox cluster, and should not be silently relabelled as required
for the three-role HA design. They are **retirement candidates, not
yet disabled**. The live read-only Guardian dependency audit found:
- Node A CT116: 49.3 MiB observed RAM; configured max 256 MiB;
  active Consul and Lunar.
- Node B CT115: 56.8 MiB observed RAM; configured max 256 MiB;
  Consul stuck activating, active Lunar.
- Host unit references on A and B: jns-cluster-proxy.service,
  jns-ha-guardian-probe.service/.timer,
  lunar-discovery-export.service/.timer.
- 0 established TCP connections to typical Consul ports from either host
  at one sample. This does **not** prove all external consumers absent.
- Node C CT117 still needs a privileged dependency audit; preserve it.
- No containers, timers, Guardian jobs or configurations were disabled.

[Guardian dependency audit](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40354985992)

VM9906 haos18-golden on Node C was originally created 2026-10-15 from
a full clone of HA-Security VM906 and converted to a Proxmox template,
as reported in the prior deployment discussion. The template copied
its guest configuration/identity/credentials and **no sanitation proof
is recorded**. Do NOT clone into production until a sanitised replacement
is verified. The old 2026-10-23 inventory phrase 'clean baseline' is not
sufficient sanitation evidence. Retain the source offline.

VM991 ha-tools-esphome was created 2026-10-05 as an on-demand ESPHome
Device Builder HAOS 18.3 VM, originally 2 vCPU, 3072 MiB RAM and 32 GiB
disk, onboot disabled. Previous deployment report states ESPHome
Device Builder 2026.9.1 installed, zero commissioned devices and Matter
Server removed. User now reports a 512 MiB RAM figure; confirm the
present Proxmox Hardware memory **versus balloon minimum** before
starting or resizing it. Current guest contents remain unverified by
the ordinary Node C runner, whose privileged access is deliberately
restricted. Keep the workshop stopped in standby until needed.

Preserve all Home Assistant databases and recorder history unchanged.

## Final same-day consolidation results — 26 October 2026, 16:55 UTC

**This section supersedes earlier pending VM906 QGA and Guardian A/B status
in this document.** All live Home Assistant databases and recorder history,
integrations, dashboards, automations, credentials and security device pairing
have been retained. HA-Security alarm/doorbell physical end-to-end testing
remains a separate requirement.

### VM906 QEMU guest-agent and recovery

- Proxmox agent device was enabled by the previously verified config-only
  change.
- Before interrupting the VM, a fresh native Proxmox compressed snapshot
  archive of VM906 was created on Node A and replicated to the Node B NAS:
  **2,841,275,559 bytes**, source and off-host SHA-256 comparison passed and
  Proxmox configuration copy matched. Recovery archive preserved; full
  restore rehearsal not performed.
- An attempted `qm shutdown 906 --timeout 180` exited nonzero, but later
  audits confirmed VM906 **had actually stopped**. No force-stop was used.
- A separately gated, identity-verified recovery workflow started the
  **same Node A VM906** only after confirming it was stopped, with no duplicate
  HA-Security controller. Guest-agent ping succeeded; `qm status 906` is
  running; `ha core info` and core Docker service verified.
- **VM906 QGA is now operational**. Its future maintenance shutdown scripts
  must not infer that a nonzero graceful-shutdown exit code means the guest
  remained running: always re-read Proxmox state before doing anything.
- [Full VM906 off-host backup](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40357102982)
- [Graceful-shutdown error (failed closed)](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40359465817)
- [Safe same-guest resumption and QGA confirmed](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40360474345)

### Why VM906 appeared much larger than VM902

Proxmox had reported VM906 at 1,878 MiB and VM902 around 964 MiB before
the restart. VM906 temporarily fell to 821 MiB just after startup, then
rose to 1,816 MiB after Core finished starting. This alone is **not
evidence of a leak**: the Linux guest memory breakdown showed:

| Metric | VM902 Primary | VM906 Security |
|---|---:|---:|
| MemAvailable | 1,359.1 MiB | **1,019.9 MiB** |
| Cached | 948.8 MiB | **821.9 MiB** |
| AnonPages | 489.1 MiB | 769.5 MiB |
| Swap usage | 0 MiB | **0 MiB** |
| Memory PSI some/full (10/60/300 sec) | 0/0/0 | **0/0/0** |

There is **no observed guest swap or RAM pressure** at the sample. PVE guest
memory includes reclaimable cache; do not assume 1,816 MiB is all committed
nonreclaimable application memory. **Keep VM906 at 2 GiB**, do not resize
it down until longer-term runtime trending and alarm load tests justify it.
[Direct HAOS Linux guest cache/pressure audit](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40363591142).

A more representative Core comparison found VM902 Core cgroup approximately
274.5 MiB versus VM906 approximately 706.6 MiB, with 8 versus 20 configured
integration entries. VM906 has 548 entities, six automation entities,
an ESPHome integration with 35 entities, and an unused Matter integration
entry (zero registered Matter devices/entities). VM906 recorder SQLite file
is 12.82 MiB and remains unchanged.

VM906 has a separate Matter Server container (not a listed Supervisor
add-on), measured at 272.2 MiB then 135.7 MiB at separate points,
with Docker restart policy `no`. It is a **possible future saving,
not currently disabled**. A guarded stop was attempted only after verifying
no Matter devices; its post-health check did not pass, so the workflow
restarted the *same* container. Later independent audit confirmed
the Matter container running, HA Core running, 35 ESPHome entities
unchanged, and HA-Security HTTP reachable. We must not claim Matter
has been permanently offloaded or disabled.
- [Matter/ESPHome role, integration and RAM audit](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40361243624)
- [Matter stop fail-closed and rollback](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40362829025)
- [Independent post-rollback service health](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40363064198)
- [All three HA roles settled Core/recorder comparison](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40363286646)

### Guardian cold retirement

The old HA900/HA901 Guardian/Consul/Lunar monolithic promotion plane is
not part of the current three-HA-role design. No host runs a Proxmox
Corosync cluster. The final dependency audit found the host-level
Guardian/cluster-proxy and Lunar-export units do not refer to
HA902/905/906, MQTT, Zigbee or Sheriff DNS. Node B's Natural Automation
Guardian terms were confined to archived/knowledge JSON rather than
executed Python or shell code. Node A maintenance CT118 watchdog
unit showed no Guardian/Consul/Lunar dependency.

- **Node B CT115 Guardian01: stopped, onboot=0**, legacy cluster-proxy,
  Guardian probe timer and Lunar export timer disabled. Original
  guest disk/config and unit files intact, private recovery manifest.
  HA-General, MQTT, Zigbee2MQTT, Sheriff DNS, and other HA endpoints
  verified after stop.
- **Node A CT116 Guardian02: stopped, onboot=0**, same obsolete host units
  disabled. Original CT config/disks and unit files retained, private
  rollback manifest. HA-Primary, HA-General, HA-Security, Zigbee bridge
  CT210 and DNS verified after stop.
- **Node C CT117 Lunar03: unchanged**, last screenshot/inventory shows
  running. Node C runner is unprivileged and its trusted gateway currently
  has no approved CT117 operations. Do not bypass the security boundary.
  Confirm remaining Node C monitoring dependencies and stop via an
  authorised Node C Proxmox operator before declaring all Guardian retired.
- [Node B Guardian01 retirement](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40361430272)
- [Node A maintenance watchdog dependency gate](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40361806635)
- [Node A Guardian02 retirement](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40361998091)

### Other placement and safety decisions

- **HA-Primary VM902 Node A remains running and lightweight**.
- **HA-General VM905 Node B remains running**, as do its production MQTT
  CT212 and Zigbee2MQTT CT214. Node B MUST NOT be powered off yet.
- **HA-Security VM906 Node A remains running**, guest agent operational.
- **Plant Manager VM903 Node B is stopped, onboot=0**, with both verified
  live-safety and cold archives on Node B NAS and independently replicated
  to Node C NFS backup storage. Original VM disks/config retained.
- **VM991 `ha-tools-esphome` is correctly allocated 3 GiB**, user
  confirmed earlier 512 MiB value was a transient Proxmox webpage error.
  On-demand commissioning VM remains stopped; do not resize/rebuild.
- **VM9906 haos18-golden stays offline**. Original cloned identity was not
  documented as sanitised, so not an approved clean production template.
- **All databases remain unchanged**: no SQLite engine changes, history purge,
  recorder migration, deletion, retention changes or entity renaming.

Production readiness next: physically verify HA-Security's ESPHome/KC868
doorbell/alarm path and independent HA Core HTTP/API after restart; finish
Node C CT117 privileged retirement after local dependency validation;
perform restore drills for saved snapshots before any source VM deletion.

## 21:23 UTC Matter Server reduction — user request after porch bulb diagnosis

The user confirmed the **front door porch bulb is blown**, accounting for the
physical lamp not illuminating (replace bulb separately). No change to the
doorbell, alarm or lighting devices is attributed to this statement.

HA-Security VM906 has **no Matter devices or entities**, one enabled Matter
Core integration and official Matter Server add-on `core_matter_server`
v9.2.0. The app was `boot:auto`, `state:started`, `watchdog:false`,
and `system_managed:false`.

**Successfully changed:** `core_matter_server` setting from
`boot:auto` to `boot:manual` via authenticated Supervisor API using
the HAOS CLI container and the existing Node C GitHub gateway. Last read:
`boot:manual`, `state:started`. The app was not uninstalled, HA was not
restarted, and all databases, Matter configuration and ESPHome devices remain
preserved.

Important: attempted native stop was rolled back after the still-enabled
Matter integration restarted the app. Disabling automatic boot alone does
NOT keep it stopped while the Matter integration remains enabled. The
available service-to-Core WebSocket tokens were rejected as admin
credentials, so **Core integration disable was NOT performed**. Do not
manually edit `/config/.storage/core.config_entries` while Core is running.
User must go to HA-Security Settings > Devices & Services > Matter >
Disable (NOT Delete), then to Settings > Apps > Matter Server > Stop.
Start on boot is already disabled. Only mark full retirement complete after
Supervisor verifies both `boot:manual` and `state:stopped`.

- [Verified persistent manual boot setting](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40403949991)
- [Previous managed disable rollback](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40403144566)

Do not change SQLite recorder, entity registries, KC868/siren assignments,
HA-General lighting or MQTT/Zigbee service placement to complete this
optimisation.


## Node C obsolete HA-Golden template retired — 28 October 2026

**Operator-executed and script-verified (per supplied Node C root terminal output):**
At `2026-10-28T11:04:45.474375+00:00`, root on Node C invoked
`gateway/solar/nodec_golden_vm9906_guarded_retire_20261028.py --execute`.
The guard confirmed the exact `haos18-golden` identity of **VM9906**, stopped
and template states, disabled autostart, precisely two expected disks, **zero
dependent LVM linked volumes** and **zero references from other VM configs**.
Post-deletion verification emitted
`stage=verified_removed`, `removed=true`,
`template_disks_removed=true` and `other_vms_untouched=true`.

**Scope:** Only the obsolete Node C VM9906 HAOS golden template. This is
not a deletion or cutover of Node C VM906, VM909, VM991, CT130, CT249 or any
production Home Assistant machine. VM9906 had been a cloned, unsanitised
HA-Security image and was not an approved reusable golden template.

**Storage accounting:** The template's two disks were reported removed,
but **physical local-lvm free-space reclaimed has not yet been quantified**;
the 32 GiB nominal guest disk is thin-provisioned and must not be reported as
32 GiB saved. A fresh `pvesm status` before/after comparison or
`lvs` pool data-percent measurement is needed for actual savings.

**Evidence:** User-supplied root console output from Node C, plus the
repo-controlled retirement code:
`gateway/solar/nodec_golden_vm9906_guarded_retire_20261028.py`.
No unsupported privilege escalation was used by the GitHub runner; deletion
was performed locally by the authorised privileged operator.

### Post-removal Node C storage measurement — 2026-10-28

User-supplied Node C `pvesm status` shows `local-lvm` used 27,129,546 KiB, available 12,458,293 KiB, utilisation 68.53%. Pre-removal Steward inventory (2026-10-28 03:35 UTC) showed used 32,414,523 KiB, available 7,173,316 KiB, utilisation 81.88%. **Verified saving: 5,284,977 KiB = 5.04 GiB**, a 13.35 percentage-point reduction in thin-pool utilisation after VM9906 golden template removal. This is actual pool-space recovery, not nominal virtual disk capacity.
