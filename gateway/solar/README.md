# JNS Solar Economy — guarded consolidation runbook

Status: **AUDIT / NOT APPROVED FOR CUTOVER**. No VM, CT, NAS, host, quorum, or automation has been modified or powered down by this workstream.

## Goal

Run production Home Assistant, security, MQTT, Zigbee, DNS and house control on **Node A** where capacity and dependency checks allow. Keep **Node C always on for the JNS Steward server, GitHub runner and management/diagnostics plane**. Keep **Node B powered down** until recovery or maintenance needs it. Power down the high-draw NAS only after safe backup completion and storage release.

Retain DNS-first addressing and the established GitHub Node C trusted inspection/deployment path permanently on the management-plane host. Preserve VM903 Plant Manager's configuration, VM905 HA-General automations, VM902 lightweight Primary, VM906 HA-Security, camera ownership on VM905, and all history/authentication.

## Live preflight — 2026-10-24

Read-only workflow: `.github/workflows/jns-solar-economy-readonly-audit.yml`
First successful audit run: https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40110302861

**Node A:** 6 logical CPUs; ~8 GB RAM; ZFS vmdata ~828 GB available. Running VM900 (4 GB) and VM902 (2 GB), VM214 house-audio (USB), CT116 Guardian, CT118 maintenance, CT210 Zigbee bridge, CT212 **jns-log-a**, CT215 NTP, CT247 Sheriff DNS. VM903/VM905 *stopped copies* also exist locally. VM902 onboot=0; VM900 onboot=1.

**Node B:** 4 logical CPUs; ~8 GB RAM; ZFS vmdata ~360 GB available. Running VM903 Plant Manager (2 GB), VM905 HA-General (1 GB configured in observed hypervisor inventory, not a verified safe production minimum), VM219 house-audio USB, CT115 Guardian, CT212 **mqtt-infra-a**, CT213 logger, CT214 Zigbee2MQTT, CT216 time, CT220 management, CT248 Sheriff DNS, and a host-level `natural-automation.service`.

**Node C:** ~8 GB RAM with ~4.2 GB available and ~2.1 GB swap in use; guest configuration IDs include VM906/909/990/991/9906 and CT117/130/131/249, but some live states are still unverified. Node C hosts the current GitHub self-hosted runner, DNS reservation importer, JNS management bridge, and running CT117, CT130, CT249, among other workloads. VM906 HA-Security is reported on Node C by historical audits; confirm live state before any shutdown. Node C remote root SSH was not available via the current runner; separate local unprivileged audit is in progress.

**Storage:** Node A `vmdata` is local ZFS, not a magical shared disk with Node B's separately named `vmdata`. Node A's `NAS` CIFS storage was inactive; Node B's `NAS` CIFS was active. Both `WD-BACKUP` NFS backends were inactive **while enabled backup jobs still referenced them**. Both hosts had DNS-related NFS mounts. Confirm which physical NAS provides each share and whether DNS requires it continuously.

**Critical collision:** CT212 is DIFFERENT ON EACH NODE: Node A logs vs Node B MQTT. VM900/902/903/905 are also defined independently on both hosts (some copies stopped). **Do not invoke a bare `pct migrate 212`, `qm migrate 905`, or start stopped duplicate copies.** First prove whether hosts are in one Proxmox cluster, verify each guest's current source disk/config/checkpoints, then use collision-free IDs / supported migration or backup+restore. Do not copy stale images over live instances.

**Live cluster check:** Node A and Node B each report NO /etc/pve/corosync.conf and no configured Proxmox cluster. Local duplicate VMIDs are real and therefore require cross-host remapping; they are not in-cluster guest IDs. Do not try a standard same-cluster qm/pct migration. Solar mode will retain independent Proxmox hosts and the requested two-node safety policy, not add a quorum witness. Node A had ~1542 MB available and ~3894 MB swap in use; Node B ~1976 MB available and ~1871 MB swap in use.

