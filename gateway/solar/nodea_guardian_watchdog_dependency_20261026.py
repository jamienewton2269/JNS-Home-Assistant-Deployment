#!/usr/bin/env python3
"""Read-only Node A CT118 maintenance watchdog dependency gate.
Also confirms HA-Security QGA and live guest following recovery.
"""
import base64,subprocess,shlex,json
INNER=r'''
import json,os,re,subprocess
def run(args,seconds=12):
 try:return subprocess.run(args,capture_output=True,text=True,timeout=seconds)
 except (OSError,subprocess.TimeoutExpired):return None
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":raise SystemExit(75)
out={"node":"nodea","read_only":True}
for c in (118,116,247):
 p=run(["pct","status",str(c)])
 out["ct"+str(c)+"_state"]=p.stdout.strip().removeprefix("status: ") if p and p.returncode==0 else "unavailable"
if out["ct118_state"]=="running":
 for svc in ("jns-watchdog.service","consul.service","lunar.service"):
  p=run(["pct","exec","118","--","systemctl","is-active",svc],9)
  out["maintenance_"+svc+"_active"]=p.stdout.strip() if p and p.stdout.strip() in ("active","inactive","failed","activating","unknown") else "unavailable"
 p=run(["pct","exec","118","--","systemctl","cat","jns-watchdog.service"],12)
 out["watchdog_unit_readable"]=bool(p and p.returncode==0)
 if p and p.returncode==0:
  s=p.stdout
  out["unit_mentions_guardian_or_consul"]=bool(re.search(r"guardian|consul|lunar",s,re.I))
  out["unit_mentions_legacy_ha"]=bool(re.search(r"homeassistant-recovery|homeassistant-standby|ha900|ha901|\b900\b|\b901\b",s,re.I))
  out["unit_mentions_current_ha"]=bool(re.search(r"ha-primary|ha-general|ha-security|vm902|vm905|vm906",s,re.I))
p=run(["qm","status","906"])
out["vm906_state"]=p.stdout.strip().removeprefix("status: ") if p and p.returncode==0 else "unavailable"
p=run(["qm","agent","906","ping"],9)
out["vm906_qga_responds"]=bool(p and p.returncode==0)
print("JNS_NODEA_WATCHDOG_GATE="+json.dumps(out,sort_keys=True))
'''
enc=base64.b64encode(INNER.encode()).decode()
argv=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5","nodea",
      shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+enc+"'))"])]
try:p=subprocess.run(argv,capture_output=True,text=True,timeout=100)
except (OSError,subprocess.TimeoutExpired):
 print("JNS_NODEA_WATCHDOG_GATE_BLOCKED=remote_timeout");raise SystemExit(1)
if p.returncode:
 print("JNS_NODEA_WATCHDOG_GATE_BLOCKED=remote_code_"+str(p.returncode));raise SystemExit(1)
for line in p.stdout.splitlines():
 if line.startswith("JNS_NODEA_WATCHDOG_GATE="):print(line,flush=True)
