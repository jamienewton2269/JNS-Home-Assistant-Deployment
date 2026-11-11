# JNS Health Intelligence — staged dashboard v0.1

**Status: staged; NOT deployed or connected to the phones.**

## Scope
One existing Home Assistant instance (HA-General). Do not deploy a second HAOS VM. Health project must not modify existing heating, lighting, security or plant packages. The future live backup project is separate.

## Privacy
This repository is public. NEVER commit health measurements, device IDs, personal identifiers, tokens, phone numbers, exports, recorder database files or private configuration. Use neutral 'Person A' and 'Person B' placeholders in source. No cloud telemetry added.

Home Assistant dashboards are not per-user access-control boundaries: require_admin restricts the dashboard navigation, but administrators, recorder/database access and HA APIs can still access source entities. Agree explicit consent with each participant and restrict all administrator accounts. Avoid exporting health entity history to general MQTT, InfluxDB, Prometheus, public dashboards or other services without separate review.

## Required prerequisites
1. Each person voluntarily enables selected Health Connect permissions and the corresponding Companion App sensors on their own Android phone.
2. Verify actual HA entity IDs and whether data is truly coming from each watch, Google Health or Health Connect.
3. Record units, timestamp freshness, frequency and duplicate sources. Never use a value just because its HA entity remains 'available'.
4. Secure local admin access and verify recorder inclusion/retention; do not globally alter recorder excludes or purge old histories.
5. Make a rollback plan using the existing signed deployment platform.

## Files / proposed target
- `dashboards/jns_health_intelligence.yaml` -> `/config/dashboards/jns_health_intelligence.yaml`
- Add to the EXISTING `lovelace:` mapping in `/config/configuration.yaml` after checking for an existing `lovelace:` mapping:

```yaml
lovelace:
  dashboards:
    jns-health:
      mode: yaml
      filename: dashboards/jns_health_intelligence.yaml
      title: JNS Health Intelligence
      icon: mdi:heart-pulse
      require_admin: true
      show_in_sidebar: true
```

IMPORTANT: merge with existing Lovelace settings, don't add a duplicate root key or overwrite existing dashboards. `require_admin` is an initial precaution, NOT isolation. The included dashboard uses deliberately nonexistent placeholder entities, so it must not be enabled until sensors are mapped and validated. Where a metric isn't supplied, remove the card; never simulate a reading.

## Plan for next build
- Inventory entity IDs using a privileged HA inventory operation, emitting ONLY anonymized category/presence/units; never commit raw private identifiers.
- Add per-sensor validated mapping in a private file on HA-General, separate from public GitHub.
- Read state freshness from source observation timestamps when supported; device/app sync may be delayed. Mark unknown/stale instead of treating HA updated time as measurement time.
- Validate temperature/pressure/glucose units and chart axes; do not mix unit types, time semantics, or simultaneous readings.
- Build advanced professional styling using native cards first; no untrusted remote JS.
- Test config, stage a signed transactional deployment, verify no impact on other automations, then activate only with device consent and actual sensor mappings.
- Keep any downtime/failover features in the separate backup project.
