# VM905 heating v0.3.5 — dormant root-owned JNS promotion capability

**Status: TESTED IN ISOLATION, NOT INSTALLED. Production HA-General still runs v0.3.4.**

## Verified production prerequisites

- Private backup-only stage: `v035-20261024T162546Z-43b0f6ec`
- Candidate digest: `43b0f6ec0229d15dc137bbf3c52cd41b4bb125072fbcc49202e744ba8a19bc6c`
- Original thermal source digest: `44054f9172e3c9e2e944240b5369b49d9735d8349fb7ca2dd0a2a782d7c8a4f8`
- Node C root dispatcher digest: `9d4f853b2e8264cb10a25a5ee5f23bd92c521e86f447de8c7278644d8caa7f8a`
- Root dispatcher job types currently **exclude** any heating promotion capability.
- Direct HAOS host rollback path has been checked and matches active Core:
  `/mnt/data/supervisor/homeassistant`.
- The original source, candidate and backup exist with expected digests on that host volume.
- `ha core info` reports HA Core **2026.10.1**, watchdog and boot enabled. This is informational; does not alone establish that every heating entity is available.
- Audit evidence:
  [gateway readiness](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40121661029),
  [recovery path](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40121826450).

## Least-privilege design

1. The proposed v4 root wrapper is **exactly** the existing root-owned v3 script plus one branch for `ha_heating_v035_promote`. All existing job types and fallback behaviour are preserved.
2. The new root-owned handler accepts precisely one immutable job JSON with keys
   `job_id`, `job_type` and `stage_id`. VM905, Node B, backup ID and candidate digest are hard-coded. No arbitrary host, VM, path or shell command may be supplied.
3. GitHub queue data is **not approval**. The handler requires an **interactive, local root-created**, mode-0600 permit inside `/etc/jns/heating-v035/`, mode 0700. The permit names the exact queued job, contains the pinned candidate digest, records heating-interruption consent and expires within 15 minutes.
4. The handler consumes that permit before any action and serialises executions with a root-owned lock. Replay and mismatched jobs are rejected.
5. Before modifying anything it requires the original staged checksums, existing v0.3.4 runtime, working HA Core loopback API, HA configuration validation, and verified independent HAOS host recovery.
6. The only planned Core change is replacing `jns_heating_zones/thermal.py` and the matching version metadata; all Lyric credentials, heating settings, entity registry, historical learning Store and dashboards remain untouched.
7. `ha core check` runs before and after file transaction, followed by controlled Core restart. The runtime must return a working Core HTTP API and expected thermal-module digest. On failure, rollback restores originals, including via HAOS host files if the Core container is unavailable, and attempts a further controlled restart.
8. Predictions remain *advisory only*; no change to active thermostat setpoint or heating duty is authorised.
9. The handler is **not** automatically executed from a push to the development branch. There is no automatic privileged installer workflow.

## Package files

- `promotion_policy.py`: pure strict job/permit validation
- `root_owned_promotion.py`: **DORMANT** fixed-purpose privileged handler
- `approval_once.py`: explicit interactive local-root permit generator, bound to immutable job ID
- `jns-gateway-exec-wrapper-v4-heating.sh`: exact single-case extension
- `install_nodec_gateway.py`: root-local installer, dry-run by default
- `transaction.py`: existing backed-up, version-pinned Core file transaction
- `test_promotion_policy.py`: deny-by-default / permit scope and expiry tests

## Activation sequence — not performed

The next prerequisite is a **reviewed, interactive installation on Node C** by an authorised administrator. The existing GitHub runner does not have permission to install root-owned dispatcher code, by design.

A controlled promotion later needs:

1. Confirm VM905 is hosting essential live heating services and choose a safe maintenance window. Check that someone can recover local heating if HA Core does not restart.
2. Verify the reviewed commit and install only the dormant root dispatcher extension interactively on Node C, using `install_nodec_gateway.py --apply`. Its dry-run does no writes; the `--apply` mode refuses unattended execution.
3. Create a unique immutable queue job on the **main** branch, using the specific job type and stage ID. The queued job must contain no other keys.
4. Use the installed `approval_once.py --confirm-heating-outage --job-id <EXACT_JOB_ID>` as **local root in an interactive session** just before submitting that job. The approval is short-lived and single use. Do not put permits, credentials or learning files in the repository.
5. Observe the explicit gateway result and independently validate heating sensor states and Lyric heating demand after Home Assistant comes back.
6. If checks or heating availability fail, stop. Investigate the gateway/HAOS recovery result before any repeat; do not use generic root shell deployment as a workaround.

**No scheduling or unattended promotion is enabled.** A timed automation could inadvertently restart the active heating node at an unsafe time.

## Current block

As of this engineering update the privileged handler is **source code only**.
Without its separately installed root-owned dispatcher case and local root permit,
the JNS GitHub queue cannot perform a production heating restart. The retained
v0.3.4 production and private v0.3.5 stage are deliberate safe defaults.
