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
