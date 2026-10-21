# JNS Steward — Unified Maintenance, Resilience and Legacy Consolidation
**Architecture and Migration Plan v0.1 — 21 October 2026**  
**Status:** Design baseline / audit required / **NOT a deployment authorization**  
**Canonical hosts:** use DNS-first service names; VMIDs below are historical until verified on live hosts.

## 1. Decision and scope
Consolidate JNS maintenance intelligence into **JNS Steward**. Steward is the single offline-first operations, diagnosis, repair and redundancy coordinator across Proxmox hosts, Home Assistant instances, MQTT brokers, Zigbee2MQTT, Zigbee coordinator bridges, Bluetooth adapters and supporting infrastructure. Do **not** create a separate universal maintenance application or second natural-language stack. Natural Automation supplies the common intent/resolution user interface; JNS Deployment supplies signed staged apply, audit and rollback.

Architectural invariants:
1. **One effective controller per exclusive device/service**; no automatic dual-writer state.
2. The surviving node can maintain and reconstruct its partner, but a healthy/ready standby is not proof of exclusive ownership.
3. Active/standby pairs exchange health, software/config digests, replication position and repair evidence on LAN plus optional out-of-band peer Wi-Fi.
4. Heartbeat loss alone never proves primary failure. Promotion requires verified demotion, credible fencing or a correctly enforced exclusive lease and authority. If safety cannot be established, isolate and alarm.
5. Rolling maintenance: hand over workloads **before** rebooting a host, test control, then update one host. Rejoining host always returns isolated and becomes standby; no automatic failback.
6. Do not rely on HA Core, MQTT, Cisco LAN switch or the same host as the only watchdog for their own failures.
7. Fail-safe behaviour for security, heating and physically hazardous actuators has precedence over continuous availability.
8. Never synchronously copy a live HA SQLite database or run two HA instances with the same writable DB.
9. No claim of zero loss without application-level measured RPO/RTO and verified durable state.
10. No node deletion until dependency and rollback gates pass.

## 2. Present estate — evidence classification
| Asset | Reported purpose/status | Consolidation disposition |
|---|---|---|
| VM902 HA-Primary / ha-primary.home.arpa | Primary-lite, maintenance dashboard; 313 unknown/unavailable on 20 Oct; duplicated legacy `ha_p0_*`/_2 entities | **Retain. Fix config/entity registry safely before using its health sensors to gate failover** |
| VM905 HA-General / ha-general.home.arpa | Running general automation, Zigbee/MQTT client | **Retain**; dedicated standby on other physical host |
| VM906 HA-Security / ha-security.home.arpa | Running on Node C | **Retain**, consent/security-specific promotion restrictions |
| CT212 MQTT / Mosquitto | Broker, historically Node B | **Retain until replacement is proven**; stateful HA redesign |
| CT214 Zigbee2MQTT | Zigbee service | **Retain**; staged peer standby |
| CT210 Zigbee serial bridge + physical coordinator | Single-radio dependency, historically Node A, legacy DNS/IP | **Retain** pending radio/adapter failover test |
| CT117 Lunar03 | Reported running on Node C | **Extract watchdog and verified repair features**; retire only after replacement soak |
| CT115, CT116 Guardian; CT117 Guardian/Lunar history | Old Guardian control-plane roles, incomplete current status | **Inventory first**; candidate decommission after authority cutover |
| VM900 HA legacy monolith, VM901 former standby | Previously caused overlapping Zigbee control; status unresolved | **Quarantine and investigate ownership**; candidate archive/remove |
| VM909 homeassistant-recovery | Stopped on Node C, 256 GB allocated; location/need unclear | **Archive/recovery candidate**, not delete until retention proof |
| CT130 JNS network monitor | Reported running on Node C | **Retain**: topology/SNMP not Steward duplication |
| CT249 DNS on Node C and Sheriff DNS pair | DNS authority and naming | **Retain**; repair peer name resolution |
| HA Plant Manager VM903 / other lean HA services | Historical migrations ambiguous | Inventory; preserve until location confirmed |
| VM990, 991, 9906 on Node C | Stopped test/golden images | Retention candidates, not assumed disposable |
| Node C thinpool | Local-LVM was 99.65% used in supplied audit | **Hard block** on new local disks until free and health verified |
| Proxmox control plane | Node C not in Corosync cluster; `nodea`, `nodeb` name lookup failed | Do **not** casually cluster existing hosts; DNS/read-only audit first |

