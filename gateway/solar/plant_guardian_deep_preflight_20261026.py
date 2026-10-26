#!/usr/bin/env python3
"""Read-only Plant Manager cold-archive and Guardian quorum dependency gates."""
import base64,json,os,shlex,subprocess,re
from pathlib import Path
def run(argv,timeout=30):
    try:return subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):return None
REMOTE=r'''
import json,re,subprocess,os
from pathlib import Path
def r(argv,timeout=15):
 try:return subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
node=os.uname().nodename.split(".")[0]
if node not in ("nodea","nodeb") or os.geteuid()!=0:raise SystemExit(1)
out={"node":node}
if node=="nodeb":
 q=r(["qm","status","903"])
 c=r(["qm","config","903"])
 out["plant_vm"]={"state":q.stdout.strip().removeprefix("status: ") if q and q.returncode==0 else "unknown"}
 if c and c.returncode==0:
  for k in ("name","onboot","memory","agent","balloon"):
   m=re.search(r"^"+k+r":\s*(.*)$",c.stdout,re.M)
   if m:
    out["plant_vm"][k]=m.group(1)[:50] if k=="name" else m.group(1).split(",",1)[0][:20]
 if out["plant_vm"]["state"]=="running":
  p=r(["qm","agent","903","ping"],9)
  out["plant_vm"]["agent_responds"]=bool(p and p.returncode==0)
  if out["plant_vm"]["agent_responds"]:
   p=r(["qm","guest","exec","903","--","ha","core","info"],11)
   if p and p.returncode==0:
    try:
     j=json.loads(p.stdout);out["plant_vm"]["ha_info_exec_started"]=True
     if j.get("exited"):out["plant_vm"]["ha_info_exitcode"]=j.get("exitcode")
    except ValueError:out["plant_vm"]["ha_info_exec_started"]=False
 backups=[]
 d=Path("/mnt/pve/NAS/dump")
 if d.exists() and d.is_dir():
  for x in d.iterdir():
   if x.name.startswith("vzdump-qemu-903-") and x.is_file():
    backups.append({"bytes":x.stat().st_size})
 out["existing_plant_archives"]={"count":len(backups),"largest_mib":round(max([x["bytes"] for x in backups],default=0)/1048576,1)}
 c=Path("/etc/pve/storage.cfg")
 if c.is_file():
  raw=c.read_text(errors="replace")
  m=re.search(r"(?ms)^cifs:\s+NAS\b(.*?)(?=^\w+:\s|\Z)",raw)
  out["nas_storage_allows_backup"]=bool(m and re.search(r"^\s*content\s+.*\bbackup\b",m.group(1),re.M))
 f=r(["df","-Pk","/mnt/pve/NAS"])
 if f and f.returncode==0 and len(f.stdout.splitlines())>=2:
  bits=f.stdout.splitlines()[-1].split()
  if len(bits)>=4:out["nas_available_gib"]=round(int(bits[3])/1048576,2)
for ct in ([116] if node=="nodea" else [115]):
 info={"ctid":ct}
 for service in ("consul","lunar"):
  a=r(["pct","exec",str(ct),"--","systemctl","is-active",service],12)
  info[service+"_state"]=a.stdout.strip() if a and a.stdout.strip() in ("active","activating","inactive","failed") else "unavailable"
 # Count only; names/addresses and tokens never sent to actions logs.
 p=r(["pct","exec",str(ct),"--","consul","members"],12)
 if p and p.returncode==0:
  entries=[x for x in p.stdout.splitlines() if x.strip()]
  info["consul_member_count"]=max(0,len(entries)-1)
  info["consul_alive_count"]=sum(bool(re.search(r"\balive\b",x)) for x in entries)
 else:info["consul_members_status"]="unavailable"
 p=r(["pct","exec",str(ct),"--","consul","operator","raft","list-peers","-format=json"],12)
 if p and p.returncode==0:
  try:
   peers=json.loads(p.stdout)
   info["consul_voters_total"]=sum(bool(x.get("Voter")) for x in peers if isinstance(x,dict))
   info["consul_peer_total"]=len(peers)
   info["consul_leader_present"]=any(x.get("Leader") for x in peers if isinstance(x,dict))
  except (ValueError,TypeError):info["consul_raft_status"]="unparsed"
 else:info["consul_raft_status"]="unavailable"
 out["guardian"]=info
print("JNS_PLANT_GUARDIAN_SAFE="+json.dumps(out,sort_keys=True))
'''
def remote(host):
    code=base64.b64encode(REMOTE.encode()).decode()
    cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",
         host,shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+code+"'))"])]
    a=run(cmd,85)
    if not a or a.returncode: return {"access":"unavailable"}
    lines=[x.split("=",1)[1] for x in a.stdout.splitlines() if x.startswith("JNS_PLANT_GUARDIAN_SAFE=")]
    if len(lines)!=1:return {"access":"no_result"}
    try:return json.loads(lines[0])
    except ValueError:return {"access":"malformed"}
def local():
    out={"node":"nodec","uid_root":os.geteuid()==0}
    d=Path("/mnt/pve/nfs-ct")
    a=run(["findmnt","-n","-M",str(d)])
    out["nfs_backup_mounted"]=bool(a and a.returncode==0)
    f=run(["df","-Pk",str(d)])
    if f and f.returncode==0 and len(f.stdout.splitlines())>=2:
        parts=f.stdout.splitlines()[-1].split()
        if len(parts)>=4:out["nfs_available_gib"]=round(int(parts[3])/1048576,1)
    patterns=(r"^\s*([a-z][a-z0-9_:-]+)\)",r"^\s*case\s+(.+?)\s+in")
    for name in ("jns-gateway-exec","jns-gateway-exec.base"):
        p=Path("/usr/local/sbin")/name
        if not p.is_file() or not os.access(p,os.R_OK):
            out[name+"_access"]="not_readable"
            continue
        s=p.read_text(errors="replace")
        types=[]
        for line in s.splitlines():
            m=re.match(patterns[0],line)
            if m and len(m.group(1))<=65:types.append(m.group(1))
        out[name+"_allowed_job_types"]=sorted(set(types))[:75]
        out[name+"_readable"]=True
    p=run(["sudo","-n","-l","/usr/local/sbin/jns-gateway-exec"])
    out["trusted_executor_sudo_n_allowed"]=bool(p and p.returncode==0)
    return out
print("JNS_PLANT_GUARDIAN_DEEP_PREFLIGHT")
for host in ("nodea","nodeb"):
    print(host.upper()+"="+json.dumps(remote(host),sort_keys=True),flush=True)
print("NODEC="+json.dumps(local(),sort_keys=True),flush=True)
print("JNS_READONLY=yes")
