# JNS Remote Development Gateway — baseline audit (2026-11-15)

## Verified
- Repository: jamienewton2269/JNS-Home-Assistant-Deployment; public; default branch main.
- Existing Node C queue uses gateway/queue/<job_id>.json with job_id and job_type.
- Executor rejected job_type gateway_capabilities with reason 'job_type is not allow-listed', exit 64.
- Job status and text results currently appear under gateway/status and gateway/results in the public repository.
- Existing repository is also the production JNS Home Assistant Deployment Platform; preserve its deployment, signing, rollback and management-PC enrollment workflows.

## Security stop condition
Do not enable arbitrary shell, PowerShell, SSH or unfiltered output publication. No credentials, sensitive host inventory, tokens, environment dumps or command output should be committed to public Git history. Redaction is defense in depth, not authorization to publish secrets. Review historical published results for exposure and rotate any exposed secrets using approved procedures.

## Read-only audit to run on Node C using existing approved executor
1. Identify runner service, identity, work directory, installed versions and permission boundaries without printing environment values or credentials.
2. Inventory trusted executor source, allowed job_type values, queue schema, locks, timeouts, retries and result publisher.
3. Identify approved SSH destinations and Windows/SAGE transport without disclosing credentials or host-specific sensitive details publicly.
4. Confirm test coverage, rollback checkpoints, queue retention and how old job IDs are handled.
5. Record only sanitized pass/fail summaries in this public repository; keep raw logs private on Node C.

## Proposed incremental changes (not yet enabled)
1. Add a read-only capabilities job_type to the existing allowlist after inspecting the executor's implementation and test harness.
2. Add schema validation, bounded runtime/output, idempotent IDs and explicit failure categories.
3. Introduce a private-result channel using existing GitHub permissions/artifacts only if access controls are verified; otherwise retain sensitive results locally and publish status only.
4. Add scoped workspace file operations with path canonicalization, atomic replacement, backups and checksum verification.
5. Add named Linux and Windows PowerShell execution profiles, explicit target allowlists, no generic arbitrary command string, and separate approval for deployments.
6. Run existing regression tests and a new deny-by-default test suite before proposing merge; never auto-deploy from this audit branch.

## Acceptance checks
- Existing queue jobs remain compatible; unknown job types still fail closed.
- Sensitive results are not pushed to public Git history.
- Failed, timed-out and duplicated jobs return deterministic safe status.
- File operations reject traversal, symlink escape and paths outside assigned workspaces.
- No live deployment or runner service modification occurs without explicit approval.

## Rollback
Changes only through reviewed commits and a dedicated branch; preserve the current main commit as a rollback reference. Do not change running Node C services until audit and tests pass.
