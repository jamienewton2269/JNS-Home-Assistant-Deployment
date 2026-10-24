# JNS Total Configuration Register — Native Redundant Infrastructure

Updated: 2026-10-21. Scope: Node A and Node B production infrastructure. Status: documented from user-confirmed architecture and 2026-10-21 host inventories; operational redundancy is user-confirmed, not independently failure-tested in this document.

## Native service pairs — record only, no Steward control

| Service | Node A | Node B | Native redundancy | Steward scope |
|---|---|---|---|---|
| Syslog | CT212 `jns-log-a` | CT213 `jns-log-b` | Existing dual logging services | **Inventory/documentation only; do not manage, restart, reconfigure or promote** |
| Time service | CT215 `jns-time-a` | CT216 `jns-time-b` | Existing paired time services | **Inventory/documentation only; do not manage, restart or promote** |
| DNS/DHCP | CT247 `jns-dns-nodea` | CT248 `jns-dns-nodeb` | Existing primary/secondary native DNS/DHCP design | **Inventory/documentation only; do not synchronize, restart, reconfigure or promote** |

### Important identity collision
CT212 on Node A is **syslog** `jns-log-a`, while CT212 on Node B is **MQTT** `mqtt-infra-a`. VMIDs and CTIDs are local to independently managed Proxmox nodes. Never assume that matching IDs denote matching services, and never use CT212 on Node A as an MQTT replication destination.

### Configuration governance
- Native redundancy precedes custom orchestration.
- Steward does not take operational authority over the three service pairs above.
- These services remain listed in the global dependency/topology inventory so HA and MQTT deployments do not collide with them.
- Record hostname, guest ID and host placement; avoid hardcoded moving guest IP addresses. Name resolution and client failover details are not changed by this document.
- Detailed service configs, runtime health, and failover behavior were not independently tested here and are not fabricated.
- Distinguish historical design from current host inventory when changes occur. Record migrations by updating this register.

### Steward-managed workloads (separate programme)
HA-Primary, HA-General, HA-Security, MQTT, Zigbee2MQTT and Bluetooth are being evaluated for Steward-coordinated redundancy. Their architecture does **not** supersede the native redundancy services listed above.

### Change status
Documentation only. No guest, host, timer, service, DNS, or existing configuration was modified.
