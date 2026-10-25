#!/usr/bin/env python3
"""JNS Solar user-authorised VM906 OFFLINE restoration from Node C NFS to Node A.

Never starts target or changes source. Expects exactly one pre-existing empty,
stopped VM906 placeholder on Node A; safely replaces it with a full Proxmox
VMA restore. Node A staging uses a transient dedicated ZFS dataset, not root.
Service cutover must happen separately after old Node C VM906 is off.
"""
import hashlib, json, os, pathlib, re, shlex, subprocess, sys, time
NFS=pathlib.Path("/mnt/pve/nfs-ct/JNS-Solar-Archives/HA-Security-906")
DATASET="vmdata/jns-solar-vm906-offline-restore-20261025"
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6","nodea"]
def block(code):
    print("VM906_OFFLINE_RESTORE_BLOCKED="+code,flush=True);sys.exit(1)
def remote(script,timeout=45):
    try:
        p=subprocess.run(SSH+[shlex.join(["bash","-c",script])],
            capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):block("remote_timeout")
    if p.returncode:
        print("VM906_REMOTE_EXIT="+str(p.returncode),flush=True)
        block("remote_preflight_or_operation_failed")
    return p.stdout
def find_backup():
    if NFS.is_symlink() or not NFS.is_dir():block("nfs_backup_dir_missing")
    found=[]
    for f in NFS.rglob("MANIFEST.json"):
        if f.is_symlink() or len(f.relative_to(NFS).parts)>3:continue
        try:m=json.loads(f.read_text())
        except (OSError,ValueError):continue
        if m.get("schema")!="jns.solar.vm906.source-snapshot.v1" or m.get("vmid")!=906:continue
        name=m.get("archive_name","")
        if not isinstance(name,str) or not re.fullmatch(r"vzdump-qemu-906-[0-9_-]+\.vma\.zst",name):
            continue
        data=f.parent/name
        if data.is_symlink() or not data.is_file():continue
        if not isinstance(m.get("bytes"),int) or data.stat().st_size!=m["bytes"]:continue
        if not re.fullmatch(r"[a-f0-9]{64}",m.get("sha256","")):continue
        if not m.get("zstd_integrity_passed"):continue
        found.append((data,m))
    if len(found)!=1:block("expected_exactly_one_verified_backup_"+str(len(found)))
    return found[0]
def local_ha_security_process():
    p=subprocess.run(["ps","-eo","args="],capture_output=True,text=True,timeout=10)
    return bool(p.returncode==0 and any(
        ("qemu-system" in l or "kvm " in l) and re.search(r" -id 906(?:\s|$)",l)
        for l in p.stdout.splitlines()))
def copy_to_nodea(src,m,dest):
    part=dest+".partial"
    print("VM906_NFS_TO_NODEA_TRANSFER_STARTED=yes",flush=True)
    try:
        with src.open("rb") as fh:
            p=subprocess.run(SSH+[shlex.join(["bash","-c",
                "umask 077; cat > "+shlex.quote(part)])],
                stdin=fh,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=1200)
    except (OSError,subprocess.TimeoutExpired):
        block("archive_transfer_timeout")
    if p.returncode:block("archive_transfer_failure")
    check="set -Eeuo pipefail; test \"$(stat -c %s "+shlex.quote(part)+")\" = "+str(m["bytes"])+"; test \"$(sha256sum "+shlex.quote(part)+" | awk '{print $1}')\" = "+shlex.quote(m["sha256"])+"; chmod 0600 "+shlex.quote(part)+"; mv -- "+shlex.quote(part)+" "+shlex.quote(dest)+"; echo TRANSFER_VERIFIED"
    if "TRANSFER_VERIFIED" not in remote(check,140):block("remote_sha_validation_failed")
    print("VM906_NODEA_ARCHIVE_SHA256_VERIFIED=yes",flush=True)
