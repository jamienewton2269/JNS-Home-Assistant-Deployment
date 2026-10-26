# JNS Proxmox Cluster Conversion — Evacuation and Guest-ID Register

**Baseline:** 26 October 2026. **Status:** PREPARATION ONLY — not authorised as a destructive, in-place cluster join.  
**Operator goal:** Production on Node A, Steward/management on always-on Node C, Node B normally off but available for scheduled ZFS catch-up replication. Preserve the DNS-name-first network policy and existing rollback/recovery copies.

## Verified live facts

- [Read-only Proxmox inventory](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40306743853): Nodes A/B/C are **independent standalone PVE hosts**, not joined. Eight A↔B guest-ID conflicts: `210, 212, 213, 214, 900, 902, 903, 905`; VM906 exists on A and C.
- [HA-Security live frontend test](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40324369943): VM906 **running on Node A**, HA frontend HTTP **200 on port 80** (normal newer-HAOS listener); port 8123 is **not** configured/listening. HAOS Observer healthy on 4357. Old Node C VM906 is **stopped/onboot=0**, confirmed by operator's Node C Proxmox shell. Preserve original stopped VM906 and NFS backup until end-to-end alarm, doorbell, tamper and ESPHome checks.
- Node A's available RAM was just **1,887 MiB** on the most recent cluster audit. Adding Node B's running HA-General + Plant Manager + MQTT/Zigbee without reclaiming capacity or upgrading RAM is unsafe.
- Source guest-purpose registers: [Node A](https://github.com/jamienewton2269/JNS-Steward-Diagnostics/tree/main/inbox/nodea), [Node B](https://github.com/jamienewton2269/JNS-Steward-Diagnostics/tree/main/inbox/nodeb), [Node C](https://github.com/jamienewton2269/JNS-Steward-Diagnostics/tree/main/inbox/nodec). Baseline records collected 26 October.
- Proxmox's official guide explicitly says **joining a node with existing guests is not supported**; the joining host's `/etc/pve` configuration is overwritten, including storage definitions. Backup/evacuate guests before joining. See [Proxmox VE Administration Guide, Adding Nodes to the Cluster](https://pve.proxmox.com/pve-docs/pve-admin-guide.pdf).

## Guest collision disposition — no automatic deletion

| ID | Node A inventory | Node B inventory | Proposed resolution before Node B joins |
| --- | --- | --- | --- |
| 210 | CT Zigbee TCP bridge **RUNNING**, USB/network bridge role | CT Zigbee gateway stopped | Preserve A CT210. Verify and archive B clone before removing its configuration. |
| 212 | CT JNS logger/indexer **RUNNING** | CT Mosquitto **RUNNING** | Preserve A CT212. B MQTT has already been staged as Node A **CT230 candidate** with app backup and unmounted ZFS copy; final service-stopped sync, start CT230, test all clients, fence B source, then evacuate. |
| 213 | CT JNS logger standby **STOPPED** | CT JNS logger-b **RUNNING** | Investigate whether standby duplication is still required. Archive both. Either move B role to collision-free CT233 or retire duplicate only after logging continuity is verified. |
| 214 | **VM** house audio A **RUNNING** | **CT** Zigbee2MQTT **RUNNING** | Preserve VM214. B Zigbee2MQTT already staged as Node A **CT231 candidate**. One coordinator only: stop B source before CT231 start; verify serial CT210, MQTT CT230, renamed devices and retained state. |
| 900 | VM HA900 legacy **STOPPED**, disks retained pending verified archive | VM HA900 clone **STOPPED** | Complete verified NFS restore archive and remove duplicate VM definitions only after integrity/restore tests. Archive B clone separately if newer/different. |
| 902 | VM HA-Primary **RUNNING** | VM HA-Primary stale **STOPPED** | Preserve A VM902; archive and retire stopped B copy after parity review. |
| 903 | VM Plant Manager stale **STOPPED** | VM Plant Manager **RUNNING** | Back up A stale VM903 and B production VM903 separately. Reuse canonical **VM903** on A only after removing its verified stale definition, confirming A RAM headroom and migrating B active state. Never start both copies. |
| 905 | VM HA-General stale **STOPPED** | VM HA-General **RUNNING** | Back up A stale VM905 and B live VM905. Reuse canonical **VM905** on A only after source integrity/rollback, removing stale destination definition, and verifying automations/MQTT/Lyric/cameras and Core availability. |

**Other non-collision Node B guests that must be inventoried and backed up:** VM219 house-audio-b USB-dependent, VM904 test source, CT115 Guardian, CT211 inactive syslog, CT216 NTP, CT220 management, CT248 Sheriff DNS, and all host services including **natural-automation**. Do not power off B while HA-General/Plant/MQTT/Zigbee or Natural Automation is active.

## Node C must be evacuated to become a joining cluster member

Node C contains currently **running** CT117 Lunar/Consul, CT130 network-monitoring stack (including MariaDB/LibreNMS), CT249 Sheriff DNS, and host-level **Steward deployment runner, management bridge, diagnostics and NFS mounts**. Stopped VM906 HA-Security rollback, VM909 HA900 historical reference, VM990/991/9906 test/golden images and CT131 also require separate protected backups and disposition.

- **Do not clear Node C's `/etc/pve`, delete its CTs, or run `pvecm add` while these exist.**
- Preserve the GitHub deployment gateway's **secrets and installed permissions without copying tokens to GitHub logs**. Build and independently validate a temporary authorised runner/control channel on Node A or an existing trusted external host before taking Node C's runner down. Node A's current 8 GiB RAM is a serious capacity blocker even for temporary management expansion.
- Keep DNS continuity through A CT247 and B CT248, with Node C CT249 returning after cluster join; check clients and authoritative updates before taking C offline.
- Back up CT130 database using an **application-consistent MariaDB export** as well as container disk backup; verify a restore on an isolated guest. Record monitoring historical data, JNS signing keys and rollback policy.
- Preserve the NFS archive on an external backend independent of Node C's local filesystem. Do not cut NAS power while it holds an active recovery archive or mounted backup.
- A restored rollback copy of VM906 must never share VMID906 with the production Node A VM after clustering. Keep it as cold NFS backup or isolated unpowered VM with **new unused ID**, NIC disabled and onboot=0.
- After authorised root-level evacuation and validation, join Node C as a clean member, then restore its unique-ID CT117/130/249 and other approved tools with suitable storage and a working gateway. Node C's local thin pool was previously near capacity; reassess before restoring anything.

## Cluster creation, quorum and native replication

1. Verify NFS backups, source/destination disk identities and host `/etc/pve`+network+storage config backups. Ensure a complete rollback route for the **cluster creation on production Node A**, not just the joining hosts. Check Corosync low-latency networking, fixed cluster host identity and time synchronisation.
2. Consider Node A **RAM upgrade to at least 16 GiB**, subject to measured load and a memory reserve target. Do not move all B guests while available RAM is ~1.8 GiB.
3. Safely establish a cluster on Node A only after separate, explicit infrastructure change approval and a maintenance window.
4. Evacuate one joining host at a time. Ensure no VM/LXC definitions remain on that host, protect host services, back up pmxcfs storage definitions, join it, then restore approved guests under cluster-wide unique VMIDs. Plan to keep a third quorum voter available before leaving B powered off.
5. The long-term **A+C running / B asleep** design can maintain 2/3 votes after **all three** have joined; a B-off target cannot receive ongoing `pvesr` snapshots until it is awake. Set up bounded automatic wake/sync/check/sleep policy and explicit failover procedures.
6. Built-in `pvesr` replication must use compatible **ZFS storage IDs** on nodes holding source and replica, adequate disk headroom, tested incremental snapshots and a verified recovery/promotion procedure. Node C's extant LVM-thin system volume is not an interchangeable ZFS replication target.
7. No Proxmox cluster membership, live guest cutover, guest destruction, DNS rewrite or automatic failover is authorised by *this register* alone.

## Immediate release gates

- [x] HA-Security active Node A Core frontend verified over configured port 80.
- [x] Old HA-Security Node C VM906 stopped and autostart fenced by operator.
- [ ] Alarm manual-arm/disarm, ESPHome KC868 tamper and doorbell validated.
- [ ] Full Node B guest-by-guest verified backups and Node A memory/VMID resolution.
- [ ] Full Node C guest + host service backups, protected deployment runner relocation and isolated CT130 restore.
- [ ] Production Node A cluster snapshot/backout and Corosync link review.
- [ ] Node C/Node B independently evacuated before either joins.
- [ ] Three-member quorum healthy before B is permitted to sleep.
