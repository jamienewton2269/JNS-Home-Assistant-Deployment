# JNS Heating Zones — thermal learning continuation (2026-10-24)

## Protected production baseline
- VM905 / HA-General is authoritative; HA900 is legacy reference only.
- Plant Manager VM903 is outside scope and must not be modified.
- Existing Lyric auth/config, historical samples, dashboards and heating control remain in place.
- Installed `jns_heating_zones` version: 0.3.4.
- Existing `JNS_FORECAST_RETRY_V2` in `coordinator.py` already provides 5-minute failure retries, 15-minute success refresh and 90-minute cached forecast validity. Do not reinstall.
- Heating forecasts use `weather.ha_general`; current dashboard target is `sensor.lyric_home_heating_projected_temperature_in_60_minutes`.

## Verified read-only evidence, 24 Oct 2026
The existing GitHub Actions Node C runner accessed VM905 through the established trusted Node B/QGA path. Latest audit: https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/40100014123

- 265 persisted samples across 23 hours in JNS heating zone storage; no samples were erased.
- 264 adjacent pairs: 146 accepted; 118 at 4.5 to <5 minutes rejected by strict minimum interval.
- Of accepted pairs, 41 strongly heated (duty >= 0.8) and 105 mostly unheated (duty <= 0.2).
- The temperature source yielded only two discrete levels (20.0 and 21.0 degrees C); all 146 currently accepted pairs had 0.0 degrees C change.
- Current fitted model parameters returned 0.0 for heat loss, heat gain, and background drift. Safe bounds correctly mark `ready=false`, reason `Learned values outside safe bounds`. The 60-minute prediction remains unavailable intentionally.
- Forecast acquisition and model readiness are separate concerns. Weather-forecast wording being "steady" does not imply that the thermal model has become ready.

## Candidate engineering work (not applied to VM905)
1. Preserve existing samples and introduce explicit learner diagnostics: collected samples, accepted intervals, interval-spacing rejects, non-zero indoor deltas, ON/OFF exposure and coefficient-validation reasons.
2. Tolerate 5-minute scheduler jitter (e.g. >=4.5 minute adjacent-pair window), without decreasing the requirements for 48 valid observations or changing physical plausibility bounds.
3. Make training robust to quantized room temperatures by supporting independently spaced 30–60 minute observation windows and time-weighted duty over each window, rather than only adjacent five-minute pairs with the end-point duty.
4. Guard against stale sensors, rapid thermostat state changes, long gaps, mixed modes, and overlapping-sample overconfidence. Require adequate nonzero indoor changes and thermal variation before declaring ready.
5. Backtest on a copied anonymised learning dataset and synthetic profiles: stable 1-degree readings, meaningful heat/cool transitions, thermostat rounding, update jitter, missing forecasts, staleness, heater ON/OFF, and rollback.
6. Keep predictive output **advisory** until test evidence validates model stability; never change the live heat demand based on an unvalidated model.
7. Improve dashboard wording to distinguish forecast state from model state and report "Learning: insufficient temperature variation" rather than a generic next-hour unavailable when appropriate.

## Guarded deployment conditions
- Preflight live component checksum, version, controller config, active sensor IDs and storage version.
- Back up entire `jns_heating_zones` directory, zone storage JSON and affected dashboard assets before writing.
- Validate import/compile and HA config; add invariant tests and runtime guardrails.
- Apply only to VM905 with JNS GitHub deployment gateway, journal change and verify sensors plus Lyric heating command path.
- Roll back code atomically and leave existing historical samples untouched if checks fail.
- Never patch HA900 or VM903 as part of this workstream.