def main():
    if os.geteuid()==0 or os.uname().nodename.split(".")[0]!="nodec":
        block("expected_nodec_unprivileged_gateway_runner")
    if subprocess.run(["findmnt","-rn","-M","/mnt/pve/nfs-ct"],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        block("nfs_unmounted")
    if not local_ha_security_process():block("nodec_source_not_confirmed_running")
    src,m=find_backup()
    print("VM906_NFS_ARCHIVE_BYTES="+str(m["bytes"]),flush=True)
    print("VM906_SOURCE_NODEC_STILL_RUNNING=yes",flush=True)
    gate=r'''
set -Eeuo pipefail
test "$(hostname -s)" = nodea
test -f /etc/pve/qemu-server/906.conf
test "$(stat -c %s /etc/pve/qemu-server/906.conf)" = 0
test "$(qm status 906)" = "status: stopped"
test "$(zfs list -H -o name -t volume 2>/dev/null | grep -Ec '(^|/)vm-906-disk-[0-9]+$' || true)" = 0
if zfs list -H __DATASET__ >/dev/null 2>&1; then exit 78; fi
test "$(free -m | awk '/^Mem:/ {print $7}')" -ge 2700
test "$(zfs list -Hp -o available vmdata)" -ge 68719476736
test -e /dev/zvol/vmdata || test -d /dev/zvol/vmdata
echo VM906_EMPTY_PLACEHOLDER_CONFIRMED
'''
    gate=gate.replace("__DATASET__",shlex.quote(DATASET))
    if "VM906_EMPTY_PLACEHOLDER_CONFIRMED" not in remote(gate,50):
        block("nodea_placeholder_gate")
    prepare=r'''
set -Eeuo pipefail
test "$(hostname -s)" = nodea
test "$(stat -c %s /etc/pve/qemu-server/906.conf)" = 0
test "$(qm status 906)" = "status: stopped"
zfs create -o compression=zstd -o atime=off __DATASET__
path="$(zfs get -H -o value mountpoint __DATASET__)"
test -d "$path" && test "$path" != /
chmod 0700 "$path"
printf 'STAGE_PATH=%s\n' "$path"
'''.replace("__DATASET__",shlex.quote(DATASET))
    out=remote(prepare,55)
    lines=[x.split("=",1)[1] for x in out.splitlines() if x.startswith("STAGE_PATH=")]
    if len(lines)!=1 or not re.fullmatch(r"/[a-zA-Z0-9_./-]+",lines[0]):
        block("nodea_staging_mount_missing")
    path=lines[0]
    dest=path+"/vm906-source-backup.vma.zst"
    copy_to_nodea(src,m,dest)
    # Exactly the pre-existing empty, stopped guest must be removed first.
    # Never operate on a guest with any actual configuration or existing disks.
    restore=r'''
set -Eeuo pipefail
test "$(hostname -s)" = nodea
test "$(stat -c %s /etc/pve/qemu-server/906.conf)" = 0
test "$(qm status 906)" = "status: stopped"
test "$(zfs list -H -o name -t volume 2>/dev/null | grep -Ec '(^|/)vm-906-disk-[0-9]+$' || true)" = 0
qm destroy 906 --purge 1 --destroy-unreferenced-disks 0 > __LOGDIR__/empty-placeholder-removal.log 2>&1
test ! -e /etc/pve/qemu-server/906.conf
if ! timeout 1600 qmrestore __ARCHIVE__ 906 --storage vmdata --unique 0 > __LOGDIR__/offline-restore-private.log 2>&1; then
  if qm config 906 >/dev/null 2>&1; then qm set 906 --onboot 0 >/dev/null || true; fi
  exit 82
fi
qm set 906 --onboot 0 >/dev/null
test "$(qm status 906)" = "status: stopped"
test "$(qm config 906 | sed -n 's/^onboot: //p')" = 0
test "$(qm config 906 | sed -n 's/^name: //p')" = ha-security
test "$(qm config 906 | grep -Ec '^(scsi|sata|virtio)[0-9]+:')" -ge 1
test "$(qm config 906 | grep -Ec '^net[0-9]+:')" -ge 1
echo VM906_NODEA_OFFLINE_RESTORE_VALIDATED
'''
    restore=restore.replace("__ARCHIVE__",shlex.quote(dest)).replace("__LOGDIR__",shlex.quote(path))
    result=remote(restore,1690)
    if "VM906_NODEA_OFFLINE_RESTORE_VALIDATED" not in result:block("nodea_offline_restore_verification")
    print("VM906_NODEA_RESTORED_STOPPED=yes",flush=True)
    print("VM906_NODEA_ONBOOT_DISABLED=yes",flush=True)
    # Keep temporary archive only in durable NFS, reclaim transient Node A staging.
    cleanup="set -Eeuo pipefail; test \"$(qm status 906)\" = 'status: stopped'; test \"$(qm config 906 | sed -n 's/^onboot: //p')\" = 0; zfs destroy "+shlex.quote(DATASET)+"; echo RESTORE_STAGE_CLEANED"
    if "RESTORE_STAGE_CLEANED" in remote(cleanup,60):
        print("VM906_NODEA_TEMP_STORAGE_RELEASED=yes",flush=True)
    if not local_ha_security_process():
        block("source_nodec_changed_during_restoration")
    print("VM906_NODEC_REMAINS_ACTIVE=yes",flush=True)
    print("VM906_LIVE_CUTOVER_NOT_PERFORMED=yes",flush=True)
    print("VM906_OFFLINE_RESTORE_SUCCESS=yes",flush=True)
if __name__=="__main__":main()
