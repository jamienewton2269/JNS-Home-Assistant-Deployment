#!/usr/bin/env python3
"""VM906 cold-start gate, read-only, via approved Node C -> Node A SSH."""
import base64,json,shlex,subprocess
REMOTE=r'''
import os,json,re,subprocess,socket
from pathlib import Path
def run(a,t=12):
 try:return subprocess.run(a,capture_output=True,text=True,timeout=t)
 except (OSError,subprocess.TimeoutExpired):return None
out={"node":"nodea","root_authorised":os.geteuid()==0,"read_only":True}
if os.uname().nodename.split(".")[0]!="nodea" or not out["root_authorised"]:raise SystemExit(1)
f=run(["free","-m"])
if f and f.returncode==0:
 for row in f.stdout.splitlines():
  p=row.split()
  if p and p[0]=="Mem:" and len(p)>=7:
   out["ram_total_MiB"]=int(p[1]);out["ram_available_MiB"]=int(p[6])
  if p and p[0]=="Swap:" and len(p)>=4:
   out["swap_total_MiB"]=int(p[1]);out["swap_used_MiB"]=int(p[2])
p=run(["qm","status","906"])
out["vm906_status"]=p.stdout.strip().removeprefix("status: ") if p and p.returncode==0 else "unknown"
c=run(["qm","config","906"])
if c and c.returncode==0:
 out["vm906_agent_configured"]=bool(re.search(r"^agent:\s*(?:enabled=)?1(?:,|$)",c.stdout,re.M))
 out["vm906_onboot_disabled"]=bool(re.search(r"^onboot:\s*0\s*$",c.stdout,re.M))
 out["vm906_locked"]=bool(re.search(r"^lock:",c.stdout,re.M))
p=run(["qm","agent","906","ping"],8)
out["vm906_qga_ping"]=bool(p and p.returncode==0)
try:
 with socket.create_connection(("ha-security.home.arpa",8123),timeout=5):
  out["ha_security_port_8123_reachable"]=True
except OSError:out["ha_security_port_8123_reachable"]=False
p=run(["zfs","list","-Hp","-o","available","vmdata"],12)
if p and p.returncode==0:
 try:out["vmdata_free_GiB"]=round(int(p.stdout.strip())/1073741824,2)
 except ValueError:pass
out["backup_verified_in_this_workflow"]=False
try:
 with socket.create_connection(("ha-security.home.arpa",80),timeout=5):
  out["ha_security_port_80_reachable"]=True
except OSError:out["ha_security_port_80_reachable"]=False
print("JNS_VM906_COLDSTART_READINESS="+json.dumps(out,sort_keys=True))
'''
src=base64.b64encode(REMOTE.encode()).decode()
cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5","nodea",
     shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+src+"'))"])]
r=subprocess.run(cmd,capture_output=True,text=True,timeout=55)
if r.returncode:raise SystemExit("JNS_VM906_COLDSTART_GATE_UNAVAILABLE")
for x in r.stdout.splitlines():
 if x.startswith("JNS_VM906_COLDSTART_READINESS="):print(x,flush=True)
