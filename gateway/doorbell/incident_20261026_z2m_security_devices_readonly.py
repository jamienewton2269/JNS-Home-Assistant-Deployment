#!/usr/bin/env python3
"""Read-only Zigbee2MQTT device freshness/error survey via Node B's CT214.

Only known target security lights, no secret keys/payloads/log bodies.
Never publish MQTT / actuate relays.
"""
import base64,json,re,shlex,subprocess
TARGETS=("0x84fd27fffe9ce438","0xa4c138bda6ec8ea0","0x847127fffe28965b")
INNER=r'''
import json,re,subprocess,os,datetime
from pathlib import Path
OUT={"read_only":True}
TARGETS={"0x84fd27fffe9ce438","0xa4c138bda6ec8ea0","0x847127fffe28965b"}
ROOTS=[Path("/opt/zigbee2mqtt/data"),Path("/var/lib/zigbee2mqtt"),Path("/data"),
       Path("/opt/zigbee2mqtt"),Path("/usr/share/zigbee2mqtt/data")]
def locate(name):
 for r in ROOTS:
  p=r/name
  try:
   if p.is_file() and not p.is_symlink() and p.stat().st_size<12*1024*1024:return p
  except OSError:pass
 return None
db=locate("database.db")
outrows=[]
if db:
 try:
  for l in db.read_text(errors="replace").splitlines():
   try:j=json.loads(l)
   except ValueError:continue
   ieee=str(j.get("ieeeAddr","")).lower()
   if ieee in TARGETS:
    outrows.append({"device_ieee":ieee,"type":str(j.get("type",""))[:18],
      "interviewCompleted":j.get("interviewCompleted"),
      "network_address_exists":bool(j.get("nwkAddr") is not None)})
 except OSError:pass
OUT["database_device_rows"]=outrows
# Never print YAML itself; identify friendly names via narrow regex but no authorization.
config=locate("configuration.yaml")
names={}
if config:
 try:
  txt=config.read_text(errors="replace")
  # Match only mappings for 3 explicitly known IEEE target keys
  for ieee in TARGETS:
   m=re.search(r"(?im)^\s*['\"]?"+re.escape(ieee)+r"['\"]?\s*:\s*(.*?)\n(?=\s*(?:['\"]?0x[0-9a-f]{16}['\"]?\s*:|\w+\s*:)|\Z)",txt,re.S)
   if m:
    z=re.search(r"(?im)^\s+friendly_name:\s*['\"]?([A-Za-z0-9 _-]{1,85})",m.group(1))
    if z:names[ieee]=z.group(1).strip()
 except OSError:pass
OUT["friendly_names"]=names
state=locate("state.json")
if state:
 try:
  j=json.loads(state.read_text())
  if isinstance(j,dict):
   rows=[]
   for key,val in j.items():
    candidate=key.lower()
    if candidate in TARGETS or candidate in [x.lower() for x in names.values()]:
     if isinstance(val,dict):
      clean={k:val[k] for k in ("state","linkquality","last_seen","availability","online") if k in val and isinstance(val[k],(str,int,float,bool))}
      rows.append({"name":key[:85],"values":clean})
   OUT["matching_state"]=rows
   OUT["state_device_total"]=len(j)
 except (OSError,ValueError):OUT["state_status"]="unavailable"
# Look for Z2M errors only, grouped by message cause; do not print unrestricted log text.
try:
 q=subprocess.run(["journalctl","-u","zigbee2mqtt","--since","2026-10-26 18:00:00",
 "--no-pager","--output=short-iso","-n","2000"],
 capture_output=True,text=True,timeout=12)
 if q.returncode==0:
  lines=q.stdout.splitlines()
  OUT["journal_readable"]=True
  reports=[]
  for row in lines:
   if any(ieee in row.lower() for ieee in TARGETS) or re.search(r"(?i)security.light|front.door.exterior.light",row):
    level=("error" if re.search(r"(?i)\berror\b|failed|timeout|no ack|no response",row) else
       "warning" if re.search(r"(?i)warn|unavailable|offline",row) else "info")
    # Print only timestamp/severity and approved error terms; not the message payload
    cause=next((k for k in ("timeout","no response","failed","not supported","unavailable","offline","interview") if k in row.lower()),"event")
    reports.append({"time":row[:24],"severity":level,"cause":cause,
     "devices":[x for x in TARGETS if x in row.lower()]})
  OUT["target_journal"]=reports[-25:]
  OUT["journal_lines"]=len(lines)
except (OSError,subprocess.TimeoutExpired):OUT["journal_readable"]=False
print("JNS_Z2M_SECURITY_DEVICES="+json.dumps(OUT,sort_keys=True,default=str))
'''
REMOTE=r'''
import os,base64,shlex,subprocess,json
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(73)
CODE=__CODE__
c=subprocess.run(["pct","status","214"],capture_output=True,text=True,timeout=11)
if c.returncode or c.stdout.strip()!="status: running":
 print("JNS_Z2M_SECURITY_DEVICES="+json.dumps({"ct214_running":False}));raise SystemExit(0)
p=subprocess.run(["pct","exec","214","--","python3","-c",
 "exec(__import__('base64').b64decode('"+CODE+"'))"],capture_output=True,text=True,timeout=48)
if p.returncode:
 print("JNS_Z2M_SECURITY_DEVICES="+json.dumps({"ct214_running":True,"inside_probe_status":"not_available"}))
else:
 for line in p.stdout.splitlines():
  if line.startswith("JNS_Z2M_SECURITY_DEVICES="):print(line)
'''
remote=REMOTE.replace("__CODE__",repr(base64.b64encode(INNER.encode()).decode()))
enc=base64.b64encode(remote.encode()).decode()
cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5","nodeb",
     shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+enc+"'))"])]
try:r=subprocess.run(cmd,capture_output=True,text=True,timeout=80)
except (OSError,subprocess.TimeoutExpired):
 print("JNS_Z2M_SURVEY_BLOCKED=timeout");raise SystemExit(1)
for row in r.stdout.splitlines():
 if row.startswith("JNS_Z2M_SECURITY_DEVICES="):print(row,flush=True)
if r.returncode:print("JNS_Z2M_SURVEY_BLOCKED=remote_unavailable");raise SystemExit(1)
