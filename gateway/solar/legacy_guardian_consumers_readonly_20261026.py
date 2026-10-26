#!/usr/bin/env python3
"""Read-only Guardian/Lunar retirement dependency audit of independent PVE hosts.
Uses the established Node C runner -> nodea/nodeb authorised SSH path only.
Does not touch guests or print service configuration, secrets or addresses.
"""
import base64,json,shlex,subprocess
R=r'''
import os,re,json,subprocess
from pathlib import Path
def run(cmd,timeout=10):
 try:return subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
node=os.uname().nodename.split(".")[0]
if node not in ("nodea","nodeb") or os.geteuid()!=0:raise SystemExit(78)
guardian={"nodea":116,"nodeb":115}[node]
out={"node":node,"guardian_ct":guardian,"read_only":True}
a=run(["pct","status",str(guardian)])
out["guardian_state"]=a.stdout.strip().removeprefix("status: ") if a and a.returncode==0 else "unavailable"
a=run(["pvesh","get",f"/nodes/{node}/lxc/{guardian}/status/current","--output-format","json"])
if a and a.returncode==0:
 try:
  j=json.loads(a.stdout)
  for v in ("mem","maxmem"):
   if isinstance(j.get(v),(int,float)):out["guardian_"+v+"_MiB"]=round(j[v]/1048576,1)
 except ValueError:pass
# Only filenames of host-level service unit references, never file bodies.
paths=(Path("/etc/systemd/system"),Path("/usr/lib/systemd/system"),Path("/lib/systemd/system"))
names={}
for p in paths:
 if p.is_dir():
  for f in p.rglob("*"):
   if not f.is_file() or f.is_symlink() or f.suffix not in (".service",".timer",".socket"):
    continue
   try:
    if f.stat().st_size>131072:continue
    s=f.read_text(errors="replace")
   except (OSError,PermissionError):continue
   hits=[x for x in ("consul","guardian","lunar") if re.search(r"\b"+x+r"\b",s,re.I)]
   if hits:names[f.name]=sorted(hits)
out["host_unit_references"]=names
# Count client TCP connections to traditional Consul ports; no addresses/identity output.
s=run(["ss","-H","-tn","state","established"])
if s and s.returncode==0:
 lines=s.stdout.splitlines()
 out["consul_port_active_connections"]=sum(bool(re.search(r":(?:8500|8300|8301|8302)\b",x)) for x in lines)
 else_placeholder=0
# Child services in Guardian, no additional configuration disclosed.
if out["guardian_state"]=="running":
 for service in ("consul","lunar"):
  x=run(["pct","exec",str(guardian),"--","systemctl","is-active",service])
  out[service+"_state"]=x.stdout.strip() if x and x.stdout.strip() in ("active","activating","inactive","failed","unknown") else "unavailable"
print("JNS_GUARDIAN_DEPS="+json.dumps(out,sort_keys=True))
'''
R=R.replace(" else_placeholder=0\n","")
def probe(host):
 token=base64.b64encode(R.encode()).decode()
 cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",host,
      shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+token+"'))"])]
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
 except (OSError,subprocess.TimeoutExpired):return {"access":"unavailable"}
 if p.returncode:return {"access":"remote_not_permitted_or_failed"}
 rows=[x.split("=",1)[1] for x in p.stdout.splitlines() if x.startswith("JNS_GUARDIAN_DEPS=")]
 try:return json.loads(rows[-1])
 except (ValueError,IndexError):return {"access":"not_returned"}
for node in ("nodea","nodeb"):
 print(node.upper()+"="+json.dumps(probe(node),sort_keys=True),flush=True)
print("JNS_GUARDIAN_DEPS_AUDIT_READONLY=yes")
