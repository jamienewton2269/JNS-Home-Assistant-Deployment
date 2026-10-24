# JNS Steward — Retirement ledger template

No node, service, package or disk may be deleted from this template. Evidence and a tested restore are required.

| Candidate | Last reported state | Action now | Retirement gate |
|---|---|---|---|
| Guardian CT115/116 | Historical; current state unknown | Inspect and map heartbeat, lease, fencing and deployment dependencies | Prove new Steward controls, standby test, reversible isolation |
| Lunar CT117 | Running on Node C in supplied audit | Port watchdog and safe recovery routines | Side-by-side comparison, no competing reboot authority |
| HA VM900/901 | Historical monolith and standby | Inspect Zigbee/radio ownership | No active controls, backup, quarantine soak |
| HA VM909 | Stopped on Node C in supplied audit | Check whether required for recovery; 256GB allocated is not necessarily used | Backup/restore proof and retention approval |
| Node C VM990/991/9906 | Stopped in supplied audit | Audit test and golden-image dependencies | Valid replacement, explicit approval |
| Old Guardian scripts / cron / sudoers | Unknown | Discover commands, triggers, accounts | Authority revoked after Steward replacement acceptance |

For EACH candidate record exact host and ID, service users, DNS names, network clients, MQTT topics, HA automations, USB passthrough, storage volumes, backups, recovery proof, rollback command, evidence timestamp, approval, quarantine start/end and reclaimed storage estimate.

Proposed quarantine minimum: 14 days including maintenance and failover test. Never clear Node C's near-full thinpool by deleting unverified snapshots or guest disks.
