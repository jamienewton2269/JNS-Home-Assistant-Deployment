#!/usr/bin/env python3
"""JNS VM906 cold-start and Guardian retirement preflight, read-only.

Authenticates via already-authorised Node C runner -> Node A/B host SSH.
Emits filtered unit/service/backup metadata. No secrets, URLs, IPs, or files.
"""
import base64,subprocess,json,shlex
REMOTE=r'''
import os,re,json,subprocess,socket
from pathlib import Path
H=os.uname().nodename.split(".")[0]
if H not in ("nodea","nodeb") or os.geteuid()!=0:raise SystemExit(75)
def run(args,sec=14):
 try:return subprocess.run(args,capture_output=True,text=True,timeout=sec)
 except (OSError,subprocess.TimeoutExpired):return None
def state(argv,choices):
 p=run(argv)
 if not p:return "unavailable"
 s=p.stdout.strip()
 return s if s in choices else "unavailable"
O={"host":H,"readonly":True,"corosync":Path("/etc/pve/corosync.conf").exists()}
unitnames=["jns-cluster-proxy.service","jns-ha-guardian-probe.service",
           "jns-ha-guardian-probe.timer","lunar-discovery-export.service",
           "lunar-discovery-export.timer","jns-watchdog.service"]
UNIT_PROPS=("Id","LoadState","ActiveState","SubState","UnitFileState","RefuseManualStop",
"Requires","Wants","WantedBy","PartOf","Before","After","Triggers","TriggeredBy")
units={}
for name in unitnames:
 d={}
 p=run(["systemctl","show",name]+["-p"+z for z in UNIT_PROPS],9)
 if p and p.returncode==0:
  for line in p.stdout.splitlines():
   if "=" not in line:continue
   k,v=line.split("=",1)
   if k in ("Id","LoadState","ActiveState","SubState","UnitFileState","RefuseManualStop"):d[k]=v[:90]
   if k in ("Requires","Wants","WantedBy","PartOf","Triggers","TriggeredBy"):
    d[k]=sorted(q for q in v.split() if re.fullmatch(r"[a-zA-Z0-9_.@:-]{2,100}",q))[:25]
 units[name]=d
O["legacy_host_units"]=units
p=run(["systemctl","list-timers","--all","--no-legend","--plain"],8)
if p and p.returncode==0:
 O["guardian_timer_listed"]=any("jns-ha-guardian-probe.timer" in x for x in p.stdout.splitlines())
 O["lunar_timer_listed"]=any("lunar-discovery-export.timer" in x for x in p.stdout.splitlines())
# Check host processes by command name and only if known legacy pattern.
p=run(["ps","-eo","comm="],8)
if p and p.returncode==0:
 counts={}
 for key in ("consul","lunar","jns-cluster-proxy","jns-watchdog"):
  counts[key]=sum(x.strip()==key for x in p.stdout.splitlines())
 O["known_host_process_counts"]=counts
c=116 if H=="nodea" else 115
O["legacy_ct_id"]=c
p=run(["pct","config",str(c)],9)
if p and p.returncode==0:
 for k in ("onboot","memory","swap"):
  m=re.search("^"+k+r":\s*(\d+)",p.stdout,re.M)
  if m:O["ct_"+k]=int(m.group(1))
p=run(["pct","status",str(c)])
O["ct_status"]=p.stdout.strip().removeprefix("status: ") if p and p.returncode==0 else "unavailable"
if O["ct_status"]=="running":
 # The child CLI may not have consul on PATH. Standard systemd properties still work.
 for svc in ("consul.service","lunar.service"):
  p=run(["pct","exec",str(c),"--","systemctl","show",svc,"-p","ActiveState","-p","UnitFileState"],12)
  if p and p.returncode==0:
   v=dict(l.split("=",1) for l in p.stdout.splitlines() if "=" in l)
   O["ct_"+svc]={"active":v.get("ActiveState"),"enabled":v.get("UnitFileState")}
 # Check active listeners without reporting addresses or sensitive endpoint details.
 p=run(["pct","exec",str(c),"--","ss","-H","-lnt"],12)
 if p and p.returncode==0:
  O["ct_consul_listeners"]=sum(bool(re.search(r":(?:8300|8301|8302|8500|8501)\b",l)) for l in p.stdout.splitlines())
# identify important host systemd unit names referencing Guardian/lunar; do not expose bodies
names=[]
for dir in ("/etc/systemd/system","/usr/local/lib/systemd/system"):
 p=Path(dir)
 if not p.is_dir():continue
 for f in p.rglob("*"):
  if f.is_symlink() or not f.is_file() or f.suffix not in (".service",".timer",".socket"):
   continue
  try:
   if f.stat().st_size>131072:continue
   data=f.read_text(errors="replace")
  except OSError:continue
  if re.search(r"consul|guardian|lunar",data,re.I):names.append(f.name)
O["host_legacy_unit_file_names"]=sorted(set(names))[:75]
if H=="nodea":
 p=run(["qm","status","906"],9)
 O["vm906_state"]=p.stdout.strip().removeprefix("status: ") if p and p.returncode==0 else "unknown"
 p=run(["qm","config","906"],9)
 if p and p.returncode==0:
  for k in ("name","memory","onboot","agent","balloon"):
   m=re.search(r"^"+k+r":\s*([^\n]+)",p.stdout,re.M)
   if m:O["vm906_"+k]=m.group(1)[:30] if k=="name" else m.group(1).split(",")[0][:25]
  O["vm906_locked"]=bool(re.search(r"^lock:",p.stdout,re.M))
 p=run(["qm","agent","906","ping"],8)
 O["vm906_agent_responding"]=bool(p and p.returncode==0)
 p=run(["free","-m"],9)
 if p and p.returncode==0:
  for line in p.stdout.splitlines():
   z=line.split()
   if z and z[0]=="Mem:" and len(z)>6:O["memory_available_mib"]=int(z[6])
   if z and z[0]=="Swap:" and len(z)>2:O["swap_used_mib"]=int(z[2])
 p=run(["zfs","list","-H","-t","snapshot","-o","name"],13)
 if p and p.returncode==0:
  O["vm906_zfs_snapshot_count"]=sum(bool(re.match(r"^vmdata/vm-906-disk-[0-9]+@",l)) for l in p.stdout.splitlines())
  O["vm906_zfs_snapshot_recent"]=any("20261026" in l for l in p.stdout.splitlines() if "vm-906-disk" in l)
 p=run(["zfs","list","-H","-o","name,used,refer,volsize","-t","volume"],13)
 if p and p.returncode==0:
  O["vm906_zvols"]=[]
  for l in p.stdout.splitlines():
   v=l.split()
   if len(v)>=4 and re.fullmatch(r"vmdata/vm-906-disk-[0-9]+",v[0]):
    O["vm906_zvols"].append({"disk":v[0].rsplit("-",1)[-1],"used":v[1],"referenced":v[2],"volsize":v[3]})
 p=run(["df","-Pk","/var/lib/jns-solar"],9)
 if p and p.returncode==0:
  try:O["host_archive_dir_free_gib"]=round(int(p.stdout.splitlines()[-1].split()[3])/1048576,1)
  except (ValueError,IndexError):pass
 p=run(["zfs","get","-H","-o","value","mountpoint","vmdata"],10)
 if p and p.returncode==0:O["vmdata_dataset_has_mountpoint"]=p.stdout.strip() not in ("none","legacy","-")
 p=run(["pvesm","status"],12)
 if p and p.returncode==0:
  O["backup_storages_status"]={z[0]:z[2] for l in p.stdout.splitlines()[1:] if len(z:=l.split())>=3 and z[0] in ("NAS","WD-BACKUP","nfs-ct")}
 p=run(["ss","-H","-lnt"],8)
 if p and p.returncode==0:
  O["port_8006_listening"]=any(re.search(r":8006\b",l) for l in p.stdout.splitlines())
else:
 p=run(["zfs","list","-H","-o","available","vmdata"],9)
 if p and p.returncode==0:O["nodeb_vmdata_available"]=p.stdout.strip()[:40]
 p=run(["qm","status","906"],9)
 O["nodeb_vm906_existing_status"]=p.stdout.strip() if p and p.returncode==0 else "absent"
 # Check backups without returning file path or sensitive artifact contents.
 base=Path("/mnt/pve/NAS/dump")
 archives=[]
 if base.is_dir():
  for v in base.iterdir():
   if v.is_file() and re.match(r"vzdump-qemu-906-\d{4}_\d{2}_\d{2}-",v.name):
    archives.append({"size_gib":round(v.stat().st_size/1073741824,3),
                     "mtime_utc_epoch":int(v.stat().st_mtime)})
 O["nas_vm906_archives"]=sorted(archives,key=lambda x:x["mtime_utc_epoch"],reverse=True)[:5]
print("JNS_GATE="+json.dumps(O,sort_keys=True))
'''
def probe(host):
 k=base64.b64encode(REMOTE.encode()).decode()
 cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",host,
       shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+k+"'))"])]
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=105)
 except (OSError,subprocess.TimeoutExpired):return {"access":"timeout"}
 if p.returncode:return {"access":"not_authorised_or_failed"}
 try:return json.loads([x.split("=",1)[1] for x in p.stdout.splitlines() if x.startswith("JNS_GATE=")][-1])
 except (IndexError,ValueError):return {"access":"invalid_result"}
for host in ("nodea","nodeb"):
 print(host.upper()+"="+json.dumps(probe(host),sort_keys=True),flush=True)
print("JNS_GATE_READONLY=yes")
