#!/usr/bin/env python3
"""JNS Solar: compare storage backend dependencies read-only.
No server names, addresses, shares, passwords or raw mount contents are
published to workflow logs; only anonymised existence/equality results.
No mounts, pvesm probes, SSH to NAS, or power commands.
"""
import base64
import json
import shlex
import subprocess

INSPECT = r'''
import json
import re
import socket
import subprocess
from pathlib import Path
MOUNTS={
  "dns_master":"/mnt/jns-dns-master",
  "dns_live":"/mnt/jns-dns-live",
  "nas_cifs":"/mnt/pve/NAS",
  "wd_backup":"/mnt/pve/WD-BACKUP",
}
def mount_exact(path):
    p=subprocess.run(["findmnt","-r","-n","-M",path,"-o","SOURCE,FSTYPE"],
                     capture_output=True,text=True,timeout=5)
    if p.returncode:return {"mounted":False,"server":None}
    s=p.stdout.strip().splitlines()
    if len(s)!=1:return {"mounted":False,"server":None}
    v=s[0].rsplit(" ",1)
    if len(v)!=2:return {"mounted":False,"server":None}
    source,fs=v
    if fs in ("nfs","nfs4") and ":" in source:
        server=source.split(":",1)[0].strip("[]")
    elif fs=="cifs" and source.startswith("//"):
        server=source[2:].split("/",1)[0]
    else:server=None
    return {"mounted":True,"server":server}
def storage_targets():
    p=Path("/etc/pve/storage.cfg")
    if not p.is_file():return {}
    current=None
    targets={}
    for line in p.read_text(errors="replace").splitlines():
        head=re.match(r"^(nfs|cifs):\s+([^\s]+)",line)
        if head:
            current=head.group(2)
            continue
        if line and not line[0].isspace():current=None
        if current in ("WD-BACKUP","NAS"):
            m=re.match(r"^\s+server\s+(\S+)",line)
            if m:targets[current]=m.group(1)
    return targets
def identity(s):
    if not s:return None
    s=s.strip().lower().strip("[]")
    try:
        addresses=set(x[4][0] for x in socket.getaddrinfo(s,None,proto=socket.IPPROTO_TCP))
        if addresses:return addresses
    except (socket.gaierror,OSError):pass
    return set()
def relation(a,b):
    if not a or not b:return "unknown"
    if a.casefold()==b.casefold():return "same"
    ia,ib=identity(a),identity(b)
    if ia and ib:return "same" if ia & ib else "different"
    return "unknown"
data={k:mount_exact(v) for k,v in MOUNTS.items()}
targets=storage_targets()
def server(k):
    m=data[k]
    if m.get("server"):return m["server"]
    if k=="nas_cifs":return targets.get("NAS")
    if k=="wd_backup":return targets.get("WD-BACKUP")
    return None
out={
  "mount_status":{k:bool(x["mounted"]) for k,x in data.items()},
  "storage_declared":{k:k in targets for k in ("NAS","WD-BACKUP")},
  "dns_master_vs_dns_live":relation(server("dns_master"),server("dns_live")),
  "dns_master_vs_nas":relation(server("dns_master"),server("nas_cifs")),
  "dns_live_vs_nas":relation(server("dns_live"),server("nas_cifs")),
  "dns_master_vs_wd_backup":relation(server("dns_master"),server("wd_backup")),
  "dns_live_vs_wd_backup":relation(server("dns_live"),server("wd_backup")),
  "nas_vs_wd_backup":relation(server("nas_cifs"),server("wd_backup")),
}
print("JNS_NAS_DEPENDENCY_JSON="+json.dumps(out,sort_keys=True))
'''
def probe(host):
    encoded=base64.b64encode(INSPECT.encode()).decode()
    cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
         "-o","ConnectTimeout=5","root@"+host,
         shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+encoded+"'))"])]
    try:r=subprocess.run(cmd,capture_output=True,text=True,timeout=35)
    except (OSError,subprocess.TimeoutExpired):return {"status":"host_or_probe_timeout"}
    if r.returncode:return {"status":"probe_unavailable"}
    lines=[l for l in r.stdout.splitlines() if l.startswith("JNS_NAS_DEPENDENCY_JSON=")]
    if not lines:return {"status":"result_missing"}
    try:return {"status":"ok",**json.loads(lines[-1].split("=",1)[1])}
    except ValueError:return {"status":"invalid_result"}
def main():
    print("JNS_SOLAR_NAS_READ_ONLY_PRECHECK",flush=True)
    for host in ("nodea","nodeb"):
        print(host,json.dumps(probe(host),sort_keys=True),flush=True)
    print("JNS_SOLAR_NAS_PRECHECK_COMPLETE",flush=True)
if __name__=="__main__":main()
