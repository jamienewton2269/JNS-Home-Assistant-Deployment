# Natural Automation + HA Steward v1

Natural Automation is the user-facing natural-language automation interface.  
HA Steward is its offline knowledge, history, diagnosis and repair-reference layer.

## v1 architecture

1. **Natural Automation** interprets the user's request and resolves Home Assistant targets.
2. **HA Steward** supplies local facts, observations and searchable offline repair knowledge.
3. **Transactional writer** performs approved changes with backup, Home Assistant validation, restart/read-back verification and rollback.
4. **Real Progress** reports measured backend stages rather than cosmetic progress.

The language layer never bypasses the transactional writer.

## Canonical source

The authoritative source is this directory in GitHub:

- `src/natural_automation.py`
- `src/steward/`
- `src/real_progress/`
- `systemd/natural-automation.service`
- `tools/seed_repairs.py`
- `tests/`

`live_recovered/` is the frozen Node B source recovered before v1 consolidation. It is retained for provenance and comparison, not deployment.

## HA-General targeting

v1 no longer binds the service to VM905 or a fixed Proxmox node.

The target resolver searches for the HA-General role by canonical VM names:

- `ha-s2-general`
- `ha-general`

It checks the local Proxmox host first, then configured DNS-named peers.  
Default peer names are DNS-first and contain no fixed IP addresses.

Environment overrides:

- `NA_TARGET_ROLE`
- `NA_TARGET_NAMES`
- `NA_PROXMOX_HOSTS`

If the role cannot be resolved, writes fail closed.

## Apply flow

For supported, fully resolved requests:

`Analyse → native HA preview → Apply automation → confirmation → re-check target/conflicts → snapshot → write → ha core check → restart → read-back verify`

The browser submits only a short-lived server-side `proposal_id`; it cannot submit an arbitrary automation object to the writer.

v1 deliberately withholds Apply when timing cannot be translated without assumptions.

## Offline Repair Knowledge

Historical HA repair/test scripts are compiled into the Steward SQLite database as searchable `manual_review` knowledge.

Each imported record contains:

- source repository path
- SHA-256 of the original script
- original script content
- inferred subsystem
- applicability metadata
- safety classification
- rollback/verification guidance

Historical records are advisory only and never grant execution permission.

## Data preserved across upgrades

The installer preserves `/opt/natural-automation/data`, including:

- aliases
- audit/change history
- Real Progress learned statistics
- Steward SQLite knowledge

Before installation it also snapshots the previous application/service and Steward DB under:

`/opt/.natural-automation-releases/`

Each snapshot includes a rollback script.

## Test

```bash
python3 -m unittest discover -s natural_automation_steward/tests -p 'test_*.py' -v
```

GitHub CI additionally validates rendered JavaScript and repair-seed generation.

## Current write scope

v1 write enablement remains intentionally narrow:

- native automation creation: enabled after explicit confirmation
- general repair execution: gated
- integration installation: gated
- device pairing/re-pairing: gated
- service migration: gated
