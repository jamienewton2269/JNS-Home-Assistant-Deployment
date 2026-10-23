# JNS HA MQTT Areas + Welcome Home — coordinated deployment

Status (2026-10-23): **STAGED, NOT ACTIVE** on HA-Primary (VM902).

## Already verified on live infrastructure
- VM905 publishes retained `jns/site/areas/catalogue` on `mqtt-infra-a.home.arpa:1883`.
- Schema `jns.area-catalogue.v1`, source `ha-general`, nine areas.
- VM902 knows five areas and must never automatically rename/delete its existing areas.
- VM902 Samsung `device_tracker.sm_s721b` and `sensor.sm_s721b_wi_fi_connection` are enabled.
- VM902 connects to the existing broker TCP port, but has **zero native MQTT config entries**.
- VM905 has native MQTT integration and owns all lighting automations.
- VM906 area receiver is pending management access; do not pretend it is synchronised.

## Native MQTT prerequisite (VM902 UI)
1. HA-Primary -> Settings -> Devices & services -> Add integration -> MQTT.
2. Use existing broker `mqtt-infra-a.home.arpa`, port `1883`.
3. Do not provision another broker; use broker credentials only if required.
4. Confirm that MQTT shows **Configured** and connected in VM902.

## Release phases (guarded)
1. Audit current `configuration.yaml`, component folders and MQTT entry.
2. Backup every original VM902 file before editing.
3. Stage only the four phone presence entities in `mqtt_statestream`, with attributes excluded.
4. Install `jns_native_area_sync` for the retained catalogue, initially `apply: false`.
5. Run `ha core check`; if invalid restore backups, **do not restart**.
6. Restart VM902 Core once; confirm publisher on `jns/ha-primary/.../state` and
   dry-run MQTT report `jns/site/areas/sync/ha-primary`.
7. Review missing/conflicting area IDs. If conflict-free, change `apply: true`
   and validate/restart before adding **missing only**. Never rename or delete.
8. On VM905, install `jns_welcome_home_vm905.STAGED.yaml` under `packages`,
   initially leave `input_boolean.jns_welcome_home_enabled` off.
9. Validate and restart VM905 carefully (avoid concurrent HA maintenance).
10. Test MQTT phone away/home events and the three-minute away gate; activate
    the enable helper only after actual end-to-end events are verified.
11. Validate 10-minute Front Door and Dogs Run lighting, retaining PIR,
    doorbell and back-door timer interlocks.
12. Later extend the same area subscriber to HA-Security VM906 using its
    existing native MQTT connection (no broker duplication).

## Important constraints
- HA-Primary VM902 remains lightweight: only mobile state publishing,
  native MQTT receiving and area registry reconciliation. Never run
  exterior-light automation logic or camera processing there.
- HA-General VM905 remains sole automation/action owner and area authority.
- `jns_native_area_sync` only accepts schema `jns.area-catalogue.v1` with
  source `ha-general`; default is **dry-run** and conflicts are explicit.
- All report topics are retained; no extra per-node MQTT broker.
- Wi-Fi SSID backup source has no confirmed home SSID; never infer the value.
- The broken Tuya back door sensor is separate and awaiting replacement;
  preserve its installed Dogs Run automation and duration control.
- No direct mutation of Home Assistant `.storage` and no public logs of
  credentials or phone location/SSID states.
