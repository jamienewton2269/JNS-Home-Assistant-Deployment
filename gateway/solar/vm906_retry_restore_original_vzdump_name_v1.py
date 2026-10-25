#!/usr/bin/env python3
"""JNS Solar: resume offline VM906 Proxmox restore from checksum-verified local archive.

Existing transfer stage has generic filename that qmrestore does not recognise.
This script restores original vzdump-qemu-906-*.vma.zst basename, then reruns
qmrestore. Only a stopped VM906 containing the exact onboot-only failed-restore
placeholder may be overwritten. Node C source remains running/untouched.
"""
import json,os,pathlib,re,shlex,subprocess,sys
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6","nodea"]
NFS=pathlib.Path("/mnt/pve/nfs-ct/JNS-Solar-Archives/HA-Security-906")
STAGE="vmdata/jns-solar-vm906-offline-restore-20261025"
def fail(msg):
    print("VM906_RESTORE_RETRY_BLOCKED="+msg,flush=True);sys.exit(1)
def remote(script,timeout=45):
    try:p=subprocess.run(SSH+[shlex.join(["bash","-c",script])],
             capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):fail("remote_timeout")
    if p.returncode:
        print("VM906_RESTORE_RETRY_REMOTE_EXIT="+str(p.returncode),flush=True)
        fail("restore_command_failed")
    return p.stdout
def find_manifest():
    hits=[]
    for f in NFS.rglob("MANIFEST.json"):
        if not f.is_file() or f.is_symlink():continue
        try:m=json.loads(f.read_text())
        except (OSError,ValueError):continue
        if m.get("schema")!="jns.solar.vm906.source-snapshot.v1" or m.get("vmid")!=906:continue
        name=m.get("archive_name")
        if not isinstance(name,str) or not re.fullmatch(r"vzdump-qemu-906-[0-9_-]+\.vma\.zst",name):continue
        if not re.fullmatch(r"[0-9a-f]{64}",m.get("sha256","")):continue
        if not isinstance(m.get("bytes"),int):continue
        hits.append(m)
    if len(hits)!=1:fail("source_manifest_not_unique")
    return hits[0]
def main():
    if os.geteuid()==0 or os.uname().nodename.split(".")[0]!="nodec":
        fail("expected_nodec_github_runner")
    m=find_manifest()
    old="vm906-source-backup.vma.zst"
    new=m["archive_name"]
    sha=m["sha256"]
    size=m["bytes"]
    pre=r'''
set -Eeuo pipefail
test "$(hostname -s)" = nodea
test "$(qm status 906)" = 'status: stopped'
test "$(stat -c %s /etc/pve/qemu-server/906.conf)" = 10
test "$(cat /etc/pve/qemu-server/906.conf)" = 'onboot: 0'
test "$(zfs list -H -o name -t volume 2>/dev/null | grep -Ec '(^|/)vm-906-disk-[0-9]+$' || true)" = 0
stage="$(zfs get -H -o value mountpoint __STAGE__)"
test -d "$stage" && test "$stage" != /
test -f "$stage/__OLD__"
test ! -e "$stage/__NEW__"
test "$(stat -c %s "$stage/__OLD__")" = __SIZE__
test "$(sha256sum "$stage/__OLD__" | awk '{print $1}')" = __SHA__
mv "$stage/__OLD__" "$stage/__NEW__"
echo VM906_RESTORE_ARCHIVE_NAME_CORRECTED
'''
    for k,v in [("__STAGE__",shlex.quote(STAGE)),
                 ("__OLD__",old),("__NEW__",new),
                 ("__SIZE__",str(size)),("__SHA__",shlex.quote(sha))]:
        pre=pre.replace(k,v)
    if "VM906_RESTORE_ARCHIVE_NAME_CORRECTED" not in remote(pre,180):
        fail("original_archive_basename_preflight")
    print("VM906_ARCHIVE_FILENAME_CORRECTED=yes",flush=True)
    restore=r'''
set -Eeuo pipefail
test "$(qm status 906)" = 'status: stopped'
test "$(cat /etc/pve/qemu-server/906.conf)" = 'onboot: 0'
test "$(zfs list -H -o name -t volume 2>/dev/null | grep -Ec '(^|/)vm-906-disk-[0-9]+$' || true)" = 0
stage="$(zfs get -H -o value mountpoint __STAGE__)"
archive="$stage/__NEW__"
test -f "$archive"
qm destroy 906 --purge 1 --destroy-unreferenced-disks 0 >"$stage/private-empty-entry-delete.log" 2>&1
test ! -e /etc/pve/qemu-server/906.conf
if ! timeout 1600 qmrestore "$archive" 906 --storage vmdata --unique 0 >"$stage/private-second-restore.log" 2>&1; then
   if qm config 906 >/dev/null 2>&1; then qm set 906 --onboot 0 >/dev/null || true; fi
   exit 82
fi
qm set 906 --onboot 0 >/dev/null
test "$(qm status 906)" = 'status: stopped'
test "$(qm config 906 | sed -n 's/^name: //p')" = ha-security
test "$(qm config 906 | sed -n 's/^onboot: //p')" = 0
test "$(qm config 906 | grep -Ec '^(scsi|virtio|sata)[0-9]+:')" -ge 1
test "$(qm config 906 | grep -Ec '^net[0-9]+:')" -ge 1
echo VM906_ON_NODEA_OFFLINE_VALIDATED
'''
    restore=restore.replace("__STAGE__",shlex.quote(STAGE)).replace("__NEW__",new)
    if "VM906_ON_NODEA_OFFLINE_VALIDATED" not in remote(restore,1690):
        fail("second_qmrestore_not_validated")
    print("VM906_OFFLINE_RESTORED_ON_NODEA=yes",flush=True)
    print("VM906_ON_NODEA_STOPPED=yes",flush=True)
    print("VM906_AUTOSTART_NODEA_DISABLED=yes",flush=True)
    cleanup=r'''
set -Eeuo pipefail
test "$(qm status 906)" = 'status: stopped'
test "$(qm config 906 | sed -n 's/^onboot: //p')" = 0
zfs destroy __STAGE__
echo VM906_TEMP_DATASET_REMOVED
'''.replace("__STAGE__",shlex.quote(STAGE))
    try:
        if "VM906_TEMP_DATASET_REMOVED" in remote(cleanup,80):
            print("VM906_NODEA_TEMP_ARCHIVE_REMOVED=yes",flush=True)
    except SystemExit:
        print("VM906_NODEA_TEMP_ARCHIVE_REMOVAL_UNCONFIRMED=yes",flush=True)
    print("VM906_LIVE_CUTOVER_NOT_PERFORMED=yes",flush=True)
    print("VM906_RETRY_SUCCESS=yes",flush=True)
if __name__=="__main__":main()
