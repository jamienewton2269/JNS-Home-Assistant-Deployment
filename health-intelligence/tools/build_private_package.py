#!/usr/bin/env python3
"""Build private, source-mapped Home Assistant template package from verified phone prefixes.
No API calls or deployment. Generated data must stay off public GitHub.
Usage: python3 build_private_package.py --profile-a PREFIX --profile-b PREFIX --out /secure/path.yaml
"""
import argparse
from pathlib import Path

METRICS = {
    "heart_rate": ("bpm", "measurement", None),
    "resting_heart_rate": ("bpm", "measurement", None),
    "heart_rate_variability": ("ms", "measurement", None),
    "oxygen_saturation": ("%", "measurement", None),
    "respiratory_rate": ("breaths/min", "measurement", None),
    "daily_steps": ("steps", "total_increasing", None),
    "daily_distance": ("m", "total_increasing", "distance"),
    "sleep_duration": ("min", "measurement", "duration"),
    "total_calories_burned": ("kcal", "total_increasing", None),
}
# A readable state requires the source to exist and be numeric.
# source's last_updated is NOT a guaranteed original measurement timestamp.
p = argparse.ArgumentParser()
p.add_argument("--profile-a", required=True)
p.add_argument("--profile-b", required=True)
p.add_argument("--out", required=True)
a = p.parse_args()
for prefix in (a.profile_a, a.profile_b):
    if not prefix.replace("_", "").replace(".", "").isalnum() or not prefix.startswith("sensor."):
        p.error("Prefix must be an entity prefix such as sensor.example_phone")
lines = [
    "# Private HA-General template package. Generated locally; never commit.",
    "template:",
    "  - sensor:",
]
for label, prefix in (("a", a.profile_a), ("b", a.profile_b)):
    for suffix, (unit, state_class, devclass) in METRICS.items():
        source = prefix + "_" + suffix
        name = f"JNS Health Profile {label.upper()} {suffix.replace('_', ' ').title()}"
        uid = f"jns_health_profile_{label}_{suffix}"
        lines += [f"      - name: \"{name}\"", f"        unique_id: {uid}",
                  f"        unit_of_measurement: \"{unit}\"",
                  f"        state_class: {state_class}"]
        if devclass:
            lines.append(f"        device_class: {devclass}")
        lines += [
            f"        availability: \"{{{{ is_number(states('{source}')) }}}}\"",
            f"        state: \"{{{{ states('{source}') | float }}}}\"",
            "        attributes:",
            f"          source_entity: \"{source}\"",
            f"          source_ha_last_updated: \"{{{{ states['{source}'].last_updated.isoformat() if states.get('{source}') else 'unknown' }}}}\"",
        ]
dest = Path(a.out)
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text("\n".join(lines)+"\n", encoding="utf-8")
dest.chmod(0o600)
print(f"Generated {len(METRICS)*2} mapped sensors in {dest}")
print("NOT deployed. Validate actual sources and local YAML before installation.")
