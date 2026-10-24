# JNS Solar Economy — guarded consolidation runbook

Status: **AUDIT / NOT APPROVED FOR CUTOVER**. No VM, CT, NAS, host, quorum, or automation has been modified or powered down by this workstream.

## Goal

Run production Home Assistant, control, DNS, MQTT, Zigbee, security, and monitoring on **Node A** where capacity and dependency checks allow. Keep Node B powered down until standby/recovery or a planned backup/maintenance operation needs it. Power down high-draw NAS only after it is cleanly quiesced and there are no active mounts, recordings, backups, or authoritative DNS dependencies.

Retain DNS-first addressing and the existing GitHub Node C trusted inspection/deployment path until an equivalent, tested runner has been relocated. Preserve VM903 Plant Manager's configuration, VM905 HA-General automations, VM902 lightweight Primary, VM906 HA-Security, camera ownership on VM905, and all history/authentication.

## Live preflight — 2026-10-24

Read-only workflow: `.github/workflows/jns-solar-economy-readonly-audit.yml`
First successful audit run: https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40110302861

**Node A:** 6 logical CPUs; ~8 GB RAM; ZFS vmdata ~828 GB available. Running VM900 (4 GB) and VM902 (2 GB), VM214 house-audio (USB), CT116 Guardian, CT118 maintenance, CT210 Zigbee bridge, CT212 **jns-log-a**, CT215 NTP, CT247 Sheriff DNS. VM903/VM905 *stopped copies* also exist locally. VM902 onboot=0; VM900 onboot=1.

**Node B:** 4 logical CPUs; ~8 GB RAM; ZFS vmdata ~360 GB available. Running VM903 Plant Manager (2 GB), VM905 HA-General (1 GB configured in observed hypervisor inventory, not a verified safe production minimum), VM219 house-audio USB, CT115 Guardian, CT212 **mqtt-infra-a**, CT213 logger, CT214 Zigbee2MQTT, CT216 time, CT220 management, CT248 Sheriff DNS, and a host-level `natural-automation.service`.

**Node C:** ~8 GB RAM with ~4.2 GB available and ~2.1 GB swap in use; guest configuration IDs include VM906/909/990/991/9906 and CT117/130/131/249, but some live states are still unverified. Node C hosts the current GitHub self-hosted runner, DNS reservation importer, JNS management bridge, and running CT117, CT130, CT249, among other workloads. VM906 HA-Security is reported on Node C by historical audits; confirm live state before any shutdown. Node C remote root SSH was not available via the current runner; separate local unprivileged audit is in progress.

**Storage:** Node A `vmdata` is local ZFS, not a magical shared disk with Node B's separately named `vmdata`. Node A's `NAS` CIFS storage was inactive; Node B's `NAS` CIFS was active. Both `WD-BACKUP` NFS backends were inactive **while enabled backup jobs still referenced them**. Both hosts had DNS-related NFS mounts. Confirm which physical NAS provides each share and whether DNS requires it continuously.

**Critical collision:** CT212 is DIFFERENT ON EACH NODE: Node A logs vs Node B MQTT. VM900/902/903/905 are also defined independently on both hosts (some copies stopped). **Do not invoke a bare `pct migrate 212`, `qm migrate 905`, or start stopped duplicate copies.** First prove whether hosts are in one Proxmox cluster, verify each guest's current source disk/config/checkpoints, then use collision-free IDs / supported migration or backup+restore. Do not copy stale images over live instances.

**Live cluster check:** Node A and Node B each report NO /etc/pve/corosync.conf and no configured Proxmox cluster. Local duplicate VMIDs are real and therefore require cross-host remapping; they are not in-cluster guest IDs. Do not try a standard same-cluster qm/pct migration. Solar mode will retain independent Proxmox hosts and the requested two-node safety policy, not add a quorum witness. Node A had ~1542 MB available and ~3894 MB swap in use; Node B ~1976 MB available and ~1871 MB swap in use.\n\n**RAM blocker:** Node A cannot safely run all existing HAs plus unchanged VM900 at current physical RAM. Reserve RAM for the PVE host, ZFS ARC and essential CTs. Consider retiring VM900 only after feature parity is tested, leaving it as an offline fallback, or increase Node A RAM. RAM headroom must be **measured**, not inferred from assigned vCPU count.

## Stage gates

1. **Independent-host / Guardian recovery topology.** Live `pvecm` checks on A/B confirmed neither is in a Proxmox Corosync cluster. Retain independent hosts (no added quorum witness). Audit Guardian/Consul, licensing/locks and split-brain behavior separately; sleeping Node B must not be treated as an unplanned outage or trigger a duplicate MQTT/Zigbee/HA leader. Explicit fencing and controlled recovery are required for B wake. Do not apply `pvecm expected` or in-cluster HA migration commands.
2. **Guest identity and capacity.** Record exact running guest's node, disk type, filesystem, memory peaks, config fingerprint, onboot, device passthrough, mountpoints, bindings, IP/DNS identity, and recovery snapshot. No collisions with Node A CT212 or existing stopped VMIDs.
3. **Service continuity.** Replicate/restore Node B MQTT persistence (CT212), Zigbee2MQTT state (CT214) and automation (VM905) to conflict-free Node A targets; preserve broker hostname/client reconnection, one active Zigbee coordinator, serial bridge CT210, Lyric auth, recorder and learned state. No blanket source/target restarts. Verify HA General, HA Primary, Plant Manager, Security and camera capabilities individually.
4. **Node B host processes.** Move or retire `natural-automation.service`, infrastructure discovery, CT220 management, logging, time and Guardian dependencies before physical shutdown. Determine what remains intentionally sleeping and disable onboot where duplicated service starts could split brain.
5. **Node C dependencies.** Do not power down the Node C runner, DNS reservation importer, management bridge, CT249/130/117 or HA-Security VM906 before relocating/retaining those capabilities. Re-register the GitHub runner with a fresh identity on an always-on host (never clone credentials). If Node C remains on for quorum, document this as a two-powered-node interim mode, not full single-node economy.
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

No host shutdown, hard Tuya power cut, Proxmox cluster conversion, blind ID migration, destroy/delete VM/CT, automatic failover promotion, or NAS shared-storage unmount while in use.

