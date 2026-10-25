# JNS Solar Economy — guarded consolidation runbook

Status: **AUDIT / NOT APPROVED FOR CUTOVER**. No VM, CT, NAS, host, quorum, or automation has been modified or powered down by this workstream.

## HA900 retirement action — 25 October 2026

- VM900 `homeassistant-recovery` on Node A is **stopped** with `onboot=0`, independently verified in [live archival preflight](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40193967811). The Proxmox shutdown UI also showed successful Stop.
- Operator has expressly authorised retaining a complete cold-recovery archive on Node C NFS and **removing VM900 and its local disks from Node A** afterward. Do **not** start another Home Assistant controller. Node C VM909 is a separate pre-existing stopped reference and is **not** part of the authorised deletion.
- Node C `nfs-ct` is mounted with ~1.4 TiB free. Node A original VM900 has two ZFS volumes: 1 MiB EFI and 256 GiB system image; the source VM was not deleted during the audit.
- [Native VMA backup and verify workflow](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40194270323) exports a stopped-guest `vzdump` to Node C NFS via the trusted runner, retaining its full Proxmox configuration. It then verifies transferred file size/SHA-256 and performs a full `zstd`/Proxmox `vma verify` integrity check. Archive manifest and files are private, mode 0600/0700.
- `jns-solar-ha900-verified-removal.yml` is an independent source cleanup workflow triggered **only on successful archive completion**. It re-hashes the NFS archive/config, checks original guest name/ID/onboot and stopped state, then targets **only Node A VM900**, preserving Node C VM909. It removes the temporary Node A backup stage after successful deletion.
- **Never declare HA900 VM/disk cleanup complete based on the backup launch.** Confirm the removal workflow succeeds and Proxmox no longer defines VM900, its ZFS rootfs volumes are absent, and NFS manifest & archive survive. If archive or verification fails, leave VM900 stopped and its source volumes intact.

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

## HA-Security moved as an offline VM image — 25 October 20:53 UTC

**Verified current state (not yet live cutover):**

- [Full offline Proxmox restore completed successfully via GitHub runner](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40232356069) after resuming a previously interrupted `qmrestore` using the original `vzdump-qemu-906-...` archive filename. Node A VM906 has a complete disk and VM config; temporary restore archive/dataset were removed. Node C original VM906 was not modified.
- [Independent two-host audit](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40232866432) confirms: **Node A VM906 is STOPPED, onboot=0, named ha-security, 2 vCPU / 2048 MiB, scsi0 on vmdata, disk exists, net0 exists.** Node C still has a running QEMU process for ID906. Both must **never run simultaneously**.
- NFS retains a protected `vzdump-qemu-906` source snapshot (~2,870,468,195 bytes, generated 2026-10-25 15:24 UTC). This backup was taken with source running; a final quiesced snapshot is recommended to capture any more recent security state before production handover.
- `ha-security.home.arpa:8123` was not reachable from the Node C runner at audit time, so no live HA API/security service acceptance has passed.
- **Node C privileged stop gate:** `github-runner` only has `sudo` permission for already allowlisted JNS gateway jobs, which do not include Proxmox VM shutdown or VM906 migration. Root SSH back to Node C is unavailable. Therefore GitHub connector *can* restore/prepare and start Node A via its established root SSH, **but cannot stop Node C source or change its onboot**. Do not weaken the gateway or use a blanket privilege grant.
- To finish: an authorised Node C Proxmox operator must set original VM906 `Start at boot: No`, gracefully stop it, verify it is stopped (and take final stopped-source backup if state changed), then trigger a gated GitHub Node A promotion workflow that checks the source process is absent and the restored target identity/disk is valid before starting Node A. Verify DNS, alarm/ESPHome/KC868, tamper and doorbell behaviour. Keep the original on Node C stopped as rollback.
- **No claim of completed HA-Security migration is authorised before the two-host startup exclusivity and functional tests succeed.**

## HA-Security one-time root cutover handoff — 25 October 19:57 UK

The user has explicitly authorised immediate HA-Security VM906 relocation from Node C to Node A. **Do not claim completion until the on-host cutover runs and both VM states are verified.**

