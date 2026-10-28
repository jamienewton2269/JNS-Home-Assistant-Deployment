#!/usr/bin/env python3
"""One-time, exact-target retirement of Node C template VM9906.

Default: audit only. --execute: guarded destruction, only after every check
passes. Designed for a privileged local Proxmox operator; NEVER elevate or
bypass the existing unprivileged Node C runner and JNS gateway boundary.
"""
import argparse, datetime, hashlib, json, os, pathlib, re, subprocess, sys

TARGET=9906
NAME="haos18-golden"
EXPECTED={"base-9906-disk-0", "base-9906-disk-1"}
def call(args, timeout=30):
    try:
        return subprocess.run(args,text=True,capture_output=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):
        raise RuntimeError("command_unavailable_or_timeout")
def require(ok, reason):
    if not ok:raise RuntimeError(reason)
def output(data):
    print("JNS_VM9906_RETIREMENT="+json.dumps(data,sort_keys=True),flush=True)
def lvs():
    p=call(["lvs","--noheadings","--separator","|","-o",
            "vg_name,lv_name,origin,lv_size,data_percent"],25)
    require(p.returncode==0,"lvm_inventory_unavailable")
    ret=[]
    for row in p.stdout.splitlines():
        bits=[x.strip() for x in row.split("|")]
        if len(bits)>=5 and bits[0]=="pve":
            ret.append({"name":bits[1],"origin":bits[2],
                        "size":bits[3],"pct":bits[4]})
    return ret
def check():
    require(os.uname().nodename.split(".")[0]=="nodec","wrong_host")
    require(os.geteuid()==0,"requires_local_privileged_proxmox_operator")
    require(not pathlib.Path("/etc/pve/corosync.conf").exists(),
            "clustered_state_requires_separate_change_plan")
    stat=call(["qm","status",str(TARGET)])
    require(stat.returncode==0 and stat.stdout.strip()=="status: stopped",
            "template_not_stopped")
    conf=call(["qm","config",str(TARGET)])
    require(conf.returncode==0,"config_unavailable")
    c=conf.stdout
    require(bool(re.search(r"^name:\s*"+re.escape(NAME)+r"\s*$",c,re.M)),
            "wrong_template_identity")
    require(bool(re.search(r"^template:\s*1\s*$",c,re.M)),
            "vm_is_not_a_template")
    require(not re.search(r"^(?:lock|protection):\s*(?!0\s*$)",c,re.M),
            "template_locked_or_protected")
    require(not re.search(r"^onboot:\s*1\s*$",c,re.M),"autostart_enabled")
    diskrows=re.findall(r"^(?:efidisk|scsi|sata|virtio|unused)\d+:\s*([^\n]+)",c,re.M)
    disks=[]
    for line in diskrows:
        match=re.search(r"local-lvm:(base-9906-disk-[01])(?:,|\s|$)",line)
        require(bool(match),"unexpected_storage_or_disk_reference")
        disks.append(match.group(1))
    require(set(disks)==EXPECTED and len(disks)==2,"unexpected_disk_layout")
    volumes=lvs()
    own=[v for v in volumes if v["name"] in EXPECTED]
    require(len(own)==2,"template_volumes_missing")
    dependent=[v for v in volumes if v["origin"] in EXPECTED]
    require(not dependent,"dependent_linked_clones_exist")
    configs=pathlib.Path("/etc/pve/qemu-server")
    require(configs.is_dir(),"proxmox_config_dir_unavailable")
    other_refs=[]
    for p in configs.glob("*.conf"):
        if p.name==str(TARGET)+".conf":continue
        try:t=p.read_text()
        except OSError:raise RuntimeError("cannot_check_all_vm_configs")
        if any(v in t for v in EXPECTED):other_refs.append(p.name)
    require(not other_refs,"other_vm_config_references_template_disks")
    return {"host":"nodec","vmid":TARGET,"name":NAME,"stopped":True,
            "template":True,"onboot_disabled":True,"disks":len(disks),
            "dependent_linked_volumes":0,"foreign_config_references":0,
            "config_sha256":hashlib.sha256(c.encode()).hexdigest()},c
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--execute",action="store_true",
        help="Destroy ONLY VM9906 once all preflight checks pass")
    args=p.parse_args()
    try:
        evidence,c=check()
        output({"stage":"preflight_passed",**{k:v for k,v in evidence.items() if k!="config_sha256"},
                "execute_requested":args.execute})
        if not args.execute:
            return 0
        # Save small, root-only source configuration for audit and troubleshooting.
        target=pathlib.Path("/var/lib/jns-solar/vm9906-retirement-20261028")
        require(not target.exists() and not target.is_symlink(),
                "audit_dir_already_exists")
        target.mkdir(parents=True,mode=0o700)
        cfg=target/"vm9906-original.conf"
        with cfg.open("x") as f:f.write(c)
        cfg.chmod(0o600)
        manifest=target/"preflight.json"
        with manifest.open("x") as f:
            json.dump(evidence,f,sort_keys=True,indent=2);f.write("\n")
        manifest.chmod(0o600)
        # Revalidate identity and dependencies immediately before destruction.
        evidence2,_=check()
        require(evidence2["config_sha256"]==evidence["config_sha256"],
                "configuration_changed_during_preflight")
        action=call(["qm","destroy",str(TARGET),"--purge","1"],210)
        if action.returncode:
            (target/"failure.txt").write_text(action.stderr[-4096:])
            (target/"failure.txt").chmod(0o600)
            raise RuntimeError("qm_destroy_failed")
        post=call(["qm","status",str(TARGET)])
        require(post.returncode!=0,"vm_entry_still_exists")
        remaining=[v for v in lvs() if v["name"] in EXPECTED]
        require(not remaining,"template_disks_remain_after_qm_destroy")
        done={"vmid":TARGET,"host":"nodec","removed":True,
              "template_disks_removed":True,"other_vms_untouched":True,
              "completed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
        fn=target/"completion.json"
        with fn.open("x") as f:
            json.dump(done,f,sort_keys=True,indent=2);f.write("\n")
        fn.chmod(0o600)
        output({"stage":"verified_removed",**done})
        return 0
    except RuntimeError as e:
        output({"stage":"blocked_or_incomplete","reason":str(e),
                "vmid":TARGET,"host":os.uname().nodename.split(".")[0]})
        return 1
if __name__=="__main__":
    sys.exit(main())
