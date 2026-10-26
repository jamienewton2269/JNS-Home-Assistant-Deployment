#!/usr/bin/env python3
"""Classify remaining legacy Guardian unit dependencies, no writes."""
import base64,json,shlex,subprocess
INNER=r'''
import os,re,json,subprocess
from pathlib import Path
H=os.uname().nodename.split(".")[0]
if H not in ("nodea","nodeb") or os.geteuid()!=0:raise SystemExit(77)
d={"host":H,"read_only":True}
names=("jns-cluster-proxy.service","jns-ha-guardian-probe.service",
"jns-ha-guardian-probe.timer","lunar-discovery-export.service",
"lunar-discovery-export.timer")
for name in names:
 p=Path("/etc/systemd/system")/name
 data=""
 try:
  if p.is_file() and not p.is_symlink():data=p.read_text(errors="replace")
 except OSError:pass
 match=re.search(r"(?m)^ExecStart\s*=\s*([^\s]+)",data)
 command=match.group(1) if match else ""
 d[name]={
 "unit_file_exists":bool(data),
 "entrypoint_category":("systemd" if "systemctl" in command else
                         "shell" if command.endswith(("sh","bash")) else
                         "python" if "python" in command else
                         "binary" if command else "unknown"),
 "mentions_legacy_ha900":bool(re.search(r"\b(?:900|901|homeassistant-recovery|homeassistant-standby)\b",data,re.I)),
 "mentions_consul":bool(re.search(r"consul|guardian",data,re.I)),
 "mentions_lunar":bool(re.search(r"lunar",data,re.I)),
 "mentions_dns":bool(re.search(r"sherrif|sheriff|dnsmasq|radvd",data,re.I)),
 "mentions_mqtt_or_zigbee":bool(re.search(r"mosquitto|mqtt|zigbee",data,re.I)),
 "mentions_current_ha_roles":bool(re.search(r"\b(?:902|905|906|ha-primary|ha-general|ha-security)\b",data,re.I))
 }
# aggregate file matches without disclosing private file contents
sections={"systemd":"/etc/systemd/system","automation":"/opt/natural-automation"}
for label,dirname in sections.items():
 base=Path(dirname)
 count=0; matched=[]; automation_files=[]
 if base.is_dir():
  for p in base.rglob("*"):
   try:
    if not p.is_file() or p.is_symlink() or p.stat().st_size>262144:continue
    if p.suffix.lower() not in (".service",".timer",".sh",".py",".yaml",".json",".conf",".yml"):continue
    value=p.read_text(errors="replace")
    if re.search(r"\b(?:consul|guardian|lunar)\b",value,re.I):
     count+=1
     if label=="systemd" and re.fullmatch(r"[a-zA-Z0-9_.@-]+",p.name):matched.append(p.name)
     if label=="automation":
      relative=str(p.relative_to(base))
      if re.fullmatch(r"[A-Za-z0-9_./-]{1,160}",relative):
       automation_files.append({"path":relative,
         "guardian":bool(re.search(r"guardian",value,re.I)),
         "consul":bool(re.search(r"consul",value,re.I)),
         "lunar":bool(re.search(r"lunar",value,re.I)),
         "active_code":p.suffix in (".py",".service",".sh")})
   except (OSError,PermissionError):continue
 d[label+"_legacy_reference_file_count"]=count
 if label=="systemd":d["legacy_systemd_file_names"]=sorted(set(matched))[:70]
 if label=="automation":d["legacy_automation_files"]=automation_files[:35]
# Inspect Node A's separate JNS maintenance watchdog without changing it.
if H=="nodea":
 p=run(["pct","status","118"],9)
 d["maintenance_ct118_status"]=p.stdout.strip().removeprefix("status: ") if p and p.returncode==0 else "unavailable"
 if d["maintenance_ct118_status"]=="running":
  q=run(["pct","exec","118","--","systemctl","is-active","jns-watchdog.service"],11)
  d["maintenance_watchdog_active"]=q.stdout.strip() if q and q.stdout.strip() in ("active","inactive","failed","activating") else "unavailable"
  # Read unit config only to emit booleans.
  q=run(["pct","exec","118","--","cat","/etc/systemd/system/jns-watchdog.service"],11)
  if q and q.returncode==0:
   d["maintenance_watchdog_unit_mentions_guardian"]=bool(re.search(r"guardian|consul|lunar",q.stdout,re.I))
   d["maintenance_watchdog_unit_mentions_legacy_ha"]=bool(re.search(r"ha900|ha901|homeassistant-recovery|homeassistant-standby",q.stdout,re.I))
   d["maintenance_watchdog_unit_mentions_current_ha"]=bool(re.search(r"ha-primary|ha-general|ha-security|vm902|vm905|vm906",q.stdout,re.I))
# No HA entity, secret, network target or sensitive command emitted.
print("JNS_GUARDIAN_SAFE="+json.dumps(d,sort_keys=True))
'''
def scan(host):
 payload=base64.b64encode(INNER.encode()).decode()
 cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",host,
 shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+payload+"'))"])]
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=110)
 except (OSError,subprocess.TimeoutExpired):return {"status":"timeout"}
 if p.returncode:return {"status":"ssh_or_probe_denied"}
 rows=[x.split("=",1)[1] for x in p.stdout.splitlines() if x.startswith("JNS_GUARDIAN_SAFE=")]
 try:return json.loads(rows[-1])
 except (ValueError,IndexError):return {"status":"bad_result"}
for host in ("nodea","nodeb"):
 print(host.upper()+"="+json.dumps(scan(host),sort_keys=True),flush=True)
print("JNS_READONLY=true")