**RAM blocker:** Node A cannot safely run all existing HAs plus unchanged VM900 at current physical RAM. Reserve RAM for the PVE host, ZFS ARC and essential CTs. Consider retiring VM900 only after feature parity is tested, leaving it as an offline fallback, or increase Node A RAM. RAM headroom must be **measured**, not inferred from assigned vCPU count.

## Live service-parity and NAS dependency audits — 2026-10-24

Read-only Home Assistant parity: https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40112580253

- VM902 HA-Primary: reachable Home Assistant Core; 10 enabled registered automations; MQTT and mobile_app entry present.
- VM905 HA-General: reachable Home Assistant Core; 56 enabled registered automations, 17 package YAML files, Lyric and JNS heating integrations; local recorder database ~228 MB.
- VM900 HA legacy: Docker accessible but Home Assistant Core container **not running**. Container inventory: 21 containers, 19 running. Known *still running* roles: audio, DNS (2), ESPHome, multicast, observer, Piper, SSH, Supervisor. Matter-labelled container stopped. Several containers not role-classified: **do not shut down VM900 or assume Core stoppage means no dependent services**. Audit actual service endpoints and migrate/replace any active dependencies first.
- VM900 guest configuration parity cannot be measured by Docker exec until Core container is running; **do not restart VM900 Core merely to perform this audit**, because it could interfere with lean production automation and Zigbee control. Use a guarded offline snapshot or explicit non-disruptive inspection instead.

Read-only NAS/DNS backend relationships: https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40112737025

- DNS master/live NFS mounts are present on both Nodes A/B and resolve to the *same* backend.
- Both DNS NFS mounts resolve to backends **different** from the configured `NAS` CIFS and `WD-BACKUP` NFS server endpoints. These results prove backend separation at audit time, not that NAS shutdown is safe for every workload.
- `NAS` CIFS is currently **mounted on Node B** but not Node A; `WD-BACKUP` NFS is mounted on neither, despite enabled backup schedules. The two NAS storage definitions also target different backends.
- Before any NAS sleep: prove no active CIFS file handles, recordings or dependent services; validate a successful backup/wake/reachability cycle; unmount or quiesce Node B's CIFS cleanly, and confirm OS-level NAS shutdown and the Tuya recovery safety interlock.

**Decision:** Production cutover and NAS/Node B power-off remain BLOCKED pending service migration, snapshots, capacity and rollback verification.

## Additional mandatory migration: HA-Security VM906 (Node C → Node A)

This is **in scope for Solar Economy**: HA-Security VM906 will move to production Node A while Node C remains the always-on Steward and management server. Current Node C VM906 service is the authority for manual alarm logic, ESPHome/KC868-A16 security endpoints and future SecureAssist integration. The approved target is **Node A**, keeping DNS name `ha-security.home.arpa` managed dynamically by Sheriff (no fixed addressing/DHCP reservations).

**Migration safety conditions:**

1. Read live Node C VM906 configuration and state, disk pool/size, EFI, TPM, guest agent, USB/serial passthrough and snapshots; verify Node A has no VMID 906 collision and supports the guest hardware mapping. Read-only workflow: `.github/workflows/jns-solar-ha-security-preflight.yml`.
2. Quantify total Node A RAM with **VM902 (2 GB), VM903 (2 GB), VM905 (1 GB configured), VM906 (~2 GB expected; verify), MQTT, Zigbee2MQTT, audio and core infra**, allowing host and ZFS headroom, and without depending on swap. VM900 Core being stopped is not enough: its 19 live auxiliary containers need an ownership/dependency check before VM900 retirement. **RAM/CPU load test gates must pass**; evaluate physical memory expansion before any cutover.
3. Preserve Home Assistant security identity, encryption/API keys, alarm entity IDs, original automations, ESPHome device ownership, KC868 doorbell/tamper functionality, event histories, backups and MQTT read-only transport. Never enrol a duplicate active ESPHome security controller or trigger a secondary alarm engine.
4. Take a consistent source backup/snapshot and a tested restorable copy; use cross-host restore/remote copy with digest validation since Nodes A/B/C are independently managed. Do not assume Proxmox shared storage, and do not operate both source/destination VM906 instances simultaneously.
5. Install and stage an offline guest copy (no production network attachment or alarm output) on Node A if resources permit. Preserve its identity and storage ownership; confirm config parity with source before stopping original. For actual cutover, coordinate controlled source shutdown, preserve desired alarm state and alert pathways, bring up only the new guest, verify `ha-security.home.arpa` resolves to its live address and all alarm/tamper/doorbell paths work, then monitor and explicitly mark source as non-booting standby.
6. Reversal: if security monitoring or alarm control fails, shut down the target first, then restore the original Node C VM906 and DNS identity after checking network uniqueness; restore the previous security state and verify notifications. Never leave both armed controllers running.

