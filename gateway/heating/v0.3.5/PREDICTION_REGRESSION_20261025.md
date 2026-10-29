# Heating prediction unavailable — verified diagnosis, 25 October 2026

**Scope:** `HA-General` VM905, custom integration `jns_heating_zones`.
**Status:** cause verified read-only, no production changes made.

## Symptom
Dashboard `testing-dashboard/house-temperature` shows:
- Indoor 20.0°C, target 20.0°C, heating call off / action idle.
- `sensor.lyric_home_heating_thermal_learning`:
  `Learned values outside safe bounds`.
- `sensor.lyric_home_heating_projected_temperature_in_60_minutes`: unknown.
- Both 24-hour and 7-day historical panels have few indoor temperature
  transitions (whole 20–21°C, not fractional temperature variation).

## Evidence
VM905 read-only diagnostic:
[GitHub Actions run 40191959504](https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40191959504).

At time of audit:
- Installed version: **0.3.4**, thermal.py SHA256
  `44054f9172e3c9e2e944240b5369b49d9735d8349fb7ca2dd0a2a782d7c8a4f8`.
- Learned Store contained **524 saved samples**; newest sample 1.7 minutes old.
- Indoor histogram: 20.0°C (294), 21.0°C (230): **only 2 distinct levels**.
- Heating ON/idle sample split: 127 / 397.
- Legacy v0.3.4 accepted 277 intervals but returned fitted thermal
  coefficients `loss_per_hour=0`, `heat_gain_c_per_hour=0`,
  `drift_c_per_hour=0`. These violate original physical plausibility
  requirements, and `ready=false`. Forecast is deliberately withheld.
- Staged v0.3.5 on the same unchanged samples found **51 independent windows**,
  17 heated, 22 idle, but just **3 nonzero indoor-delta windows** and
  two room temperature levels. Candidate also returns
  `ready=false`, reason `Learning: insufficient temperature variation`.
- `weather.ha_general` is available, and the v2 forecast-retry marker
  is present in coordinator.py. Weather availability is not the limiting
  condition for the current `None` projection.
- No change to stored samples by this audit.

## Engineering implication

The problem is *statistical identifiability*, not lack of scheduler ticks:
a quantized whole-degree thermostat cannot produce enough meaningful
short-interval room temperature deltas while holding 20°C.
The original model's five-minute regression was invalidated by these
readings. Longer independent windows correctly prevent spurious fitting,
but **deploying v0.3.5 alone does not restore immediate numerical forecasts**.

The previous apparent working predictions might have used different
underlying data, a pre-fit/default estimate, or a short initial
regression that happened to satisfy gates. This audit **cannot verify**
their accuracy; avoid claiming they were wrong or that a 0.3.5 rollout
alone fixes the result.

## Next safe steps

1. Examine HA-General registered indoor room temperature sensors and their
   historic resolution. Prefer an **existing co-located 0.1°C sensor** if
   available; verify position matches the heated zone before selecting it.
   Leave the Honeywell climate entity in charge of actual heating control.
2. If no suitable sensor is present, design an explicitly labeled,
   uncertainty-bounded *provisional* estimate that is distinct from a
   validated learned prediction; do not silently publish a fabricated
   precise 60-minute forecast.
3. Preserve learning history and separate epochs when changing
   indoor/outdoor sensor sources. A sensor-source swap must not combine
   old 20/21°C inputs with new fractional readings as one homogeneous model.
4. The already staged v0.3.5 learner is advisory-only and has private
   backups, but production still runs 0.3.4; custom Python source needs
   guarded HA Core restart, approved authentication and verified rollback.
5. Improve the dashboard to display independent statuses
   (live thermostat control, weather forecast, thermal model calibration,
   provisionally estimated trend, model confidence).
6. Never change Honeywell setpoints, heating safety automation, HA900,
   Plant Manager VM903, or apply synthetic coefficients without approval.

## References
- `gateway/heating/v0.3.5/thermal.py`
- `gateway/heating/v0.3.5/diagnose_prediction_gap.py`
- `gateway/heating/v0.3.5/RELEASE_OPERATOR.md`
