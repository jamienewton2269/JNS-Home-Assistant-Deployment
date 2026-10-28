#!/usr/bin/env python3
"""Read-only checks for a single retired Node C Proxmox template: VM9906."""
import json, os, re, subprocess

def cmd(args):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=15)
        return p.stdout if p.returncode==0 else None
    except (OSError,subprocess.TimeoutExpired):return None

result={"vmid":9906,"host":os.uname().nodename.split(".")[0],"read_only":True}
if result["host"]!="nodec":
    print("JNS_GOLDEN_PREFLIGHT="+json.dumps({**result,"gate":"WRONG_NODE"},sort_keys=True));raise SystemExit(2)
status=cmd(["qm","status","9906"])
config=cmd(["qm","config","9906"])
result["status"]=status.strip().removeprefix("status: ") if status else "unknown"
result["config_readable"]=config is not None
if config is not None:
    result["correct_name"]=bool(re.search(r"^name:\s*haos18-golden\s*$",config,re.M))
    result["template"]=bool(re.search(r"^template:\s*1\s*$",config,re.M))
    result["protected"]=bool(re.search(r"^protection:\s*1\s*$",config,re.M))
    result["locked"]=bool(re.search(r"^lock:",config,re.M))
    result["onboot"]=bool(re.search(r"^onboot:\s*1\s*$",config,re.M))
    result["disks_configured"]=len(re.findall(r"^(?:scsi|virtio|sata|ide|efidisk|unused)\d+:",config,re.M))
    result["disk_storages"]=sorted(set(re.findall(r"^(?:scsi|virtio|sata|ide|efidisk|unused)\d+:\s*([a-zA-Z0-9_-]+):",config,re.M)))
raw=cmd(["lvs","--noheadings","--separator","|","-o","lv_name,origin,lv_size,data_percent","pve"])
result["lvm_readable"]=raw is not None
if raw is not None:
    lv=[v.strip().split("|") for v in raw.splitlines()]
    base=[v[0].strip() for v in lv if len(v)>=2 and re.fullmatch(r"base-9906-disk-\d+",v[0].strip())]
    depend=[v for v in lv if len(v)>=2 and v[1].strip() in base]
    result["template_base_volumes"]=len(base)
    result["dependent_linked_volumes"]=len(depend)
    result["linked_clone_gate_clear"]=not depend
priv=cmd(["sudo","-n","-l"])
result["sudo_rights_readable"]=priv is not None
if priv is not None:
    result["sudo_has_direct_qm_permission"]="/usr/sbin/qm" in priv
    result["sudo_has_gateway_permission"]="jns-gateway-exec" in priv
result["eligible"]=(result["status"]=="stopped" and result.get("correct_name") and
    result.get("template") and not result.get("protected") and not result.get("locked") and
    not result.get("onboot") and result.get("lvm_readable") and result.get("linked_clone_gate_clear"))
print("JNS_GOLDEN_PREFLIGHT="+json.dumps(result,sort_keys=True),flush=True)