- The installed Node C `github-runner` has only named root sudo grants (gateway executor and network monitor), **not** `qm`/`vzdump`; SSH `root@nodec` from Node A, Node B and localhost is unavailable. This was checked in [live authorised access audit](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40227771925). Do not bypass the allowlist.
- A single cutover implementation was committed as `gateway/solar/move_vm906_nodec_to_nodea_one_time_20261025.py` and [successfully syntax-checked and staged onto Node C](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40228454934).
- The staged file is `/home/github-runner/.local/share/jns-solar/ha-security-906/move_vm906.py`, SHA-256 `4951ab5f0c24a83069106c4c6f148ff0f99a10c4a852bdb90d1621294c743e29`. Privileged execution has **not** occurred; this is an explicit root-console handoff.
- A Node C root shell can copy the staged script to a root-owned immutable-in-use copy, check the above digest and execute it. It validates ID/name/disks/passthrough, Node A RAM/storage/network and NFS mount, disables source autostart, gracefully shuts down original VM906, performs a full **stopped-source** `vzdump` to NFS, verifies SHA and zstd integrity, streams to Node A over the existing GitHub runner's pinned SSH identity, restores as **offline** VM906 on Node A, confirms preserved NIC MAC and Proxmox identity, starts the target only after old source is off, and tests `ha-security.home.arpa:8123`. Success enables Node A onboot=1 and retains Node C VM906 stopped with onboot=0.
- A cutover error tries to stop the target before restoring the source, never deletes original VM906 on Node C, and never changes any VM ID other than 906. If either VM cannot be proven stopped, it fails closed rather than starting two controllers.
- **Endpoint reachability is not a full security/alarm/tamper function test.** Check actual alarm and ESPHome/KC868 doorbell functions after the move before removing the old source.
- Separate HA900 NFS archival run 40194270323 was cancelled; no assumption that VM900 disks are deleted or archive completed.

## HA-Security VM906 relocation checkpoint — 25 October 2026

**Current state: NOT MIGRATED. Source VM906 remains live on Node C.** [Current source/destination audit](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40199089457) confirms VM906 definition and disk present on Node C; VM906 does not exist on Node A. Node A has 3795 MiB available RAM, 2687 MiB swap in use and ~778 GiB free vmdata. Node C NFS backup share has ~1382 GiB free.

The HA900 archive run 40194270323 ended cancelled; Node A VM900 is stopped and onboot=0, its disk removal is unverified. Do not confuse an archived VM900 copy with a freed or deleted VM900 source.

**Privileged source access gate:** Node C GitHub runner cannot directly run `qm`/ `vzdump` as root. The [existing allowlist inspection](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40199885120) found the gateway's already-installed handlers cover HA package/network identity, Tuya, Veyra and DNS tasks, NOT VM906 relocation. Do not escalate the runner or bypass its trust boundary.

Prepared, syntax-tested, narrowly scoped source scripts in `gateway/solar/`:
- `ha_security_906_source_prebackup_nodec_v1.sh`: run by approved root on Node C only; checks source identity, NFS headroom and passthrough; creates a private current Proxmox `vzdump` snapshot of VM906 on NFS, full zstd test and SHA-256 manifest. Does not stop source.
- `ha_security_906_stage_nodea_from_nfs_v1.py`: run from approved Node C root after the source backup; through the runner's existing SSH identity streams the pinned archive directly to root-only storage on Node A, verifies SHA-256, runs `qmrestore` to **stopped, onboot=0 VM906** on `vmdata`. Source remains running until a separately approved, controlled final cutover.
- Both files were syntax-validated by [JNS Solar VM906 Migration Script Validation](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40200179593). **Syntax checks do not constitute VM migration success.**

**Final live cutover is NOT authorised to happen blindly:** verify the offline restore and HA-Security target configuration, security/tamper integrations, existing alarm state, source/target MAC/DNS ownership, available Node A RAM under load and rollback. Stop Node C VM906 and set onboot=0 before bringing up the Node A copy; never run them concurrently. Preserve source VM906 stopped for rollback until HA-Security endpoint and actual alarm/doorbell functionality are verified. On successful cutover Node C remains the always-on Steward host.

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

**Off-host full backup pending**: [Read-only capacity check](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40123502737) confirms approximately **800 GiB available on Node A `vmdata`**, suitable for a controlled local staging backup, and **88.1 GiB free on Node B's mounted `NAS` CIFS**. Neither node has `WD-BACKUP` mounted and Node A's `NAS` mount is inactive. The 256 GB provisioned/44.4 GB ZFS-accounted HA900 source is **not a verified compressed backup size**. Measure/validate actual compressed output and NAS free-space reserve before any off-host copy; ensure the archive can be restored when NAS is sleeping (on-demand wake permitted). No full backup, transfer or restore test has yet occurred. Destructive cleanup remains blocked.

## 2026-10-24 service migration execution checkpoint

### Steward/Natural Automation Node B → Node C