**Node C stays powered on by design.** Keep the Steward, GitHub runner/deployment gateway, management bridge, DNS importer and required CT117/130/249 on Node C. Only the HA-Security workload moves to Node A. Target is two powered hosts (production A + management C), with B and large backup NAS normally off.

## Steward placement and Node C power policy — live audit

Read-only placement audit: https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40119338960

- User-approved steady state: **Node C remains powered on for Steward, management and the GitHub gateway**. Node B can sleep after production and its remaining services have migrated; Node A owns live house control.
- Node C currently has a protected /var/lib/jns-steward directory; it is **not writable by the unprivileged GitHub runner**. Node C management bridge and DNS reservation importer are active.
- Tested Node C systemd unit names natural-automation.service, jns-steward.service and jns-steward-agent.service are currently **not installed or inactive** at the host level; do not claim Steward has already moved. It could run inside an LXC or under a differently named service and needs explicit verification.
- Node B currently runs **natural-automation.service** with its knowledge directory under /opt/natural-automation/data/knowledge. Preserve the live Natural Automation/Steward stack and working state before Node B shutdown. Do not clone service private keys or blindly copy credentials to Node C.
- No need to move the Node C GitHub runner. Any full HA900 add-on manifest must be transferred to the protected Node C Steward store through an explicitly restricted, verified local importer. The public GitHub repository retains safe aggregate metadata only.
## HA900 cold reference and supporting-service cleanup

**Approved objective:** After dependencies are moved and documented, move HA900 from Node A to Node C as a **stopped, non-autostart reference** and remove unnecessary supporting-service runtime payloads to save disk space. Node C continues running the independent Steward and management services. HA900 itself must not have an active network, Zigbee, alarm, MQTT or automation role.

**Storage constraint (live audits 2026-10-24):** HA900 has a 256 GB provisioned virtual disk, approximately 27.9 GB referenced data and 44.4 GB ZFS-accounted usage. Node C root had only ~5.9 GiB free on an 80 GiB host disk. Further datastore capacity checks are needed; a thick 256 GB restore is NOT authorised. Reducing auxiliary containers and compacting a sparse archival image may help, but must not compromise recovery.

**Ordered safe procedure:**

1. Inventory and document every HA900 add-on and container: purpose, version, image, enabled status, ports, data locations, settings, backup methods, dependent consumers and which live lean-node service supersedes it. The earlier audit found 19 running containers; identified roles include DNS, ESPHome, audio, Piper, multicast, SSH, observer and Supervisor. Unknown service consumers block cleanup.
2. Record the complete service manifest and configuration exports in **protected onsite Steward storage on Node C**, with secrets, encryption keys and auth tokens restricted to authorised local access. Never publish raw config, identities, network addresses, credentials or exports to public GitHub or GitHub Actions logs. Save only redacted roles/versions/progress publicly.
3. Before any deletion, produce a full **independently restorable pre-cleanup backup** of HA900 with Supervisor, service config, addon data, encrypted secrets, HA history and relevant ZFS/VM configuration. Verify backup digest, the off-host copy, restore/decryption feasibility and location before any destructive step. Preserve one unmodified complete recovery copy even after slimming the reference guest.
4. Confirm every live consumer has been moved away or is deliberately retired: especially ESPHome/KC868 security, DNS forwarding, TTS/Piper/audio, MQTT/Zigbee and remote management paths. Verify replacement service health and retain rollback.
5. Strip **only a disposable staged copy**, not the live source: uninstall identified redundant add-ons via supported HA Supervisor methods where possible, preserve exported configs and safely remove unused image layers without deleting required Docker volumes, HAOS data partitions or Supervisor state. Reclaim sparse blocks only with filesystem/storage-format-aware operations and verify saved bytes.
6. Place a slim, verified cold-reference guest or importable snapshot on Node C under a collision-free VM ID with adequate datastore headroom. Keep guest stopped, onboot=0 and network disabled so it cannot conflict with live HA. Document cold boot/reference procedures but do not boot it on the production network.
7. Only after backup, cold-copy integrity, consumer checks and explicit safety gates pass: cleanly shut down the original Node A HA900, set onboot=0 and remove its Node A disk via the guarded migration cleanup. Record all removed image/container/volume identifiers, the config archive pointers, cleanup timestamps, checksums, reclaimed GiB, and rollback instructions in the always-on Steward.

