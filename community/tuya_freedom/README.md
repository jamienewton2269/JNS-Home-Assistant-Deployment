# JNS Tuya Freedom — community migration toolkit (v0.1 candidate)

A conservative, reusable **Home Assistant Tuya cloud → local** migration tool.
Designed for standard HA Core/OS/Supervised/Container installations. Do not
write to or patch Home Assistant `.storage` directly. Uses HA's supported
WebSocket entity-registry commands and REST config flows.

## What works today

- Read registered Tuya cloud entities, Tuya Local and LocalTuya entities, and
  Tuya-manufacturer entities already handled by MQTT/ZHA/Matter.
- Build **private**, name-based migration suggestions. Every suggestion is
  unapproved by default; a matching name alone is **not** proof of the same
  physical device or datapoint.
- Reuse installed `tuya_local` rather than install competing duplicate handlers.
- Drive Home Assistant's supported config flows from a private series of
  explicit form responses, when local keys / device types are known.
- Rename approved cloud entities to an unused backup ID, then rename a
  verified, loaded local entity to the original HA entity ID. This preserves
  **entity-ID** references in normal automations/dashboards.
- Keep a private rollback journal; restore the old registry names on request
  or after a failed cutover.
- Check that migrated local entities still appear responsive.

**Not yet automatic:** extracting unknown per-device Tuya local keys,
identifying every Tuya device type and datapoint, updating automations that
target a **device ID** rather than an entity ID, testing physical device
actuation without an operator, enforcing router firewall policy, or proving a
device can survive a cold boot with Tuya WAN/DNS blocked. Therefore v0.1 does
**not** remove or disable the Tuya cloud integration and does **not** claim a
completed offline migration.

## Prerequisites

1. Create and **verify** a complete HA backup and export/copy the existing
   config/entity registry. Do not edit registry JSON. Ensure rollback access.
2. Install [Tuya Local](https://github.com/make-all/tuya-local) from HACS if
   not already installed. Where possible, use a **stable DNS name**, not a
   hardcoded DHCP address, for the device's local host.
3. Have an HA admin long-lived token stored in an environment variable
   (`HA_TOKEN`); do not commit or paste credentials into GitHub Actions.
4. Run on a trusted computer with Python 3.10+ and `websocket-client`:

   ```shell
   python3 -m pip install "websocket-client>=1.8,<2"
   export HA_TOKEN='...read token securely from your password manager...'
   ```

5. Use `--url http://your-ha-hostname:8123` for your own installation.

## Initial scan and proposal (no HA changes)

```shell
python3 tuya_freedom.py audit --url http://ha-general.home.arpa:8123
python3 tuya_freedom.py plan  --url http://ha-general.home.arpa:8123
```

These write `tuya-freedom-private-inventory.json` and
`tuya-freedom-private-plan.json`, both mode `0600`. Keep them on trusted
storage, outside any public repo. **Do not publish them.**

Each proposed mapping has:

```json
{"cloud": "switch.example", "local": "switch.example_local",
 "confidence": "name_hint_not_verified", "approved": false}
```

Before setting `approved` to `true`, verify the **same physical device and
same function/datapoint** (switch-to-switch, sensor-to-sensor). Wrong matches
can cause unintended switching.

## Onboard devices where local keys are available

Tuya Local's own flow may offer a **one-time** Tuya/Smart Life cloud login
to retrieve local keys. That is an onboarding convenience, not a runtime
cloud dependency, but credentials should not be retained in this tool.
Keys change if devices are re-paired. See Tuya Local device instructions.

For repeatable local provisioning, capture the *specific version's* config
form responses as a local JSON file (mode `0600`), for example:

```json
{
  "handler": "tuya_local",
  "devices": [
    {
      "steps": [
        {"host": "plug.home.arpa", "device_id": "REPLACE_LOCALLY",
         "local_key": "REPLACE_LOCALLY", "protocol_version": "auto"}
      ]
    }
  ]
}
```

That example illustrates a **possible form step, not a guaranteed complete
Tuya Local flow**. Actual flows are multistep, may begin with account/choice
forms, and may require type/name selection. The tool **fails closed** when
additional forms are needed; update the manifest locally to match the installed
integration's live form fields. Never put key files in GitHub.

```shell
chmod 600 /trusted/private/tuya-flow-steps.json
python3 onboard.py --url http://ha-general.home.arpa:8123 \
  --steps-file /trusted/private/tuya-flow-steps.json \
  --apply --confirm ONBOARD
```

## Guarded entity-ID cutover

After adding the local entities and checking they work, approve exact pairs
in the private plan file and run:

```shell
python3 tuya_freedom.py cutover --url http://ha-general.home.arpa:8123 \
  --confirm CUTOVER
python3 tuya_freedom.py verify --url http://ha-general.home.arpa:8123
```

Keep the private journal. Cutover **does not remove the cloud config entries**.
The tool will refuse missing/unavailable local entities, duplicate mappings,
mismatched entity domains or unapproved suggestions. It will not act on a light
or switch during validation, so physical function tests are still necessary.

To revert:

```shell
python3 tuya_freedom.py rollback --url http://ha-general.home.arpa:8123 \
  --confirm ROLLBACK
```

**Journal/rollback scope:** entity-registry ID renames only. This does not
revert config-entry changes, device references or router/firewall changes.
Keep HA full backups, and resolve unexpected states before further cutovers.

## Acceptance criteria for actual cloud independence

For each migrated physical device:

1. Functional local state and command verification, including correct
   datapoints and HA automation behavior. Keep cloud control until stable.
2. Test local control with *device* internet access blocked at the router;
   if the device stalls, a device-specific DNS block may also be needed.
   Apply/undo these rules **per device**, not across the entire IoT LAN.
3. Confirm operation across an extended outage and **power cycle of the
   device**, plus a Home Assistant restart. Observe availability and commands.
4. Check the router's WAN/DNS logs to show the device is not using Tuya
   endpoints and no remote rule bypass remains.
5. Only then consider disabling its cloud config entry. HA Tuya cloud entries
   often cover multiple devices, so only disable when **all** devices on the
   entry have migrated or been deliberately excluded.
6. Recheck automations, dashboards, device-ID triggers and recovery.

Some Tuya firmware remains **cloud-dependent even with local LAN APIs**, and
some devices do not expose every datapoint locally. Such devices should be
reported as **blocked/unsupported**, not silently switched.

## JNS-specific read-only baseline (2026-10-24)

The JNS Node C audit of HA-General (VM905) confirmed 3 cloud Tuya config
entries, 34 cloud entities, 36 devices assigned a cloud config entry, and 5
Tuya Local config entries containing local-key fields (54 local entities).
LocalTuya was absent. Further *private* per-device reconciliation is required.
The JNS production audit **does not automatically run this community cutover**.

## Security and community packaging

- No local keys/tokens are requested on the command line; the HA admin token
  is read from an environment variable. Treat local JSON manifests as secret.
- Never upload `.storage` or raw audits to GitHub.
- A name-only mapping is always subject to an explicit operator approval.
- HA state checks are not a substitute for actual offline network testing.
- Run `python3 -m unittest -v test_tuya_freedom.py` for dry-run safety tests.

License/reuse: code intended for a future standalone community repository
after tests, documentation and permissions review. No upstream endorsement.
