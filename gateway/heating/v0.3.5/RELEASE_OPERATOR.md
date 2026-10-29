# JNS Heating Zones v0.3.5 — guarded production promotion

**Status: release controller prepared and tested; NOT installed on Node B; production VM905 remains v0.3.4.**

This page distinguishes the tested private staging operation from a *live*
Home Assistant integration update. The purpose is to prevent a file-level
commit being mistaken for activation.

## Correct deployment mechanism

Home Assistant Core loads Python custom integration modules into memory.
`homeassistant.reload_config_entry` can unload/recreate an integration entry,
but **does not reliably import edited Python source**. The release must use a
**guarded Core-only restart**, not a Proxmox VM reboot and not a simple
configuration-entry reload. Other HA-General automations will be unavailable
during that Core restart. Plan an availability-safe window.

A `release_controller.py` designed for a **root-owned Node B installation**
is included. It is intentionally *not callable by GitHub Actions*. It:
1. Verifies root-only permissions, exact SHA/stage ID and a **local,
   short-lived, single-use** operator approval.
2. Uses an existing, root-owned Home Assistant administrator long-lived token
   to read live HA state at `http://ha-general.home.arpa:80`; the
   `SUPERVISOR_TOKEN` inside Core is **not** a Home Assistant admin token.
3. Requires HA Core state RUNNING, no recorder migration, Lyric thermostat
   temperature valid, and a live *off* heating-call sensor. Blocks if thermostat
   reports `hvac_action=heating`.
4. Verifies private staging state, unchanged source fingerprints and
   original learning-store backup. Applies precisely `thermal.py` and
   `manifest.json` via the checked, root-owned `transaction.py`.
5. Runs `ha core check` and `ha core restart` on HAOS **VM905 only**.
   Does not touch Proxmox VM power, MQTT, Zigbee, HA900, VM902, VM903 or
   Honeywell setpoints.
6. Polls the live Home Assistant API and verifies the new learner publishes
   `valid_windows` status, proving the replacement Python code is live.
7. On failure, restores the original files through the **HAOS host filesystem**
   (`/mnt/data/supervisor/homeassistant/`), even if the Core Docker container
   cannot start. Attempts a second Core restart and checks recovery; announces
   CRITICAL if rollback/recovery cannot be verified.
8. Preserves **all** currently accumulated learning samples. It never copies
   the older backup onto live `.storage` files.

## One-time operator prerequisites (do not paste tokens into ChatGPT or GitHub)

- Root-controlled Node B deployment of the two vetted files:
  - `release_controller.py` as
    `/usr/local/sbin/jns-heating-promote`, owner root:root, mode **0700**.
  - `transaction.py` as
    `/usr/local/libexec/jns-heating/transaction.py`, owner root:root,
    mode **0600**.
- `/etc/jns/` must be root-owned and mode **0700**.
- Create a Home Assistant long-lived access token **using a local
  administrator account** from the Home Assistant user profile. Put the token
  **only** into `/etc/jns/ha-general-api.token`, root:root mode **0600**.
  Use a trusted local console, not a GitHub workflow, shell command argument,
  terminal transcript, chat or repository commit. Revoke it after promotion
  if long-term control is not required.
- Immediately before maintenance, root creates a mode-0600,
  single-use `/etc/jns/heating-v035-approval.json` with **exact keys**:
  ```json
  {
    "stage_id": "v035-20261024T162546Z-43b0f6ec",
    "candidate_sha256": "43b0f6ec0229d15dc137bbf3c52cd41b4bb125072fbcc49202e744ba8a19bc6c",
    "intent": "promote_v035",
    "expires_utc": "REPLACE_WITH_UTC_ISO8601_WITHIN_30_MINUTES"
  }
  ```
  The expiry must be within the next 30 minutes. The handler consumes the
  approval at promotion; a later attempt needs a new approval.
- Confirm maintenance window, alternative control of heating if required,
  stable Node B power and no Solar Economy automatic shutdown during the
  restart. Record the existing thermostat setpoint externally.

## Root-owned operator commands on Node B *after prerequisites*

```bash
/usr/local/sbin/jns-heating-promote --preflight
# Only if it reports JNS_HEATING_SAFE_TO_PROMOTE:
/usr/local/sbin/jns-heating-promote --promote
```

**Never** run `--promote` before root-only file installation, live
authenticated preflight and an agreed availability-safe Core restart window.
A passed `--preflight` does not imply that HA will be available at the time
of a later promotion; the controller checks the live sensors again.

## Observed live state at last read-only audits

- Node B VM905, HAOS running Core 2026.10.1, listener **port 80** (not 8123).
- The Home Assistant Core Docker container is running.
- Heating integration `jns_heating_zones` and original v0.3.4
  `thermal.py` match the protected baseline.
- The existing config entry supports `async_unload_entry`, but Python
  module replacement still requires a Core restart.
- Home Assistant **returns HTTP 401** for the available Supervisor token.
  No administrator long-lived token has been supplied to or installed by this
  deployment, so authenticated live-state checks and production promotion
  have **not** run.
- Recorder last showed `binary_sensor.lyric_home_heating_heating_call=off`,
  but an old database record is **not** a substitute for live API state.
- Existing private v0.3.5 stage passed checksum and restrictive permissions
  validation. No production source, learning storage, dashboards or
  thermostat configuration was changed.

## Relevant code and checks

- `release_controller.py`: root-owned fixed-target operator release program
- `transaction.py`: guarded staging and source backup/restore
- `test_release_controller.py`: synthetic integration lifecycle,
  live heating guard and host-side emergency rollback tests
- `test_transaction.py`: permissions, backup integrity and rollback
- `thermal.py` / `test_thermal.py`: advisory thermal model and synthetic tests

Review the latest green `JNS Heating v0.3.5 Candidate Tests` workflow,
the earlier real historical-data shadow test, and private-stage verification
before placing any root-owned script into production.