**Do not claim cleanup finished until the archive is verified and service payloads are actually removed.** Current status is read-only assessment; no HA900 services or volumes have been deleted.
## HA900 private service register — captured

Read-only private manifest capture succeeded: https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40119664083

- 2026-10-24: **21 containers recorded, including 19 running**.
- A root-only manifest containing names, images, versions as encoded in image tags, states, declared ports and mount metadata was written on **Node A** under /var/lib/jns-solar/ha900/evidence (directory mode 0700, manifest mode 0600). This is deliberately not in public GitHub or public CI logs.
- SHA-256 evidence: 77555d0defa1574c7e4d22e63130a42e8958766264b713b2e9f361524a221e82.
- **This is metadata capture, not a complete configuration/secret export or restorable backup.** Capture and verify full service configurations in protected backup storage before stripping any add-ons or images.
- Protected importer to the always-on **Node C Steward** is not yet verified; the unprivileged GitHub runner cannot write Node C's existing /var/lib/jns-steward directory. Do not claim Node C already has the private manifest.
- Container removal, guest slimming, off-host backup and VM900 relocation have **not** happened. HA900 remains on Node A until consumers are verified and storage/restore tests pass.
## Continuation evidence — 2026-10-24

**Private HA900 inventory copied from Node A to Node C** (without disclosing service details). [Verified transfer](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40122911210) matches original manifest SHA-256 `77555d0defa1574c7e4d22e63130a42e8958766264b713b2e9f361524a221e82`. Stored in the Node C GitHub runner user's mode-0700 private staging directory; this is NOT yet the root-owned Steward database.

**Per-container retirement register created privately on Node C**. [Verified protected register](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40123394762) documents all 21 containers across 12 candidate service groups with state, image, ports and unresolved replacement dependencies. Register SHA-256: `71bac555d65ac726394ba89b89d4a1ff61e254182681799784497d8e4c068ec0`. No container has yet been approved for removal. This register is intentionally **not committed to public GitHub**.

**Steward migration checkpoint**: [read-only source/target gate](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40123069226) confirms the Node B service is `active` and `enabled`, knowledge seed and site-state are present, and the live ~0.05 MB SQLite `steward.db` passed its quick integrity check (13 schema objects). CT221 was not configured on Node B at audit time. The Node C private HA900 register staging is checksum-verified; no root-owned import utility is installed yet.

**Natural Automation API blocker**: [read-only diagnostic](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40123208524) confirms Node B port 8099 accepts connections and `/` returns HTTP 200 while `/api/status` exceeded a 5-second timeout. The repository implementation of `/api/status` runs target resolver and full HA entity inventory; this diagnostic does not establish a broken service. Use a dedicated lightweight readiness probe plus dependency inventory before moving active Natural Automation to Node C. Keep Node B service unchanged until tested Node C sidecar and rollback exist.

**Off-host full backup pending**: Read-only capacity check `.github/workflows/jns-solar-ha900-backup-capacity.yml` checks source ZFS and mounted NAS destination headroom without creating backups or mounting shares. Restore tests and backup source consistency are not yet complete, so destructive cleanup remains blocked.

