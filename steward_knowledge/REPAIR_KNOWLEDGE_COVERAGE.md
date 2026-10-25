# JNS Steward repair-knowledge coverage

Verified against the live host-based Steward on Proxmox Node B on 2026-10-25.

## Operational contract

The deployment repository is the canonical source for repair, maintenance and diagnostic scripts and orchestration workflows. The private JNS-Steward-Diagnostics repository continues to supply separate site-state snapshots; it does not confer permission to run repairs.

The v2 static catalogue records each source file verbatim, SHA-256, detected subsystem, purpose and **evidence of that purpose** (docstring, source comments, workflow name or filename-only inference), operational primitives observed in the source, workflow references, verification/rollback indicators, portability restriction and applicability cautions. All records are **manual_review**, `portable=false`, and `execution_authority=none`.

**Do not interpret source existence as proof that a repair was ever run.** Current records intentionally mark execution results as `not_established_from_repository_source`. A workflow's presence is not its deployment outcome.

## Confirmed current installation

The latest full sync contained 564 current source artifacts and retained 17 earlier historical records, for 581 offline-searchable entries in the Steward SQLite DB at `/opt/natural-automation/data/steward.db`.

Purpose provenance of the full source catalogue:

- Python module docstring: 147
- Script header/source comments: 109
- Named orchestration workflow: 223
- Filename-only inference, requiring contextual review: 85

The 85 underdocumented sources are explicitly recorded in the facts namespace `repair_catalogue`, manifest key `unreviewed_purpose_paths`. This list is a **coverage review queue**, not an assurance that their historical purpose or outcome is known.

## Querying offline knowledge

On the existing Node B Steward host:

```sh
python3 /opt/natural-automation/tools/steward_repair_lookup.py "zigbee" --limit 5
python3 /opt/natural-automation/tools/steward_repair_lookup.py "lux manual" --limit 5
python3 /opt/natural-automation/tools/steward_repair_lookup.py "tuya" --limit 5
```

The results contain why, how, source provenance, known workflow references, verification and rollback advice, and limitations. Full source text is stored in the SQLite recipe's `artifact.content` but omitted from normal query output. The Natural Automation browser does **not yet expose this search as a graphical UI**; the offline CLI is operational now.

## Refresh and recovery

The GitHub workflow `.github/workflows/jns-steward-full-repair-sync.yml` uses the existing Node C self-hosted runner and trusted SSH connection, on a six-hour schedule and on explicit `steward_knowledge/repair-catalogue-sync.request` updates.

Each refresh compiles and tests the catalogue, verifies current source revision, transmits it to Node B, and imports safely into SQLite. When source scripts change, the importer makes a verified SQLite online backup before a transaction, preserves existing learning and historical records and verifies the searchable index. When the digest of the source inventory is unchanged, only the freshness manifest is updated. Neither case restarts Home Assistant nor Steward, changes Home Assistant automations, or runs any imported repair procedure.

Last known full import: [Actions run 40144881642](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40144881642).
Last confirmed no-op refresh: [Actions run 40144921186](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40144921186), `unchanged=true`, no new SQLite backup.

## Outstanding for genuinely full operational understanding

For each underdocumented procedure, attach an evidence-backed dossier including: observed failure/symptoms, why this particular fix was chosen, exact production target at the time, human approval, invoked revision, execution log or run ID, observed pass/fail result, subsequent regression checks, and tested rollback. Information from a conversation or legacy filename should not be silently promoted to verified live history.

Do not grant automatic execution, privileged escalation or write access merely because a procedure is indexed. Use the separate Steward proposal, approval, transactional apply and validation contract.
