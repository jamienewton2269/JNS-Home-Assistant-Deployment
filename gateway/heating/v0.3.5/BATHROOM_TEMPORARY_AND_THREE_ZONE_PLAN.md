# JNS temporary bathroom thermal source and three-zone plan

**Requested on 25 October 2026:** Use Bathroom Sensor temporarily for
predictive learning, exclude shower-related temperature and RH excursions,
keep Honeywell thermostat as heating controller; plan three additional Zigbee
temperature sensors (beside thermostat, upstairs, living room/fireplace).

## Proven input quality

- Bathroom temperature entity:
  `sensor.0xa4c1382471d2ed23_temperature`
- Bathroom humidity entity:
  `sensor.0xa4c1382471d2ed23_humidity`
- Honeywell heating-control reference:
  `sensor.thermostat_thermostat_indoor_temperature`
- Live external weather entity:
  `weather.ha_general`, with existing outdoor temperature source still
  `sensor.thermostat_thermostat_outdoor_temperature` until independently
  validated replacement.
- Bathroom temperature measures in ~0.01°C increments; current whole-degree
  Honeywell feed alone is not identifiable enough for thermal regression.
- In a recent 72-hour Recorder summary, bathroom temperature ranged from
  20.85°C to **35.73°C**, and showed an abnormal jump over 3°C.
  The 35.73°C plateau contaminated the median: **never import this old
  period into a house learning model**.
- Latest observations at audit: Bathroom 20.89°C, Honeywell 20°C, bathroom
  humidity 59.35%RH. The last recorder-change time is not necessarily
  the latest MQTT-report time when retained values repeat.
- Read-only evidence:
  https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40194634979

## Guarded provisional input (candidate only)

New pure filter `bathroom_reference.py` with regression tests in
`test_bathroom_reference.py`:
1. Only genuine, timestamped MQTT/HA reports, max 15 minutes old;
   same retained state cannot repeatedly qualify as a new observation.
2. 3 good measurements spanning at least 10 minutes before acceptance.
3. Reject 27°C+ room readings, >2°C divergence from Honeywell,
   humidity >=75%, >=8 percentage-point humidity rise in 15 minutes,
   >=0.65°C temperature rise in 10 minutes.
4. After shower-like events, quarantine at least 30 minutes, restarting
   the warm-up sequence. Unknown/invalid readings are never silently imputed.
5. Sensor epoch is `bathroom-precision-v1`: do not mix with historic
   Honeywell whole-degree series.
6. Output is **advisory only**. No Honeywell heating demand/setpoint changes.

**Not yet wired to live HA-General.** A new advisory model/store, HA
coordinator integration, restart window and root-owned approved JNS
deployment are still needed; adding this Python file to the GitHub
development branch does not change a live HA entity. The secure
v0.3.5 privileged handler remains uninstalled and live API admin-token
preflight is not authorised. Do not bypass these gates with arbitrary
`.storage` modifications.

## Three permanent Zigbee sensors

Prefer three identical Zigbee2MQTT-supported SONOFF SNZB-02P battery-powered
temperature/humidity sensors for like-for-like calibration and readings.

1. `House Thermostat Precision` — beside Honeywell but not touching it,
   roughly 1.2–1.5m high, away from radiators/direct sun. The future
   canonical room-temperature learning source.
2. `Upstairs Landing Temperature` — normal circulation area at similar
   height, not above a radiator or bathroom door, to learn upstairs lag
   and stratification.
3. `Living Room Temperature` — at occupant height in the main living
   zone, outside direct fire radiation and away from the chimney breast.
   Compare living-room rise vs thermostat/upstairs for a fireplace
   heat-contribution flag; do NOT use it to directly change thermostat
   duty before independent validation. A fourth sensor may be added near
   (but safely distanced from) the fireplace if a thermal gradient is desired.

Use the Honeywell control sensor until the new house-reference series has
calibrated and shown its representativeness. Log each new Zigbee IEEE and
registered entity ID in the commissioning inventory, don't assume
predefined entity IDs. New sensor comparisons must preserve original
Honeywell auth, setpoints and samples.
