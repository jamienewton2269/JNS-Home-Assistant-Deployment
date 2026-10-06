#!/usr/bin/env bash
set -euo pipefail
ssh nodeb '
  grep -n "def analyse(text" /opt/natural-automation/natural_automation.py
  grep -n "result={\"action\":action" /opt/natural-automation/natural_automation.py
  grep -n "function show(d)" /opt/natural-automation/natural_automation.py
  grep -n "let activeRequest" /opt/natural-automation/natural_automation.py
'
