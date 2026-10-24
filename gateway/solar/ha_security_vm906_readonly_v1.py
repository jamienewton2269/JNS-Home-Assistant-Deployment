#!/usr/bin/env python3
"""Solar Economy VM906 read-only relocation preflight.
Runs on established nodec GitHub runner. No state changes, no private MAC,
IP, mount endpoint, token, auth material, entity, or configuration secrets.
"""
import json
import pathlib
import re
import shlex
import socket
import subprocess

def run(cmd, seconds=15):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=seconds)
    except (OSError, subprocess.TimeoutExpired):
        return None

def vm_config_summary(data):
    summary={"config_readable":bool(data),"vm_id":906}
    if not data:return summary
    for key in ("name","memory","balloon","cores","sockets","onboot","startup","agent","ostype","bios","machine"):
        m=re.search(r"^"+key+r":\s*(.*)$",data,re.M)
        if m:
            v=m.group(1).strip()
            if key in ("name","memory","balloon","cores","sockets","onboot","ostype","bios","agent"):
                summary[key]=v[:70]
            elif key=="machine":
                summary[key]=v.split(",")[0][:50]
            elif key=="startup": summary["startup_configured"]=True
    disks={}
    passthrough=[]
    for line in data.splitlines():
        m=re.match(r"^(scsi\d+|virtio\d+|sata\d+|ide\d+|efidisk\d+|tpmstate\d+|unused\d+):\s*(.+)",line)
        if m:
            typ,vol=m.groups()
            target=vol.split(",",1)[0]
            storage=target.split(":",1)[0] if ":" in target else ("device_or_path" if target.startswith("/") else "other")
            size=re.search(r"(?:^|,)size=([^,\s]+)",vol)
            disks[typ]={"storage":storage,"size":size.group(1) if size else "unspecified","physical_path":target.startswith("/"),"media_cdrom":"media=cdrom" in vol}
        p=re.match(r"^(usb\d+|hostpci\d+|serial\d+|parallel\d+|args|hookscript|ivshmem):",line)
        if p:passthrough.append(p.group(1))
    summary["disks"]=disks
    summary["special_device_configuration"]=passthrough
    summary["snapshot_sections"]=len(re.findall(r"^\[[^\]]+\]",data,re.M))
    summary["network_adapter_count"]=len(re.findall(r"^net\d+:",data,re.M))
    summary["additional_host_mounts"]=bool(re.search(r"^(virtiofs\d+|share\d+):",data,re.M))
    return summary

def nodec_local():
    path=pathlib.Path("/etc/pve/nodes/nodec/qemu-server/906.conf")
    try:config=path.read_text(encoding="utf-8")
    except OSError:config=""
    result=vm_config_summary(config)
    pidpath=pathlib.Path("/var/run/qemu-server/906.pid")
    try:
        pid=int(pidpath.read_text().strip())
        process_exists=pathlib.Path("/proc/"+str(pid)).exists()
        result["running_pid_observed"]=bool(process_exists)
    except (OSError,ValueError):
        result["running_pid_observed"]=False
    result["pid_signal_authoritative"]=False
    # The runtime PID is an indicator, not a guarantee of a running HA Core.
    try:
        for d in ("nodec", "nodea", "nodeb"):
            p=pathlib.Path("/etc/pve/nodes")/d/"qemu-server/906.conf"
            result["locally_visible_vm906_config_"+d]=p.is_file()
    except OSError:
        pass
    d=pathlib.Path("/dev")
    result["host_usb_presence"]=d.exists()  # no serial identifiers disclosed
    return result

def nodea_remote():
    command=r'''
set -eu
if [ "$(hostname -s)" != "nodea" ]; then exit 55; fi
if qm config 906 >/dev/null 2>&1; then echo "TARGET_906_COLLISION=yes"; else echo "TARGET_906_COLLISION=no"; fi
echo "TARGET_PVE_AVAILABLE=yes"
free -m | awk '/^Mem:/ {print "TARGET_MEM_TOTAL_MB="$2;print "TARGET_MEM_AVAILABLE_MB="$7} /^Swap:/ {print "TARGET_SWAP_USED_MB="$3}'
pvesm status 2>/dev/null | awk '$1=="vmdata" {print "TARGET_VMDATA_STATUS="$3;print "TARGET_VMDATA_AVAILABLE_KIB="$6}' || :
qm list 2>/dev/null | awk 'NR>1 && ($1==900 || $1==902 || $1==903 || $1==905 || $1==906) {print "VM_ON_A_"$1"="$3}'
'''
    cmd=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=5",
         "-o","StrictHostKeyChecking=yes","nodea",shlex.join(["bash","-c",command])]
    p=run(cmd,20)
    if not p or p.returncode:return {"status":"trusted_nodea_read_blocked"}
    allowed={"TARGET_906_COLLISION","TARGET_PVE_AVAILABLE","TARGET_MEM_TOTAL_MB",
             "TARGET_MEM_AVAILABLE_MB","TARGET_SWAP_USED_MB","TARGET_VMDATA_STATUS",
             "TARGET_VMDATA_AVAILABLE_KIB","VM_ON_A_900","VM_ON_A_902","VM_ON_A_903",
             "VM_ON_A_905","VM_ON_A_906"}
    data={}
    for line in p.stdout.splitlines():
        if "=" not in line:continue
        k,v=line.split("=",1)
        if k in allowed and re.fullmatch(r"[\w.-]+",v):
            data[k]=v
    return {"status":"ok",**data}

def dns_tcp():
    result={}
    target="ha-security.home.arpa"
    try:
        entries=socket.getaddrinfo(target,8123,type=socket.SOCK_STREAM)
        result["name_resolves"]=bool(entries)
    except OSError:
        result["name_resolves"]=False
    result["tcp_8123_reachable"]=False
    if result["name_resolves"]:
        try:
            with socket.create_connection((target,8123),timeout=4):
                result["tcp_8123_reachable"]=True
        except OSError:pass
    return result

def main():
    print("JNS_SOLAR_VM906_RELOCATION_PREFLIGHT_READ_ONLY")
    print("NODEC_VM906="+json.dumps(nodec_local(),sort_keys=True))
    print("NODEA_DESTINATION="+json.dumps(nodea_remote(),sort_keys=True))
    print("HA_SECURITY_DNS_HEALTH="+json.dumps(dns_tcp(),sort_keys=True))
    print("JNS_SOLAR_VM906_PREFLIGHT_COMPLETE_READ_ONLY")
if __name__=="__main__":main()
