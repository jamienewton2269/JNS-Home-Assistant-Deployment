# HA-General Testing dashboard

**Target:** VM905 `ha-s2-general` / HA-General.

**Dashboard title:** `Testing`.

**Purpose:** Give a simple Home Assistant-native recovery and commissioning surface for devices while the Zigbee and Tuya-local migration is being stabilised.

The dashboard uses the established `lovelace-auto-entities` card rather than maintaining a second hand-written device list. Current and future Home Assistant entities therefore appear automatically in the appropriate controls/sensors/fans views. Device location is stored in the normal Home Assistant **Area** field and commissioning classifications are stored as standard **Labels**.

Commissioning labels:

- `Commissioned`
- `Purpose: Standard Light`
- `Purpose: General Socket`
- `Purpose: Fan`
- `Purpose: Protected IT`
- `Purpose: Grow Light`
- `Alarm Profile`
- `Alarm Excluded`

Protected IT controls are intentionally separated and require confirmation before toggling.

The canonical dashboard file is `testing-dashboard.yaml`.
