# JNS Health Intelligence — entity discovery
# No personal readings or entity IDs should be committed to this public repository.
#
# HA-General > Developer Tools > Template:
# Paste the following Jinja template and review locally.
# It lists only entity identifiers, domains and units, NOT values.
#
# {% for s in states.sensor
#     if 'health_connect' in s.entity_id
#     or 'heart_rate' in s.entity_id
#     or 'oxygen_saturation' in s.entity_id
#     or 'blood_pressure' in s.entity_id
#     or 'hrv' in s.entity_id
#     or 'sleep' in s.entity_id %}
# {{ s.entity_id }} | {{ s.attributes.get('unit_of_measurement', '-') }}
# {% endfor %}
#
# Caution: entity IDs and names may identify people or devices. Treat the
# output as private and do not paste it into a public GitHub issue.
#
# Verification:
# 1. COROS app has recent watch measurements.
# 2. Android Settings > Health Connect > Data and access shows actual stored
#    records, their timestamps and which app wrote them.
# 3. Companion App sensors enabled on both Android devices and configured
#    to send to HA-General.
# 4. Developer Tools > States: matching sensors exist and have fresh readings.
# 5. Compare numerical readings and observation timestamps with source apps;
#    HA last_updated alone is not a reliable observation timestamp.
# 6. Check duplicates (phone and watch) before forming derived statistics.
#
# COROS normal third-party sync may include workout data but not every
# daily measurement. Health Sync may bridge COROS -> Health Connect, if needed,
# but do not install unless inspection establishes missing data.