## Stage gates

1. **Independent-host / Guardian recovery topology.** Live `pvecm` checks on A/B confirmed neither is in a Proxmox Corosync cluster. Retain independent hosts (no added quorum witness). Audit Guardian/Consul, licensing/locks and split-brain behavior separately; sleeping Node B must not be treated as an unplanned outage or trigger a duplicate MQTT/Zigbee/HA leader. Explicit fencing and controlled recovery are required for B wake. Do not apply `pvecm expected` or in-cluster HA migration commands.
2. **Guest identity and capacity.** Record exact running guest's node, disk type, filesystem, memory peaks, config fingerprint, onboot, device passthrough, mountpoints, bindings, IP/DNS identity, and recovery snapshot. No collisions with Node A CT212 or existing stopped VMIDs.
3. **Service continuity.** Replicate/restore Node B MQTT persistence (CT212), Zigbee2MQTT state (CT214) and automation (VM905) to conflict-free Node A targets; preserve broker hostname/client reconnection, one active Zigbee coordinator, serial bridge CT210, Lyric auth, recorder and learned state. No blanket source/target restarts. Verify HA General, HA Primary, Plant Manager, Security and camera capabilities individually. Explicitly include moving HA-Security VM906 from Node C to Node A (see mandatory section above).
4. **Node B host processes.** Move or retire `natural-automation.service`, infrastructure discovery, CT220 management, logging, time and Guardian dependencies before physical shutdown. Determine what remains intentionally sleeping and disable onboot where duplicated service starts could split brain.
5. **Always-on Node C Steward and management.** Keep the existing Node C GitHub runner, Steward, DNS importer, management bridge and required CT249/130/117 in service; confirm the actual Steward service path. Transfer only HA-Security VM906 to Node A. Node C is NOT a Proxmox quorum witness. This is intentionally a two-powered-node operating mode, not an interim state.
6. **NAS discipline.** Identify XigmaNAS high-draw hardware vs WD My Cloud NFS shares. XigmaNAS's known Wake-on-LAN limitations mean clean remote shutdown and the specifically approved Tuya/BIOS power-recovery mechanism, not unguarded power removal. Keep socket energised through OS shutdown and verify device is off before controlled socket restart. Never cycle the protected router plug. Backup targets must show mounted/reachable before a backup; verify success and data integrity, release open handles, unmount and only then shut NAS down. Keep authoritative DNS data reachable when NAS is off.
7. **System boot order and fallback.** Start essential DNS/NTP → MQTT → Zigbee → HA-General → HA-Primary / Plant Manager / HA-Security as dependencies require. Automatic 'onboot' should be enabled only for verified active production guests. A sleeping Node B may wake on explicit service recovery or maintenance, but must not start duplicate HA brokers/bridges by itself. Test physical wake path and independent out-of-band recovery before any power-off.
8. **Solar automation later.** First commission a manual Economy/Normal/Recovery switch with dry-run gate results. After verifying inverter PV/battery SOC entities, add hysteresis and minimum on/off dwell times, forecasts, battery reserve and critical load exemptions. Never cut safety-critical systems solely on low PV readings.

## Cutover acceptance

- Source and destination backups plus restoration test complete.
- CPU, RAM, ZFS ARC, disk I/O and datastore free-space headroom pass load tests.
- Sensor readings and HA automations, MQTT retained messages, Zigbee, DNS/DHCP, security/doorbell, history, dashboards and camera views remain functional.
- No active VM/CT disks or mount dependencies on sleeping hosts/NAS.
- No duplicate broker/controller, quorum loss, failed backup schedule, stale VM startup or WOL-only dead-end.
- Explicit, tested rollback to the original Node B guest and service locations.
- Only then cleanly stop guest services, **shutdown** Node B and verify reachable recovery/wake.

## Prohibited operations until gates clear

No host shutdown, hard Tuya power cut, Proxmox cluster conversion, blind ID migration, removal of HA900 source data before a verified independent recovery copy, automatic failover promotion, or NAS shared-storage unmount while in use.

