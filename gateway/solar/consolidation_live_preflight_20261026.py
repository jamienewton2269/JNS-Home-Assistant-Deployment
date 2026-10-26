#!/usr/bin/env python3
"""Read-only JNS consolidation preflight. No guest writes, power controls, or secret output.

Runs on the existing Node C GitHub Actions runner using already authorised access;
does not assume it has unrestricted root. Emits filtered state only.
"""
import base64
import json
import os
import re
import shlex
import subprocess
from pathlib import Path

def run(argv, timeout=18):
    try:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None

def remotescript(host, src):
    encoded=base64.b64encode(src.encode()).decode()
    argv=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
          "-o","ConnectTimeout=5",host,
          shlex.join(["python3","-c", "exec(__import__('base64').b64decode('"+encoded+"'))"])]
    result=run(argv,70)
    if result is None or result.returncode!=0:
        return {"access":"unavailable_or_not_authorised"}
    lines=[x[len("JNS_SAFE_AUDIT="):] for x in result.stdout.splitlines()
           if x.startswith("JNS_SAFE_AUDIT=")]
    if len(lines)!=1:
        return {"access":"no_allowlisted_result"}
    try:
        return json.loads(lines[0])
    except ValueError:
        return {"access":"invalid_safe_result"}

REMOTE=String = r'''
import os,re,json,subprocess
from pathlib import Path
def run(argv,timeout=12):
    try:return subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):return None
def check_vm(vmid):
    q=run(["qm","status",str(vmid)])
    c=run(["qm","config",str(vmid)])
    d={"id":vmid,"state":q.stdout.strip().removeprefix("status: ") if q and q.returncode==0 else "unavailable",
       "config_readable":bool(c and c.returncode==0)}
    if c and c.returncode==0:
        text=c.stdout
        for key in ("name","memory","balloon","cores","onboot","agent"):
            m=re.search("^"+key+r":\s*([^\n]+)",text,re.M)
            if m:
                val=m.group(1).strip()
                if key=="name":
                    d[key]=val if re.fullmatch(r"[a-zA-Z0-9_-]{1,80}",val) else "restricted"
                elif key=="agent":
                    d[key]=bool(re.search(r"(^|[, ])(enabled=)?1([, ]|$)",val))
                elif val.isdecimal():d[key]=int(val)
        d["disk_count"]=len(re.findall(r"^(scsi|sata|virtio|ide|efidisk)\d+:",text,re.M))
        d["storage_backends"]=sorted(set(re.findall(r"^(?:scsi|sata|virtio)\d+:\s*([a-zA-Z0-9_-]+):",text,re.M)))
        d["usb_passthrough"]=bool(re.search(r"^(usb|hostpci)\d+:",text,re.M))
    if vmid==906 and d["state"]=="running":
        a=run(["qm","agent","906","ping"],9)
        d["qga_ping"]=bool(a and a.returncode==0)
        d["qga_error_kind"]="none" if d["qga_ping"] else "not_responding_or_not_permitted"
    return d
def pct_status(vmid):
    d={"id":vmid}
    p=run(["pct","status",str(vmid)])
    d["state"]=p.stdout.strip().removeprefix("status: ") if p and p.returncode==0 else "unavailable"
    if d["state"]=="running":
        for service in ("consul","lunar"):
            r=run(["pct","exec",str(vmid),"--","systemctl","is-active",service],12)
            d[service+"_active"]=r.stdout.strip() if r and r.stdout.strip() in
                ("active","inactive","failed","activating","deactivating","unknown") else "unavailable"
            r=run(["pct","exec",str(vmid),"--","systemctl","is-enabled",service],12)
            d[service+"_enabled"]=r.stdout.strip() if r and r.stdout.strip() in
                ("enabled","disabled","static","masked","indirect","generated","linked","not-found") else "unavailable"
    return d
def storage():
    s=run(["pvesm","status"])
    out={}
    if s and s.returncode==0:
        for line in s.stdout.splitlines()[1:]:
            v=line.split()
            if len(v)>=3 and v[0] in ("NAS","WD-BACKUP","vmdata","nfs-ct","local-lvm"):
                out[v[0]]=v[2] if v[2] in ("active","inactive","disabled","unknown") else "unknown"
    return out
host=os.uname().nodename.split(".")[0]
out={"host":host,"identity_verified":host in ("nodea","nodeb"),
     "uid_root":os.geteuid()==0,"storage":storage()}
if host=="nodea":
    out["vms"]=[check_vm(906),check_vm(902)]
    out["guardian"]=[pct_status(116)]
elif host=="nodeb":
    out["vms"]=[check_vm(903),check_vm(905)]
    out["guardian"]=[pct_status(115)]
for svc in ("jns-cluster-proxy","pve-ha-crm","pve-ha-lrm"):
    s=run(["systemctl","is-active",svc],7)
    out["host_"+svc+"_active"]=s.stdout.strip() if s and s.stdout.strip() in ("active","inactive","failed") else "unavailable"
out["corosync_config_exists"]=Path("/etc/pve/corosync.conf").exists()
print("JNS_SAFE_AUDIT="+json.dumps(out,sort_keys=True))
'''
def local_nodec():
    p=run(["hostname","-s"])
    host=p.stdout.strip() if p and p.returncode==0 else "unavailable"
    if host!="nodec":
        return {"host":host,"access":"wrong_runner"}
    out={"host":"nodec","uid_root":os.geteuid()==0,
         "corosync_config_exists":Path("/etc/pve/corosync.conf").exists()}
    for vmid in (991,903):
        q=run(["qm","status",str(vmid)])
        c=run(["qm","config",str(vmid)])
        d={"id":vmid,
           "state":q.stdout.strip().removeprefix("status: ") if q and q.returncode==0 else "unavailable",
           "config_readable":bool(c and c.returncode==0)}
        if not d["config_readable"]:
            try:
                ctext=(Path("/etc/pve/qemu-server")/(str(vmid)+".conf")).read_text()
            except (OSError,PermissionError):ctext=""
        else:ctext=c.stdout
        if ctext:
            d["config_readable"]=True
            for key in ("name","memory","onboot","agent","cores"):
                m=re.search("^"+key+r":\s*([^\n]+)",ctext,re.M)
                if m:
                    val=m.group(1).strip()
                    if key=="name":d[key]=val if re.fullmatch(r"[a-zA-Z0-9_-]{1,80}",val) else "restricted"
                    elif key=="agent":d[key]=bool(re.search(r"(^|[, ])(enabled=)?1([, ]|$)",val))
                    elif val.isdecimal():d[key]=int(val)
            d["disk_count"]=len(re.findall(r"^(scsi|sata|virtio|ide|efidisk)\d+:",ctext,re.M))
            d["storage_backends"]=sorted(set(re.findall(r"^(?:scsi|sata|virtio)\d+:\s*([a-zA-Z0-9_-]+):",ctext,re.M)))
            d["usb_passthrough"]=bool(re.search(r"^(usb|hostpci)\d+:",ctext,re.M))
        out.setdefault("vms",[]).append(d)
    for ct in (117,):
        a=run(["pct","status",str(ct)])
        d={"id":ct,"state":a.stdout.strip().removeprefix("status: ") if a and a.returncode==0 else "unavailable"}
        if d["state"]=="running":
            for svc in ("consul","lunar"):
                b=run(["pct","exec",str(ct),"--","systemctl","is-active",svc])
                d[svc+"_active"]=b.stdout.strip() if b and b.stdout.strip() in ("active","inactive","failed") else "unavailable"
        out.setdefault("guardian",[]).append(d)
    for k in ("actions.runner.jamienewton2269-JNS-Home-Assistant-Deployment.nodec","jns-management-bridge"):
        a=run(["systemctl","is-active",k])
        out[k+"_active"]=a.stdout.strip() if a and a.stdout.strip() in ("active","inactive","failed") else "unavailable"
    out["nas_backup_mounted"]=bool(run(["findmnt","-n","-M","/mnt/pve/nfs-ct"]) and
                                  run(["findmnt","-n","-M","/mnt/pve/nfs-ct"]).returncode==0)
    return out
def main():
    print("JNS_CONSOLIDATION_READONLY_PREFLIGHT_20261026")
    for host in ("nodea","nodeb"):
        print(host.upper()+"="+json.dumps(remotescript(host,REMOTE),sort_keys=True),flush=True)
    print("NODEC="+json.dumps(local_nodec(),sort_keys=True),flush=True)
    print("JNS_CONSOLIDATION_NO_STATE_CHANGED=yes")
if __name__=="__main__":main()
