#!/usr/bin/env python3
"""Read-only Natural Automation API health diagnostics without private content."""
import base64,json,shlex,subprocess
PROBE=r'''
import json
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
info={"audit":"natural-automation-api-v1"}
def sysd(property):
 try:
  p=subprocess.run(["systemctl","show","natural-automation.service","--property="+property,"--value"],
                   capture_output=True,text=True,timeout=5)
  return p.stdout.strip()[:60] if p.returncode==0 else "unavailable"
 except Exception:return "unavailable"
for prop in ["ActiveState","SubState","Result","ExecMainStatus","NRestarts","UnitFileState"]:
 info[prop]=sysd(prop)
try:
 with socket.create_connection(("127.0.0.1",8099),timeout=2):info["tcp_8099"]=True
except OSError:info["tcp_8099"]=False
for suffix,label in [("/api/status","api_status"),("/","root")]:
 req=urllib.request.Request("http://127.0.0.1:8099"+suffix,method="GET")
 try:
  with urllib.request.urlopen(req,timeout=5) as res:
   data=res.read(65536)
   info[label]={"http":res.status,"body_bytes":len(data),"content_type":res.headers.get("Content-Type","").split(";",1)[0]}
   if label=="api_status":
    try:
     obj=json.loads(data)
     info[label]["json_valid"]=isinstance(obj,dict)
     info[label]["ok_field_true"]=obj.get("ok") is True
     info[label]["apply_enabled"]=obj.get("apply_enabled")
     info[label]["target_role"]=(obj.get("target") or {}).get("role") if isinstance(obj.get("target"),dict) else None
    except (ValueError,TypeError):info[label]["json_valid"]=False
 except urllib.error.HTTPError as e:
  info[label]={"http":e.code}
 except urllib.error.URLError as e:
  info[label]={"error_class":type(e.reason).__name__}
 except (TimeoutError,OSError,ValueError) as e:
  info[label]={"error_class":type(e).__name__}
print("NATURAL_API_DIAGNOSTIC_JSON="+json.dumps(info,sort_keys=True))
'''
encoded=base64.b64encode(PROBE.encode()).decode()
cmd=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=5","-o","StrictHostKeyChecking=yes","nodeb",
     shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+encoded+"'))"])]
try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=24)
except (OSError,subprocess.TimeoutExpired):print("NATURAL_API_DIAGNOSTIC_BLOCKED=transport_timeout");raise SystemExit(1)
if p.returncode:print("NATURAL_API_DIAGNOSTIC_BLOCKED=ssh_or_guest_probe_failed");raise SystemExit(1)
lines=[x for x in p.stdout.splitlines() if x.startswith("NATURAL_API_DIAGNOSTIC_JSON=")]
if not lines:print("NATURAL_API_DIAGNOSTIC_BLOCKED=missing_payload");raise SystemExit(1)
print(lines[-1])