**Evidence rules:** historical reports are hypotheses until freshly observed; no automatic cleanup based solely on this table.

## 3. Steward component boundaries

### 3.1 Steward Host Agent (small; systemd, host-local)
Install per Proxmox host and optionally per service guest where host probing cannot see application health. Responsibilities: signed inventory, dependency graph, heartbeat and link-health probes, process/service checks, physical/virtual interface probes, journald/syslog extraction, supervised repair execution, checkpoint/rollback reports. Resource-limited, offline capable, no mandatory LLM. Never embed private signing keys in replicated VM images.

### 3.2 Steward Pair Supervisor
For each service pair maintain:
- unique pair ID, roles, monotonically increasing **generation/term**, service owner, promotion epoch, peer certificates, explicit host placement;
- monotonic heartbeat sequences on wired LAN and optional independently powered direct Wi-Fi; compare paths, do not treat two links on same switch as independent;
- synchronized *validated* software manifests, configuration versions, application-aware checkpoints, state freshness and state hashes;
- independent active-service probes (actual publish/subscribe, HA control checks, Zigbee event loop, Bluetooth advertisement reception);
- diagnostics + evidence for primary unavailability; do not assert exact cause from missing packets.

### 3.3 Ownership safety / fencing adapter
Dedicated minimal component, independent of Steward's reasoning engine. API: `observe`, `request_demote`, `prove_fenced`, `acquire_owner`, `renew_owner`, `release_owner`, `deny`. Signed, replay-resistant operations; epoch records in durable storage. Use STONITH/hypervisor or independent power/network-control fencing where validated. Self-demotion is useful but insufficient if agent or host freezes. A two-node pair plus Wi-Fi improves diagnosis but cannot guarantee safe promotion after both paths fail. An optional lightweight witness or reliable fencing is still required for those cases. The witness need not run HA or join Proxmox.

### 3.4 Steward Maintenance Manager
Dependency-aware update scheduler: `request -> freeze incompatible changes -> prove standby -> synchronize -> demote -> exclusive promote -> verify service -> maintenance -> isolated rejoin -> resync -> standby -> report`. One physical host at a time. Maintenance denied if quorum/fencing, spare host capacity, state freshness, backup health or downstream control is not adequate. No dangerous remote reboot based only on a stale heartbeat.

### 3.5 Steward Repair and Reconstruction
Only versioned, allowlisted repair recipes. First try local non-invasive repair; escalate to guarded service restart; reconstruct guest on approved target only after fencing and proof the original cannot rejoin as active. Rebuild from signed install manifest + known-good app-consistent snapshot + securely recovered secrets and physical-device binding map. Do not clone Zigbee coordinator identity into two live radios. Every procedure has preconditions, dry-run, progress, verification, timeout, rollback and audit record.

### 3.6 Steward Learning
Offline-first evidence and rules; sign, validate and exchange **distilled, non-secret lessons** among siblings. Never blindly propagate machine-specific network addresses, USB bindings, entity IDs, encryption keys or broad learned remediation. Human-approved policy for impactful new repairs. Natural Automation parser becomes shared interface for inspection/proposals, not a second executor.

### 3.7 Steward dashboard
One dashboard: pair health, effective owner/epoch, last trustworthy sync, RPO/RTO from tests, service probe, maintenance lock, repairs pending, last fencing proof, dependencies and last incident. Distinguish `healthy`, `degraded`, `unknown`, `unavailable` and `unmanaged`. A panel reading “0 active problems” alongside 313 unavailable entities must not be shown as green. `ha_p0_*` are historic entity IDs, **not** a new server name.

## 4. What to port from Guardian and Lunar
**Port behaviour and validated algorithms, not the old control plane wholesale.**

