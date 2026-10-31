# Health intelligence: mapping and observation integrity

Read-only HA-General `/api/states` discovery confirmed two Android Companion App sources with populated pulse, activity, sleep and calorie metrics. One source also publishes resting pulse, HRV, SpO2 and respiratory rate. This public repository intentionally does not record either person's name, phone entity prefix, medical values or raw device identifiers.

## Mapping policy
- Device-to-person ownership must be confirmed separately before assigning Person A/Person B.
- Keep actual phone sensor IDs in private HA-General configuration; map to generic `sensor.jns_health_person_a_*` and `sensor.jns_health_person_b_*` dashboard entities.
- Do not sum step counts from distinct daily and hardware pedometer sensors, or duplicate calories.
- Treat `unknown` / `unavailable` as missing, not 0. Do not produce fabricated observations.
- Source state `last_updated` is an HA state timestamp, not necessarily the wearable observation timestamp. Identify native observation timestamps if possible; explicitly display source and staleness.
- Sleep duration and sleep segments have different time semantics/units; validate before combining.
- Do not automatically raise clinical alarms or infer disease from one smartwatch reading. No emergency-use claim.
- Require permission/consent and retain health data in existing local recorder only; don't commit exports or link to unrelated dashboards.
- Check configuration in isolated staging and roll back atomically using existing deployment system.
