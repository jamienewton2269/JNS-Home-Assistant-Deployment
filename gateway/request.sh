#!/usr/bin/env bash
set -euo pipefail
ssh nodeb '
  cp -a /opt/natural-automation/steward/writer.py /opt/natural-automation/steward/writer.py.pre-apply-button
  sed -i "s#/config/natural_automation.yaml#/config/automations.yaml#g" /opt/natural-automation/steward/writer.py
  python3 -m py_compile /opt/natural-automation/steward/writer.py
  grep -n "automations.yaml" /opt/natural-automation/steward/writer.py
'