| Legacy capability | New Steward location | Migration test |
|---|---|---|
| Guardian peer heartbeat / service probes | Host Agent + Pair Supervisor | LAN outage, service hung, network partition |
| Guardian leases / promotion rules | Ownership safety adapter; **rewrite if no provable fencing** | Mutual exclusion under asymmetric outage |
| Guardian/Consul discovery and placement records | Signed inventory / DNS and peer discovery adapter | DNS changes, stale record, witness unavailable |
| Guardian hot-standby preflight / staged promotion | Maintenance Manager | Host drain and handover with measured downtime |
| Lunar watchdog and reboot checks | Host-local watchdog policy | HA hung, host degraded, no reboot loops |
| Lunar evidence, alerting and service recovery rules | Repair Engine + audit | Repeatable safe repair + rollback |
| Lunar emergency recovery/remote action | Host Agent guarded executor | No uncontrolled reset; safety/authority checks |
| Old Guardian UI/duplicated dashboards | Steward unified view | Historical metrics mapped, alerts not silently lost |
| Legacy repair scripts | Reviewed signed recipe catalogue | Idempotence, clear ownership, controlled privilege |
| Existing JNS Deployment signature/rollback | **Reuse as-is** | Signed package, config check, rollback |
| Natural Automation parsing/approval | **Reuse as-is** | Same prompt preview/apply UX |

**Porting method:** collect actual services, scripts, binaries, systemd units, configs, timers, sudoers, firewall rules, IPC/message topics, Consul sessions, HA integrations and events; capture hash and provenance; mark each KEEP, PORT, REPLACE, QUARANTINE or RETIRE. No assumed source code from history. Run legacy and new monitoring side by side in **observe-only** mode; only one path may retain promotion/reboot authority.

## 5. Service-specific failover contracts
**HA-Primary / HA-General / HA-Security:** one automation/control writer; app-consistent incremental state; idempotent integrations; HA-Security hard interlocks; detect broken HA-Primary readiness entities without authorising failover. Standby is current but isolated from active physical outputs.

**MQTT:** Mosquitto bridge replication is **not** full persistence/session replication. Inventory retained messages, persistent sessions, queued QoS 1/2, credentials/ACLs, client IDs and will messages. Choose an actually supported HA-capable broker or tested active/passive persistence scheme. Stable `mqtt.home.arpa`, bounded DNS cache/reconnection, client recovery tests.

**Zigbee2MQTT:** replicate service configuration and network backup; only one controller accesses the serial/TCP coordinator at a time. CT210 physical radio is a distinct SPOF. Validate serial route, USB power, coordinator-state restoration and PAN/security identity before enabling replacement radio. Never pair a second live coordinator with same network identity.

**Bluetooth:** passive advertisement scanning can be multi-receiver with deduplication/quality selection; exclusive GATT connections and pairing keys require single-owner handover and radio coverage check. Treat scan reception as evidence, not as proof of actuator ownership.

**Network and DNS:** DNS-first dynamic v4/v6, no hardcoded moving service IPs. Independent wireless management link is telemetry+handover, not an authority by itself; no route bridging into production LAN without security review.

## 6. Cleanup and retirement plan

### Stage A — Evidence snapshot (no changes)
1. Enumerate all three physical hosts with DNS-first access; include `qm list`, `pct list`, storage, replication, systemd, network interfaces, PCI/USB mappings, snapshots and current boot policy.
2. Snapshot configs and dependency graph: which HA entity/integration, MQTT client, Zigbee adapter, DNS entry, webhook, scheduler and external service refers to each VM/CT.
3. Inspect Guardian CT115/116/117 + Lunar CT117 role overlap. Determine which watchdog actions or fencing controls are **actually active**.
4. Identify current VM900/901/909 and duplicate HA-Primary `ha_p0_*`/_2 registrations; do not delete entities to conceal integration errors.
5. Inventory stale packages, scripts, timers, cron, sudoers and service users; distinguish active invoked code from dormant historical files.
6. Capture backup integrity, timestamps and tested restore location; Node C nearly full thinpool is a capacity gate.

### Stage B — Classify and preserve
Every candidate has a ledger entry: identity, host, DNS, VMID, owner, last-activity evidence, dependency list, storage reclaimed estimate, snapshot/backup location, license/secret needs, rollback, maintenance window and named approval. Classify:
- **KEEP** active dependencies;
- **PORT** useful Guardian/Lunar logic;
- **REPLACE** only after new Steward functional equivalence;
- **QUARANTINE** disable autorun / network access without deleting disks (only after observation and explicit approval);
- **RETIRE** remove artifacts only after acceptance and retention window.

