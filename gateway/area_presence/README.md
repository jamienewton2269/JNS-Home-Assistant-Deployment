# JNS MQTT Areas + Welcome Home — live deployment state

Verified 2026-10-24 via Node C GitHub runner, VM902/VM905 guest reads and MQTT retained topics.
**Do not rerun initial installation steps** without checking the current installation first.

## HA-Primary VM902 — installed and running
- Native MQTT integration configured, title `mqtt-infra-a.home.arpa`.
- `mqtt_statestream` present in `/config/configuration.yaml`, base topic `jns/ha-primary`.
- Four allowlisted phone entities (tracker, Wi-Fi sensor and two Bluetooth entries), publish attributes disabled.
- Native `jns_native_area_sync` installed with `node: ha-primary`, `apply: true`.
- Core restarted **after** its configuration and component file changes on 2026-10-24.
- Area registry now has 11 areas: nine HA-General shared areas plus local `security` and `general`.
- Latest retained `jns/site/areas/sync/ha-primary` generated at **2026-10-24T16:00:00Z**:
  nine already-present shared areas, zero missing, zero conflicts, zero created.
- The receiver uses the existing MQTT integration; no second broker is installed.

## HA-General VM905 — installed, intentionally inactive pending arrival validation
- MQTT native integration already configured.
- `/config/packages/jns_welcome_home.yaml` exists; Core restarted after the package was deployed.
- Automation registry contains and enables:
  `automation.jns_welcome_home_process_remote_presence`
  and `automation.jns_welcome_home_release_exterior_lighting`.
- Last restored status: `input_boolean.jns_welcome_home_enabled=off`, timer `timer.jns_welcome_home=idle`.
- **DO NOT turn the enable helper on until the presence transport and a true away→home event are validated.**
- Arrival is gated on away for at least 3 minutes and after sunset. Garage/Dogs Run and Front Door light outputs must honour PIR, doorbell and back-door timer interlocks.
- Faulty Tuya back-door sensor is awaiting replacement; do not alter its separate automation.

## Outstanding transport verification
- MQTT broker test using `mosquitto_sub` confirmed the retained area catalogue and retained sync report.
- Retained topics `jns/ha-primary/device_tracker/sm_s721b/state` and
  `jns/ha-primary/sensor/sm_s721b_wi_fi_connection/state` **were not present** during
  the 2026-10-24 live audit. This does not prove a publisher fault: MQTT Statestream
  emits on state changes, and none may have occurred since Home Assistant restart.
- Request a controlled Companion App sensor update (e.g. temporary Wi-Fi OFF then ON,
  opening HA mobile app so the sensors update). Read only MQTT topic presence, never
  publish private phone location values into GitHub logs.
- Once the phone topic appears, confirm VM905 processed a real away→home event,
  then enable master helper deliberately and conduct physical lighting verification.
- If topic still absent after a known state change, diagnose `mqtt_statestream`
  runtime, MQTT connection health and HA log before another restart.
- VM906 HA-Security area receiver remains pending verified management access.
  Do not claim area synchronisation to VM906.

## MQTT HA failover future
- Currently clients use `mqtt-infra-a.home.arpa`. Maintain as operational.
- Future broker HA should have a stable service name `mqtt.home.arpa` pointing at a
  fenced active broker VIP; promote standby only after authoritative checks.
  Coordinate retained messages, MQTT sessions, client reconnects and split-brain
  avoidance. No DNS/VIP cutover has been performed.

## Reference traces
- JNS Primary MQTT Configured Check: GitHub Actions run **40110274300**.
- JNS MQTT Live Area and Presence Audit: **40110398998**.
- JNS Welcome Home MQTT Transport Runtime Audit: **40110619731**.
- JNS MQTT Deployment Final State: **40110799719**.
- Scripts are in `gateway/area_presence/`; workflows use Node C runner.
- No live Home Assistant configuration files were modified by these 2026-10-24
  audits; only read-only inspections were performed.
