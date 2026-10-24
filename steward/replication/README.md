# Steward replication — Stage 0 acceptance gates

Run `bash steward_replication_preflight.sh` independently on nodea and nodeb. Script is read-only: no snapshots, creates, migrations, backups, network changes or restarts.

## Why this is needed
Latest host reports show VM902 **running on A / stopped on B**, VM905 **running on B / stopped on A**. Those stopped VMs must not be overwritten or powered on without verifying their disk contents and intended purpose. VM906 currently runs on temporary Node C and does not yet exist as an accepted A/B production pair. Both hosts reported no usable Corosync cluster state, so native pvesr is not currently configured as cross-host replication.

## Acceptance checklist
- [ ] Confirm exact source/standby VM disk IDs, paths, firmware, attached storage and snapshots.
- [ ] Establish whether existing stopped copies are historical backups or replicas, and preserve/archive safely.
- [ ] Confirm pool topology, supported snapshot/send/receive, capacity and target free space.
- [ ] Decide ZFS incremental replication versus application-consistent backup/restore; do not copy live HA database file directly.
- [ ] Verify DNS and SSH trust over stable hostnames and service naming; do not hardcode VM/IoT service IPs.
- [ ] Record signed, append-only generation marker, monotonic owner epochs and last completed consistent checkpoint.
- [ ] First pilot is *isolated replication*, without onboot or automations enabled on standby.
- [ ] Keep Guardian/Lunar in existing authority roles until Steward fencing/ownership controls are validated.
- [ ] Validate schedule, checksums, rollback, snapshot pruning, source/storage failure, duplicate writer protection and reconstruction.
- [ ] MQTT requires application-specific session-state correctness; do not treat Mosquitto bridge as complete replication.
- [ ] Stage HA-Security migration from Node C only after A/B success and safe cutover plan.

No production changes authorized by this documentation.
