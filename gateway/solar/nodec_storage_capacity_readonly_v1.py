#!/usr/bin/env python3
"""Read-only VM900 Node C placement capacity inspection.
Sanitises block device IDs, LVM volumes and addresses; no direct
container, guest, mount or user data is disclosed.
"""
import json,re,subprocess
from pathlib import Path

def run(args,timeout=12):
    try:
        r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
        return r.returncode,r.stdout
    except (OSError,subprocess.TimeoutExpired):
        return 125,""

def sizes_to_gib(s):
    # LVM bytes from --units b --nosuffix
    try:return round(float(s)/1073741824,2)
    except (TypeError,ValueError):return None
def local_capacity():
    result={"status":"ok"}
    try:
        p=Path("/etc/pve/storage.cfg").read_text(errors="replace")
        result["storage_definitions"]=[]
        curr=None
        for line in p.splitlines():
            h=re.match(r"^(\w+):\s+(\S+)",line)
            if h:
                curr={"type":h.group(1),"storage":h.group(2),
                      "path_on_nodec":None,"nodes":None,"content":None}
                result["storage_definitions"].append(curr)
                continue
            if not line[:1].isspace() or curr is None:continue
            m=re.match(r"^\s+(path|nodes|content|vgname|thinpool|pool)\s+(.+)",line)
            if m:
                k,v=m.groups()
                if k=="path":curr["path_on_nodec"]=v if v in ("/var/lib/vz","/mnt/data") else "custom_path"
                elif k=="nodes":curr["nodes"]=v[:60]
                elif k=="content":curr["content"]=v[:80]
                elif k in ("vgname","thinpool","pool"):curr[k]="configured"
    except OSError:
        result["storage_definitions"]="not_readable"
    r,out=run(["/usr/bin/lsblk","-b","-J","-o","TYPE,SIZE,FSTYPE,MOUNTPOINT"])
    if r==0:
        try:
            j=json.loads(out)
            nodes=j.get("blockdevices",[])
            def rec(items):
                for v in items:
                    typ=v.get("type")
                    if typ in ("disk","part","lvm"):
                        yield {"type":typ,"size_gib":sizes_to_gib(v.get("size")),
                               "fstype":v.get("fstype"),"root_mount":v.get("mountpoint")=="/"}
                    yield from rec(v.get("children") or [])
            result["block_devices"]=list(rec(nodes))[:50]
        except ValueError:result["block_devices"]="invalid"
    else:result["block_devices"]="unavailable"
    r,out=run(["/usr/sbin/lvs","--reportformat","json","--units","b","--nosuffix",
      "-o","lv_size,data_percent,lv_attr,vg_name,lv_name"],15)
    if r==0:
        try:
            j=json.loads(out)
            vals=[]
            for report in j.get("report",[]):
                for item in report.get("lv",[]):
                    name=item.get("lv_name","")
                    if re.fullmatch(r"vm-\d+-disk-\d+",name):
                        vals.append({"role":"existing_guest_disk","size_gib":sizes_to_gib(item.get("lv_size"))})
                    else:
                        vals.append({"role":"lvm_pool_or_system","size_gib":sizes_to_gib(item.get("lv_size")),
                                     "data_percent":item.get("data_percent"),"lv_attr":str(item.get("lv_attr",""))[:3]})
            result["lvm_summary"]={"existing_guest_disks":sum(x["role"]=="existing_guest_disk" for x in vals),
                "pool_and_system_volumes":[x for x in vals if x["role"]!="existing_guest_disk"][:15]}
        except ValueError:result["lvm_summary"]="unparsed"
    else:result["lvm_summary"]="not_permitted"
    r,out=run(["/usr/sbin/vgs","--reportformat","json","--units","b","--nosuffix","-o","vg_size,vg_free"],15)
    if r==0:
        try:
            j=json.loads(out)
            result["volume_groups"]=[{"size_gib":sizes_to_gib(v.get("vg_size")),
                 "free_gib":sizes_to_gib(v.get("vg_free"))} for x in j.get("report",[]) for v in x.get("vg",[])]
        except ValueError:result["volume_groups"]="unparsed"
    return result

if __name__=="__main__":
    print("JNS_VM900_NODEC_LOCAL_CAPACITY_READONLY")
    print("NODEC="+json.dumps(local_capacity(),sort_keys=True))
    print("JNS_VM900_NODEC_LOCAL_CAPACITY_COMPLETE")
