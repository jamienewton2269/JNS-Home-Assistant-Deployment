# JNS 10:00 comfort deadline — adaptive warm-up release candidate

Status: **DEVELOPMENT ONLY — NOT DEPLOYED to VM905** (29 Oct 2026).

## Existing behaviour and user requirement

- Overnight thermostat setpoint 18°C. Home comfort target 21°C **reached by 10:00**.
- The existing 5-minute predictive controller applies 21°C by 10:00 minus its estimated preheat lead (with 10-minute margin).
- Model v0.3.4 is not ready because the thermostat reports only coarse 1°C values. The scheduler therefore uses the 120-minute fallback.
- The separately staged precision bathroom model v0.3.6 is *advisory only*. It **must not** become an implicit thermostat control input.
- Keep alarm exclusions and manual override unchanged. Home security VM906 remains independent until security handover passes.

## Candidate change

Adds measured **morning warm-up timing calibration**, not a second physics learner. When the existing schedule explicitly raises a below-21°C Honeywell thermostat target to 21°C in the 04:00–10:00 window, record room temperature/time and watch for a genuinely observed heating call. When the existing house temperature reaches 20.8–21.0°C and the full run is plausible, record elapsed minutes per degree. Do not learn from manual overrides, alarm away, unknown state, interrupted thermostat targets, or runs with no observed heat.

The ready JNS thermal model takes priority, otherwise use this empirical rate only after **three complete accepted morning cycles**; before then retain the 120-minute fallback. Cap the calculated lead to 360 minutes; retain the existing +10-minute scheduling margin and the 10:00 hard time boundary. The observer has **no thermostat output actions**. A run that does not reach target is discarded rather than creating a fabricated learning sample. High-resolution bathroom signals remain separate until their cross-room accuracy is proven.

## Release gates (must be completed, not bypassed)

1. Finish HA-Security VM906 → VM905 ownership transfer and physical handover, then obtain user-approved quiet maintenance period. No heating package deploy during ongoing cutover.
2. Validate this branch's offline YAML/Jinja unit tests **and** run Home Assistant config check on a private, non-live copy. Check full package against exact VM905 live YAML, helpers and automation entities; assess memory and exact path.
3. Back up VM905 heating package, dashboard, actual helper states, relevant HA configuration and snapshots; record checksums. No bulk copy from HA900.
4. Establish current live API authentication and safe heating-idle state, followed by approved fixed-purpose root-installed Node C gateway transaction with atomic rollback. Never use a generic remote command or publicly triggered restart.
5. Install one replacement `/config/packages/jns_heating_predictive_schedule.yaml` only with guard and checks, verify no duplicate automations, HA config check and safe Core restart **only if required**. Preserve existing bedtime automations and manual override.
6. Verify schedule trace, alarm gating, 18°C overnight, 21°C by 10:00, observation timing, heating-call validation, helper restore, and dashboard explanation for at least three genuine mornings. Confirm predictions improve relative to 120-minute fallback.
7. Deploy v0.3.6 bathroom learner by its **separate pre-existing six-file root-approved** release only when ready. Never pretend this schedule candidate activates that module. If no safe runner/admin-token gate, **STOP**.

## Limitations

1-degree Honeywell measurements mean learning cannot distinguish small changes. No new samples until valid future heating cycles complete. The empirical estimate is not guaranteed to hit exactly 10:00 when outside conditions change. Install neither an unvalidated predictive output nor a fabricated lead time. Fall back safely if confidence declines.

**This GitHub branch is a proposal only. None of the candidate YAML, its helper entities or thermostat controls has been installed or restarted on HA-General.**