### Stage C — Shadow Steward deployment
Install non-controlling Host Agents, load telemetry side-by-side and compare to Guardian/Lunar. Validate no unexpected resource use or control. Neither Steward nor old components may promote HA or power-cycle hosts during shadow phase.

### Stage D — Service-pair migrations (one at a time)
First MQTT data/session requirements and one HA-General or HA-Primary pilot after correcting HA-Primary health. Then HA-Security, Zigbee2MQTT/CT210 and Bluetooth. For each: establish owner and standby, validate sync, deliberately test LAN/Wi-Fi separation, planned update, abrupt failure, asymmetric partition, stale backup, recovery and rejoin. Gate each rollout on measured RPO/RTO and no dual control.

### Stage E — Authority transfer
Provide signed transition manifest explicitly naming old Guardian/Lunar commands that lose promotion, reboot, power-control or automation authority. Deploy new Steward agent guards; revoke superseded credentials and admin wrappers carefully. Verify old service cannot self-reactivate on reboot. Preserve readonly history/export.

### Stage F — Quarantine, soak, retire
Quarantine old nodes and redundant code one component at a time; monitor at least **14 days** including an actual maintenance cycle and recovery drill (duration is proposed, not evidence). At each stage confirm no lost DNS, automation, broker, security, audio, sensor or serial bridge dependency. Restore a quarantined component on first regression. After signed acceptance and tested backup, retire guest, systemd units, service principals, stale DNS records, firewall permits and code. Keep immutable audit trail.

## 7. Mandatory stop conditions
Any of: unclear active owner; unreliable HA-Primary readiness; inability to fence; both peers on same failure domain; unsafe storage replication; MQTT state not verified; health dependency on failed node; broken DNS names; insufficient disk capacity; untested recovery; uncertain security/radio hardware ownership; unresolved Guardian/Lunar authority; recovery image unverified. These mean *do not promote/delete/reboot automatically*. Report an actionable alarm and keep safe control state.

## 8. Acceptance matrix
| Test | Expected result |
|---|---|
| Application process crash | Agent reports and local repair or fenced failover succeeds |
| HA VM planned update | Handover before reboot; no simultaneous automation writes |
| Proxmox host planned reboot | Surviving host handles eligible HA/MQTT services |
| Wired path failure, direct Wi-Fi remains | Maintain authenticated peer evidence; controlled demotion only if supported |
| Both peer paths lost | No uncontrolled dual ownership |
| Broker failover | Measure QoS, retained/session state and Z2M reconnect |
| Zigbee radio failure | No fake HA success; explicit coordinator recovery result |
| Failed primary returns | Isolated start, reconcile, joins as standby only |
| Rebuild | New guest from signed manifest and secure state; original fenced |
| Guardian/Lunar removed | No lost monitoring, no secondary watchdog authority |
| Storage pressure | Maintenance blocked before thinpool exhaustion |

## 9. Initial action list
1. Read-only estate audit with full names and dependency map; fix Node A/B hostname resolution (do not hardcode services).
2. Investigate Node C local-LVM at 99.65% and clear only proven retired data, with backup.
3. Recover HA-Primary monitoring/entity registration and the existing HA-General link **without another duplicate integration**.
4. Identify actual Guardian/Lunar processes, service commands, configuration paths and ownership controls before writing ported code.
5. Create per-service capability/replication matrix, then Steward Host Agent + read-only dashboard.
6. Stage MQTT and HA pilot with failover disabled, record acceptance evidence, then staged activation.
7. Migrate remaining services and retire only approved, quarantined assets.

## 10. Change management and provenance
This is a **target design**, not a claim that replication exists. No existing service, guest, integration, code path or DNS record has been removed or changed by this document. Authoritative verification requires current host read-only audits. Keep all production changes in signed JNS Deployment transactions with preflight, preview, explicit approval, health verification, rollback and provenance. GitHub commits are source/documentation only, **not** deployment instructions to the runner.
