# HA / MQTT continuity — safe implementation and acceptance plan

Status: **Preflight only** (19 October 2026). No deployment authorized by this branch.

## Requirements

- HA-General (currently VM905) continues control during single-host maintenance or failure.
- MQTT (currently CT212) continues serving Zigbee2MQTT (currently CT214).
- A standby is *current*, not just a bootable stale snapshot.
- Planned updates drain active services to another physical host **before** restart; rejoining host becomes standby, not automatic primary.
- Unplanned failover requires an independent, quorum-backed decision and proof that prior owner is fenced. Never run duplicate HA automation writers or two uncoordinated MQTT primaries.
- Hostnames/service DNS, not fixed VM/IoT IP addresses. Flag legacy IPs.
- Do not alter Zigbee coordinator CT210 ownership until a separate physical-radio recovery scheme has been tested.
- No new VM disks on Node C local-lvm until 99.65%-used thin pool is addressed.

## Evidence from Node C audit (user supplied)

- pvecm: no /etc/pve/corosync.conf (Node C unclustered).
- pvesr: no jobs listed on Node C.
- nodea/nodeb names failed resolution; nodec resolved to legacy 10.10.10.236.
- ha-general.home.arpa resolved; mqtt.home.arpa did not.
- Node C local-lvm at 99.65% used, NFS share at 47.02%.
- No evidence yet of native Proxmox HA, replicated disks, broker synchronization, shared-storage suitability, or functioning automatic promotion.

## Stage 0: read-only inventory

Run `tools/ha_mqtt_ha_preflight.sh` as root from Node C. Collect results privately. Resolve DNS naming first, then audit Nodes A/B. Map actual workload placement, source disk types, storage available by node, VM config, networking, DNS authority, broker persistence, MQTT credentials, client session requirements, and Zigbee adapter routing. Treat missing data as a blocker; do not invent hostnames, addresses, IDs or capacity.

## Stage 1: infrastructure choice

Assess suitability for a 3-node Proxmox cluster only **after** backups, independent-node configuration compatibility, storage layout, guest VMID collisions, and node-name resolution are verified. Joining nonempty independent nodes to a cluster is not an in-place safe conversion: a migration plan is required. Prefer built-in HA manager/fencing and maintenance behavior where appropriate; no direct production cluster joins during discovery.

## Stage 2: MQTT continuity first

Determine whether Mosquitto must be retained and whether its exact reliability requirements can be met with a supported broker design. Plain Mosquitto bridging replicates selected topics, **not** every persistent session, subscription, queued QoS message or shared HA state. An active/passive setup needs tested durable persistence replication + one-active-writer enforcement, or replace it with a broker solution offering documented clustered session/state semantics. Keep stable DNS service name, conservative TTL and client reconnect/backoff; DNS caching means this is not instantaneous. Demonstrate retained message, active persistent session, clean/unclean recovery, QoS 1/2 behavior, Zigbee2MQTT reconnection and state reconciliation.

## Stage 3: Home Assistant continuity

HA Core is not a general-purpose multi-master replicated control system. Running a duplicate application against the same writable configuration/SQLite database is unsafe. Design single-writer active/passive with controlled, application-consistent state transfer and independent health verification. Standby must not execute automations, own integrations with side effects, or take the Zigbee controller. On promotion validate the config and reconcile actual physical device state. Inventory integrations that cannot fail over transparently.

## Stage 4: maintenance orchestration

1. Request planned maintenance; set per-workload lock.
2. Check quorum, fence availability, standby application integrity, replication lag, free capacity, and MQTT/HA client health.
3. Transfer ownership (including MQTT service endpoint); wait for actual reconnect/control validation.
4. Allow only the drained host to reboot/apply updates. Abort maintenance if any check fails.
5. Rejoining host starts isolated, resyncs, and rejoins as standby; no automatic failback. Alert if redundancy degraded.
6. On unplanned failure: prefer safety over availability when ownership cannot be proven; isolate and alert rather than risk split-brain.

## Test gates

- Baseline: on/off and dimmable test lights, Zigbee2MQTT events, HA automation state, MQTT retained message and persistent client probes.
- Planned reboot: automation continues, broker reconnects, no concurrent command writers, no repeated flip-flop.
- Unplanned host isolation: quorum + fencing verified; record real interruption and message loss.
- Recovery: old primary rejoins passively; reconcile device state; monitor 24h for oscillation.
- Failure cases: DNS outage, broker stalled-but-running, HA unhealthy-but-running, insufficient sync, disk full, no quorum, update failure, coordinator CT210 outage.
- Record measured RTO, RPO and pass/fail against requirements; do not claim zero RPO without a synchronous solution and test evidence.

## Change control

This branch contains **only** a read-only audit script and a design plan. No automatic deployment workflow, node reboot, database copy, IP hardcoding, cluster initialization or MQTT switching is permitted from this branch. Production changes require a separate reviewed and explicitly approved rollout.
