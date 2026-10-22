# Plant Manager — Preservation Decision

Status: **PRESERVE — DEVELOPMENT ASSET**, not currently in operational use (user confirmed 2026-10-22).

- Current known deployment: Node B VM903 (ha-s1-plant), running as of 2026-10-22 screenshot.
- It is **not an obsolete guest** and is **not approved for deletion, reinitialization, overwriting, or consolidation**.
- Retain all existing development work, configuration, scripts, integrations, databases, secrets, snapshots, and recoverable VM state.
- May assess whether to stop the VM to save resources only **after** a verified restorable backup and review of dependencies; no change without user approval.
- Distinguish *not currently in use* from *no longer required*.
- Any future Proxmox cluster ID remapping or host migration must preserve Plant Manager's state.
- Steward and guest-purpose cleanup audits should classify this workload as **RETAIN/ARCHIVE-SAFELY**, never RETIRE.

Recorded as a configuration decision only. No production guest was changed.
