# HA-General boiler demand runtime monitor

Observation only: reads `climate.thermostat_thermostat.attributes.hvac_action == heating` from Honeywell Lyric on HA-General VM905. It never changes thermostat mode, setpoint, schedules, authentication or heating control.

## Dashboard
[Boiler Usage](http://ha-general.home.arpa/jns-boiler/usage) appears in HA-General's sidebar.

- Current call for heat and monitoring availability.
- Today's and this calendar month's hours.
- Previous day and previous month.
- 24-hour activity timeline, 30-day daily runtime and monthly history.
- Persistent cumulative runtime feeds daily/monthly Utility Meters; midnight and month boundaries follow Home Assistant's configured timezone.
- Left-hand integration prevents the new ON value being applied backwards over the preceding OFF interval. One-minute maximum sub-interval updates totals during a steady heating call.
- Long-term statistics use the cumulative hours sensor; monthly totals do not depend on retaining a full month of raw recorder history.

## Interpretation
This measures Lyric's reported **space-heating demand**, not confirmed burner firing, gas volume, kWh or cost. Thermostat polling limits timing accuracy. Boiler cycling/modulation and domestic hot water are not directly observed.
Monitoring starts at installation; the first day/month are partial. No historical totals are invented. Unknown/unavailable Lyric periods contribute no assumed runtime and are shown in the availability indicator/timeline. Home Assistant downtime is not reconstructed.

## Files and activation
- `/config/packages/jns_boiler_monitor.yaml`
- `/config/dashboards/jns_boiler_monitor.yaml`
- Additive-only install rejects pre-existing target files or entity conflicts.
- A manifest in `/config/.jns-backups/boiler-runtime-<run-id>/manifest.json` records checksums and that both targets were previously absent.
- Existing Node C runner -> trusted Node B SSH -> VM905 guest agent.
- Native Core configuration check must pass before one guarded Core restart.
- Configuration-check failure removes only the exact files created by this transaction. Concurrent edits are never overwritten.
- Restart status must be confirmed; no blind retries.
- Postactivation checks require registered, recorded, numeric hour sensors with long-term-statistics state classes.
- Review matching GitHub workflow and `results/deploy-<run-id>.txt` before claiming activation.
