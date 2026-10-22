# JNS Guest Rationalisation — Audit 2026-10-22

Source: Private JNS-Steward-Diagnostics uploads at 2026-10-22T13:13–13:14Z, `inbox/nodea/20261022T131346Z-2a815d21225e.json` and `inbox/nodeb/20261022T131442Z-f920e36e2079.json`. Counts are per-host registered guests, not unique services.

**Totals: Node A 14 (9 running, 5 stopped); Node B 15 (10 running, 5 stopped). Combined 29 registrations: 19 running and 10 stopped.**

| Host | Guest | State | Observed purpose / active service | Action |
|---|---|---|---|---|
| A | VM214 | running | house-audio-a | RETAIN pending audio role confirmation |
| A | VM900 | running | homeassistant-recovery, 4084 MiB | HIGH priority investigate dependencies |
| A | VM901 | stopped | homeassistant-standby | preserve until backup/provenance review |
| A | VM902 | running | HA-Primary | RETAIN |
| A | VM903 | stopped | ha-s1-plant | PRESERVE development/backup |
| A | VM905 | stopped | ha-s2-general | historical copy preserve until redundancy plan |
| A | CT102 | stopped | CT102 | unknown; examine metadata before archive |
| A | CT116 | running | guardian02: consul, lunar | review old control-plane dependencies; no shutdown |
| A | CT118 | running | jns-maintenance: jns-watchdog | review Steward overlap; no shutdown |
| A | CT210 | running | Zigbee gateway: jns-zigbee-bridge | RETAIN |
| A | CT212 | running | jns-log-a: rsyslog, keepalived, jns indexer/web | NATIVE service; DO NOT TOUCH |
| A | CT213 | stopped | jns-log-b old copy | identify provenance; no deletion |
| A | CT215 | running | jns-time-a: chrony | NATIVE service; DO NOT TOUCH |
| A | CT247 | running | jns-dns-nodea: jns-dns, avahi, radvd | NATIVE service; DO NOT TOUCH |
| B | VM219 | running | house-audio-b | RETAIN pending audio role confirmation |
| B | VM900 | stopped | homeassistant-recovery old copy | preserve until provenance |
| B | VM902 | stopped | HA-Primary historical copy | preserve until verified replication |
| B | VM903 | running | Plant Manager 2048 MiB, not currently in use | PROTECTED development asset; no delete/overwrite |
| B | VM904 | stopped | veyra-source01 | preserve until Veyra artifact check |
| B | VM905 | running | HA-General | RETAIN |
| B | CT115 | running | guardian01: lunar | review legacy failover dependencies |
| B | CT210 | stopped | Zigbee gateway historical copy | preserve pending provenance |
| B | CT211 | stopped | jns-syslog | compare to native log service before archive |
| B | CT212 | running | MQTT: mosquitto | RETAIN |
| B | CT213 | running | jns-log-b: rsyslog, keepalived, jns indexer/web | NATIVE service; DO NOT TOUCH |
| B | CT214 | running | zigbee2mqtt-a: zigbee2mqtt | RETAIN |
| B | CT216 | running | jns-time-b: chrony | NATIVE service; DO NOT TOUCH |
| B | CT220 | running | jns-mgmt-b; no specific app unit identified | investigate processes, listening services, dependencies |
| B | CT248 | running | jns-dns-nodeb: jns-dns, avahi, radvd | NATIVE service; DO NOT TOUCH |

## Boundaries and next assessment

- The audit establishes *names, power state, configured memory and selected active LXC services*, **not** absence of dependencies or safe-retirement proof. Full VM-internal processes were not inspected.
- Prioritise read-only HA900 integration/automation/data-ownership verification and CT220/CT118/CT115/116 responsibilities.
- VM903 Plant Manager is explicitly user-protected. Do not delete, overwrite or change its power state without verified backup and explicit approval.
- Cluster joining / replication are paused pending consolidation, ID-collision mapping and backups.
- No guest modifications performed.
