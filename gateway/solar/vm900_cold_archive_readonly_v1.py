#!/usr/bin/env python3
"""JNS Solar VM900 cold-archive feasibility, zero mutation or PII in output."""
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

def cmd(argv, timeout=25):
    try:
        p=subprocess.run(argv, capture_output=True,text=True,timeout=timeout)
        return p.returncode,p.stdout,p.stderr
    except (OSError,subprocess.TimeoutExpired):
        return 125,"","unavailable"

def remote(node,script,timeout=35):
    # Existing pinned hostname aliases. No accept-new, no identity changes.
    rc,out,err=cmd(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=6",
      "-o","StrictHostKeyChecking=yes",node,
      shlex.join(["bash","-c",script])],timeout)
    if rc: return {"status":"ssh_blocked","exit_code":rc}
    return {"status":"ok","output":out}

def vm900_source():
    shell=r'''
set -u
test "$(hostname -s)" = nodea || exit 57
echo 'HOST_OK=yes'
qm status 900 || :
qm config 900 | grep -E '^(name|memory|cores|onboot|startup|scsi[0-9]+|efidisk[0-9]+|net[0-9]+):' | sed -E 's/^(net[0-9]+):.*/\1: [present-redacted]/'
for vol in vmdata/vm-900-disk-1 vmdata/vm-900-disk-0; do
  if command -v zfs >/dev/null; then
    zfs list -H -o name,used,refer,volsize "$vol" 2>/dev/null || :
  fi
done
echo '--- guest backup mode availability ---'
command -v vzdump >/dev/null && echo 'VZDUMP_AVAILABLE=yes' || :
echo '--- existing backup storage ---'
pvesm status 2>/dev/null | awk 'NR>1 && ($1=="local" || $1=="NAS" || $1=="WD-BACKUP") {print "STORAGE="$1,"STATE="$3,"FREE_KIB="$6}' || :
'''
    r=remote("nodea",shell,35)
    if r["status"]!="ok":return r
    output=r["output"]
    data={"status":"ok"}
    mm=re.search(r"status:\s+(\w+)",output)
    data["vm900_state"]=mm.group(1) if mm else "unavailable"
    data["disk_virtual_sizes"]=re.findall(r"size=(\d+[GMK])",output)
    m=re.search(r"^memory:\s+(\d+)",output,re.M)
    data["ram_configured_mb"]=int(m.group(1)) if m else None
    m=re.search(r"^onboot:\s+(\d+)",output,re.M)
    data["onboot"]=int(m.group(1)) if m else None
    data["vzdump_available"]="VZDUMP_AVAILABLE=yes" in output
    data["zfs_disk_metrics"]=[]
    for line in output.splitlines():
        # ZFS dataset names and sizes only, never secrets, addresses or volume contents
        if re.fullmatch(r"vmdata/vm-900-disk-\d+\s+\S+\s+\S+\s+\S+",line):
            v=line.split()
            data["zfs_disk_metrics"].append({"volume":v[0].split("/")[-1],
                "used":v[1],"referenced":v[2],"virtual_size":v[3]})
    data["storage_states"]={}
    for line in output.splitlines():
        m=re.match(r"STORAGE=(\S+) STATE=(\S+) FREE_KIB=(\S+)",line)
        if m:data["storage_states"][m.group(1)]={"state":m.group(2),"free_kib":m.group(3)}
    data["vm_network_adapters"] = sum("net" in x for x in output.splitlines() if x.startswith("net"))
    return data

def nodec_storage():
    data={"status":"ok","host":os.uname().nodename.split(".")[0]}
    paths=["/","/var/lib/vz","/mnt","/opt"]
    data["filesystems"]={}
    for p in paths:
        if not os.path.isdir(p):continue
        usage=shutil.disk_usage(p)
        data["filesystems"][p]={"free_gib":round(usage.free/2**30,1),
                                "total_gib":round(usage.total/2**30,1)}
    rc,out,_=cmd(["/usr/sbin/zfs","list","-H","-o","name,available,used","-t","filesystem,volume"],15)
    data["zfs_query_allowed"]=(rc==0)
    if rc==0:
        rows=[]
        for l in out.splitlines():
            bits=l.split()
            if len(bits)>=3:
                rows.append({"pool":bits[0].split("/")[0],"available":bits[1],
                             "used":bits[2],"is_vm_disk":bits[0].split("/")[-1].startswith("vm-")})
        data["zfs_pool_entries"]=rows[:25]
    configs=Path("/etc/pve/nodes/nodec/qemu-server")
    try:ids={int(x.stem) for x in configs.glob("*.conf") if x.stem.isdigit()}
    except OSError:ids=set()
    data["vm900_id_config_collision"]=900 in ids
    for p in [Path("/etc/pve/storage.cfg"),Path("/etc/pve/nodes/nodec/qemu-server/906.conf")]:
        data["present_"+p.name]=p.is_file()
    return data

def inspect_vm900_containers():
    # Only classify roles and exposed port counts; Docker names/addresses never logged.
    sub=["docker","ps","--format","{{.Names}}|{{.Status}}|{{.Ports}}"]
    c=remote("nodea","qm guest exec 900 -- "+shlex.join(sub),18)
    if c["status"]!="ok":return {"status":"guest_exec_transport_blocked"}
    try:r=json.loads(c["output"])
    except ValueError:return {"status":"guest_exec_unavailable"}
    if not r.get("exited"):return {"status":"guest_exec_async_or_unavailable"}
    if r.get("exitcode")!=0:return {"status":"docker_query_failed"}
    rows=[]
    for l in r.get("out-data","").splitlines():
        p=l.split("|",2)
        if len(p)!=3:continue
        rows.append(p)
    roles=("audio","dns","esphome","multicast","observer","piper","ssh",
           "supervisor","mqtt","matter","zigbee","go2rtc","influxdb")
    running=[r for r in rows if r[1].startswith("Up ")]
    def classify(n):
        return next((x for x in roles if x in n.lower()),"other")
    kinds={}
    for name,state,ports in running:
        role=classify(name)
        kinds.setdefault(role,{"running":0,"has_published_ports":0})
        kinds[role]["running"]+=1
        if "->" in ports:kinds[role]["has_published_ports"]+=1
    return {"status":"ok","total":len(rows),"running":len(running),
            "running_roles":kinds,
            "core_running":any(n.lower() in ("homeassistant","home-assistant") and st.startswith("Up ") for n,st,_ in rows)}

def main():
    print("JNS_VM900_COLD_ARCHIVE_READONLY")
    print("SOURCE_NODEA="+json.dumps(vm900_source(),sort_keys=True))
    print("DEST_NODEC="+json.dumps(nodec_storage(),sort_keys=True))
    print("CONTAINERS="+json.dumps(inspect_vm900_containers(),sort_keys=True))
    print("JNS_VM900_COLD_ARCHIVE_READONLY_COMPLETE")
if __name__=="__main__":main()
