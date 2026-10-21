# JNS Steward — Cross-host HA replication pilot v0.2

## Tested facts (21 October 2026 host reports)
- Node A running VM902, stopped VM905; Node B running VM905, stopped VM902.
- Both `vmdata` pools are healthy ZFS; large available capacity.
- Both are standalone Proxmox, `pvesr` empty; no native cluster replication.
- Node A and B peer short names fail lookup. HA-Primary and MQTT service names also have inconsistent resolution.
- Node A CT212 is *syslog*, Node B CT212 is *MQTT*. Existing syslog, time/NTP, DNS/DHCP pairs are native and **out of Steward control**.
- HA-Security still on temporary Node C; relocate later.
- Node A recovery VG reports missing PVs; do not use it.
- Existing stopped HA VMs are historical copies, **not proven replicas**. Neither should be overwritten.

## Implementation stages
0. DNS/SSH trust: resolve peer FQDNs using existing native DNS services; configure dedicated least-privilege replication identity with verified host keys. Do not alter the native DNS/DHCP pair as part of this pilot.
1. Run read-only `steward_ab_transport_preflight.sh nodea` on A and `... nodeb` on B. No changes.
2. Select *new isolated dataset paths* for stream-received ZFS volumes on each target, not the live or stopped VM paths; capacity and snapshot retention reviewed.
3. Obtain application-consistent HA checkpoint strategy (not a naive running SQLite file copy). Test backup restore in isolated network. Pin exact VM settings and secure credentials separately.
4. Create opt-in source snapshot and ZFS `send -i` pipeline with atomic receives, host identity, checksums, throttling, failure journal, bounded snapshot retention, and transfer acknowledgement. Distinct VM IDs required if a restored replica is registered locally.
5. Validate recovery as isolated guest, no normal HA outputs or duplicate MAC/IP; inventory device ownership and state age.
6. Add systemd scheduled sync with freshness alerts. Observe-only until integrity confirmed.
7. Only then develop Steward safety fencing, demotion, promotion, no automatic failback, repair/rebuild. MQTT/Zigbee application-aware adapters separate.
8. Relocate HA-Security from Node C to A/B using supervised cutover once pair validated.

## Stop conditions
DNS failure, unknown disk provenance, source/standby identity collision, missing fencing, bad app checkpoint, broken ZFS pool, missing ssh trust, stale state, insufficient storage, HA or MQTT configuration uncertainty. Stop without a write.

## Configuration boundary
Steward MUST NOT manage, reconfigure, promote or restart native dual syslog, time or DNS/DHCP services. Document dependencies only.

## Status
Only read-only transport preflight committed; no replication job exists and no production change was applied.