- [Read-only staging preflight](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40124227906): Node B code, repair modules and current site knowledge all found; total source dataset is small, private Node C runner home writable; existing Node C sudo is only via preapproved JNS gateway paths, NOT general root installation.
- [Private source copy](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40124424320): 26 files, 112819-byte protected archive staged on Node C; SHA-256 `517a78dc7ccfc3547181626b59c67fbddbd8a9155bf37d91d203a5c9042ec3e4`; SQLite source copied via consistent read-only backup. Node B service remains active.
- [Isolated Node C shadow smoke](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40125137370): read-only temp service replied HTTP 200 on loopback with `NA_ENABLE_APPLY=0`; copied 13-object database passed `PRAGMA quick_check`; shadow process stopped and temporary data cleared.
- Prepared guarded one-time installer: `gateway/solar/install_nodec_steward_shadow_root_v1.sh`. **Not executed**. It must be installed through an authorised, reviewed Node C root workflow; the current unprivileged GitHub runner must not bypass its JNS sudo allowlist. Installation would set up a disabled-autostart, loopback-only, apply-disabled shadow unit and import HA900's checksum-pinned private records into protected root Steward storage.
- Final promotion is still pending: privileged installation, test HA-General read-only Proxmox transport from Node C, fresh Node B SQLite/knowledge delta export, service equivalence validation, tightly staged DNS/entrypoint change, then explicit Node B service deactivation with rollback. Do not copy Node B's apply-enabled unit verbatim.

### MQTT and Zigbee2MQTT Node B → Node A

- [Destination preflight](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40124709863): Node A has free CT230 and CT231 targets; Node B CT212 is MQTT and CT214 is Zigbee2MQTT (despite both container names containing `mqtt`); both use independent ZFS rootfs and have **no external CT bind mounts**. Node A's CT212 is occupied by unrelated logging.
- First Proxmox `vzdump --mode snapshot` for MQTT **failed**; private diagnostic found a guest tar read-permission/user-namespace failure. The source was not stopped. Do not retry an unchanged permission-failing backup as though it succeeded.
- [Application-aware source audit](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40125399295) found Mosquitto config at `/etc/mosquitto`, persistence at `/var/lib/mosquitto`, and Zigbee2MQTT data under `/opt/zigbee2mqtt/data` plus its installation and systemd definition.
- [Verified, root-only application copies on Node A](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40125637374): MQTT CT212 tar.gz 92794 bytes, SHA-256 `f5ae7662427133df4f6e175bf0169bbeac170cdf89750274f5bcc4fe0bbf126f`; Zigbee2MQTT CT214 tar.gz 63404741 bytes, SHA-256 `a40904dfa4405bb55849f4814dfd729dfb9d9c0e66afe7d5968a802313bf6ff9`. Archives are private to host root, not committed to GitHub. **No destination CT is registered or started.**
- [Full ZFS root filesystem replication completed](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40125917728): CT212's dataset copied to a private Node A MQTT staging dataset (~384061440 referenced bytes); CT214's dataset copied to a private Zigbee staging dataset (~732434432 referenced bytes). **Source and destination snapshot GUIDs matched**, `canmount=off`, mountpoint=none, mounted=no; CT230 and CT231 Proxmox definitions remained absent. Source MQTT and Zigbee2MQTT continue running on Node B. This is preliminary crash-consistent storage staging, NOT a final clean application cutover. The source ZFS snapshots must be tracked for eventual release after final migration.
- Application copies and live ZFS snapshots are crash-consistent staging points, NOT final clean cutover state. At cutover, quiesce broker/adapter deliberately; take a final consistent checkpoint; verify broker passwords, persistence/retained topics and all consumers, one Zigbee coordinator, bridge CT210 connectivity, DNS alias/leases and HA reconnects. Keep old Node B CTs disabled on boot before promoting new CT230/CT231. Verify rollback in reverse order.

### Operational blockers

- Node A RAM remains ~8 GB with significant swap already used; moving HA-General, Plant Manager, HA-Security and MQTT/Zigbee production there requires retiring/stopping HA900 support only after dependencies and measured RAM headroom pass. Likely evaluate a 16 GB or larger physical RAM upgrade.
- Node C's Steward permanent root installation requires its existing authorised deployment gate or a reviewed one-time root command; no broad sudo grant for `github-runner`.
- HA900 full recoverable backup and slim cold reference on Node C still pending storage validation and verified restore; no old service or images deleted yet.
- Node B, NAS and HA-Security remain in production locations until explicit tests and rollback criteria pass. Node C stays always-on by design.
**Next VM migration gate:** `gateway/solar/vm903_905_zfs_readonly_v1.py` audits Node B's running HA-General VM905 and Plant Manager VM903 disks and Node A's stopped duplicate IDs. If VM disk layouts permit, stage complete ZFS source snapshots under **separate unmounted datasets**, without overwriting old Node A VMID 903/905 definitions or starting duplicate HAs. Capacity and full service dependency gates still block cutover.

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

