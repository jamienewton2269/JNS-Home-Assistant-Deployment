#!/usr/bin/env python3
"""User-authorised JNS VM906 Node C -> Node A cold migration.

Execute once as ROOT on Node C. No GitHub runner sudo broadening.
Back up a QUIESCED VM906 to Node C NFS, SHA256-copy to Node A, restore
same identity, start only once old source is off, validate HA HTTP and
roll back automatically to Node C on failure. Never deletes the source.
"""
import datetime
import hashlib
import json
import os
import pathlib
import re
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

VM=906
SOURCE="nodec"
DEST="nodea"
RUNNER="github-runner"
DNS="ha-security.home.arpa"
NFS=pathlib.Path("/mnt/pve/nfs-ct")
ROOT=NFS/"JNS-Solar-Archives"/"HA-Security-906"
SSH=["runuser","-u",RUNNER,"--","ssh",
     "-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
     "-o","ConnectTimeout=6",DEST]
pre_stop=False
dest_started=False
original_onboot="1"
backup_dir=None

def note(s):
    print("JNS_VM906_"+s,flush=True)
def call(argv,timeout=30,log=None,check=True):
    try:
        if log is None:
            r=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
        else:
            with open(log,"w") as f:
                r=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as e:
        raise RuntimeError("command_timeout_or_io:"+type(e).__name__) from None
    if check and r.returncode:
        raise RuntimeError("command_failed_rc_"+str(r.returncode))
    return r
def nodea(script,timeout=45):
    result=call(SSH+[shlex.join(["bash","-c",script])],timeout=timeout)
    return result.stdout
def qstate():
    return call(["qm","status",str(VM)],12).stdout.strip()
def source_cfg():
    return call(["qm","config",str(VM)],12).stdout
def dig(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for buf in iter(lambda:f.read(4*1024*1024),b""):
            h.update(buf)
    return h.hexdigest()

def preflight():
    global original_onboot
    if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!=SOURCE:
        raise RuntimeError("requires_nodec_root")
    if qstate()!="status: running":
        raise RuntimeError("source_vm906_not_running")
    cfg=source_cfg()
    if not re.search(r"^name:\s+ha-security\s*$",cfg,re.M):
        raise RuntimeError("wrong_source_vm_identity")
    if not re.search(r"^scsi0:\s+",cfg,re.M) or not re.search(r"^net0:\s+",cfg,re.M):
        raise RuntimeError("missing_disk_or_network")
    if re.search(r"^(usb\d+|hostpci\d+|args|hookscript|virtiofs\d+):",cfg,re.M):
        raise RuntimeError("host_passthrough_must_be_reviewed")
    original_onboot=(re.search(r"^onboot:\s+([01])",cfg,re.M).group(1)
                     if re.search(r"^onboot:\s+([01])",cfg,re.M) else "0")
    if call(["findmnt","-rn","-M",str(NFS),"-t","nfs,nfs4"],10,check=False).returncode:
        raise RuntimeError("nfs_backup_mount_unavailable")
    stat=os.statvfs(NFS)
    if stat.f_bavail*stat.f_frsize < 80*1024**3:
        raise RuntimeError("nfs_less_than_80gib_available")
    if not pathlib.Path("/usr/sbin/vzdump").exists():
        raise RuntimeError("vzdump_unavailable")
    if not pathlib.Path("/usr/bin/runuser").exists():
        raise RuntimeError("runuser_unavailable")
    if call(["id","-u",RUNNER],5,check=False).returncode:
        raise RuntimeError("runner_account_unavailable")
    shell=r'''
set -Eeuo pipefail
test "$(hostname -s)" = nodea
test ! -e /etc/pve/qemu-server/906.conf
if qm config 906 >/dev/null 2>&1; then exit 74; fi
test -d /sys/class/net/vmbr0
test "$(free -m | awk '/^Mem:/ {print $7}')" -ge 3100
test "$(zfs list -Hp -o available vmdata)" -ge 68719476736
test ! -e /var/lib/jns-solar/ha-security-906/migrated-906.vma.zst
test ! -e /var/lib/jns-solar/ha-security-906/migrated-906.vma.zst.partial
install -d -m 0700 /var/lib/jns-solar/ha-security-906
echo NODEA_READY
'''
    if "NODEA_READY" not in nodea(shell,40):
        raise RuntimeError("destination_gate_not_confirmed")
    note("SOURCE_AND_DESTINATION_PREFLIGHT_OK=yes")
    return cfg

def stop_source():
    global pre_stop
    # Prevent source automatic restart before stopping it.
    call(["qm","set",str(VM),"--onboot","0"],25)
    note("SOURCE_GRACEFUL_SHUTDOWN_REQUESTED=yes")
    attempt=call(["qm","shutdown",str(VM),"--timeout","150"],175,check=False)
    for i in range(24):
        if qstate()=="status: stopped":
            pre_stop=True
            note("SOURCE_STOPPED_CONFIRMED=yes")
            return
        time.sleep(2)
    raise RuntimeError("source_refused_graceful_shutdown_rc_"+str(attempt.returncode))

def make_backup(saved_cfg):
    global backup_dir
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    if ROOT.is_symlink():raise RuntimeError("unsafe_nfs_parent_symlink")
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir=ROOT/("cold-migration-"+stamp)
    backup_dir.mkdir(mode=0o700)
    original=backup_dir/"vm906-original.conf"
    with original.open("x") as f:f.write(saved_cfg)
    os.chmod(original,0o600)
    private_log=backup_dir/"private-vzdump.log"
    note("COLD_BACKUP_STARTED=yes")
    call(["vzdump",str(VM),"--mode","stop","--compress","zstd",
          "--dumpdir",str(backup_dir)],2100,log=private_log)
    files=list(backup_dir.glob("vzdump-qemu-906-*.vma.zst"))
    if len(files)!=1:raise RuntimeError("expected_one_vma_archive")
    archive=files[0]
    size=archive.stat().st_size
    if size<1024*1024 or size>80*1024**3:
        raise RuntimeError("unexpected_backup_size")
    os.chmod(archive,0o600)
    call(["zstd","-q","-t",str(archive)],1200,log=backup_dir/"private-zstd-check.log")
    digest=dig(archive)
    manifest={"format":"Proxmox VMA zstd","vmid":906,"source_node":SOURCE,
              "destination_node":DEST,"archive":archive.name,"size_bytes":size,
              "sha256":digest,"source_config_sha256":hashlib.sha256(saved_cfg.encode()).hexdigest(),
              "source_stopped_at_capture":True,"nfs_sha256_verified":True,
              "source_retained_for_rollback":True,
              "created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
    mf=backup_dir/"migration-manifest.json"
    with mf.open("x") as f:json.dump(manifest,f,indent=2,sort_keys=True);f.write("\n")
    os.chmod(mf,0o600)
    note("COLD_BACKUP_VERIFIED=yes")
    note("ARCHIVE_BYTES="+str(size))
    return archive,size,digest

def stream_archive(archive,size,digest):
    remote_path="/var/lib/jns-solar/ha-security-906/migrated-906.vma.zst"
    part=remote_path+".partial"
    note("ARCHIVE_COPY_TO_NODEA_STARTED=yes")
    try:
        with archive.open("rb") as infile:
            p=subprocess.run(SSH+[shlex.join(["bash","-c",
               "umask 077; cat > "+shlex.quote(part)])],
               stdin=infile,stdout=subprocess.DEVNULL,
               stderr=subprocess.DEVNULL,timeout=1500)
    except (OSError,subprocess.TimeoutExpired):
        raise RuntimeError("archive_transfer_timeout") from None
    if p.returncode:raise RuntimeError("archive_transfer_rc_"+str(p.returncode))
    verify=r'''
set -Eeuo pipefail
part=__PART__
dest=__DEST__
test "$(stat -c %s "$part")" = __SIZE__
test "$(sha256sum "$part" | awk '{print $1}')" = __HASH__
chmod 0600 "$part"
mv -- "$part" "$dest"
test ! -e /etc/pve/qemu-server/906.conf
echo COPY_VERIFIED
'''
    for token,val in [("__PART__",shlex.quote(part)),("__DEST__",shlex.quote(remote_path)),
                      ("__SIZE__",str(size)),("__HASH__",shlex.quote(digest))]:
        verify=verify.replace(token,val)
    if "COPY_VERIFIED" not in nodea(verify,150):
        raise RuntimeError("copy_verify_no_marker")
    note("ARCHIVE_SHA256_VERIFIED_ON_NODEA=yes")
    return remote_path

def restore_and_start(remote_path,saved_cfg):
    global dest_started
    note("NODEA_VM906_RESTORE_STARTED=yes")
    # Must first restore offline, preserve net0 and VM identity and disable onboot.
    restore=r'''
set -Eeuo pipefail
test ! -e /etc/pve/qemu-server/906.conf
if ! timeout 1600 qmrestore __PATH__ 906 --storage vmdata --unique 0 \
     > /var/lib/jns-solar/ha-security-906/private-restore.log 2>&1; then
  exit 81
fi
qm set 906 --onboot 0 >/dev/null
test "$(qm status 906)" = "status: stopped"
test "$(qm config 906 | sed -n 's/^onboot: //p')" = 0
test "$(qm config 906 | sed -n 's/^name: //p')" = ha-security
echo RESTORED_OFFLINE
'''.replace("__PATH__",shlex.quote(remote_path))
    if "RESTORED_OFFLINE" not in nodea(restore,1700):
        raise RuntimeError("restore_did_not_verify")
    note("NODEA_VM906_OFFLINE_RESTORE_VERIFIED=yes")
    original_net=re.search(r"^net0:\s*(.+)$",saved_cfg,re.M)
    config_text=nodea("qm config 906")
    target_net=re.search(r"^net0:\s*(.+)$",config_text,re.M)
    if not original_net or not target_net:
        raise RuntimeError("guest_net_adapter_missing_after_restore")
    old_mac=re.search(r"([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}",original_net.group(1))
    new_mac=re.search(r"([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}",target_net.group(1))
    if not old_mac or not new_mac or old_mac.group(0).casefold()!=new_mac.group(0).casefold():
        raise RuntimeError("guest_network_identity_mismatch")
    # Verify source still stopped immediately before VM906 starts on Node A.
    if qstate()!="status: stopped":raise RuntimeError("source_vm_started_again")
    if "NODEA_STARTED" not in nodea("set -e; test \"$(qm status 906)\" = 'status: stopped'; qm start 906 >/dev/null; test \"$(qm status 906)\" = 'status: running'; echo NODEA_STARTED",90):
        raise RuntimeError("nodea_start_not_confirmed")
    dest_started=True
    note("NODEA_VM906_STARTED=yes")

def target_ready():
    # Source is stopped, so an HTTPS/HTTP response for ha-security cannot be
    # from the original HA guest. DNS-first. No secrets supplied or printed.
    probe=r'''
python3 - <<'PY'
import socket,urllib.request,urllib.error
host="ha-security.home.arpa"
try:
 with socket.create_connection((host,8123),timeout=3):
  pass
except OSError:
 raise SystemExit(1)
try:
 with urllib.request.urlopen("http://"+host+":8123/",timeout=5) as req:
  code=req.status
except urllib.error.HTTPError as err:
 code=err.code
except Exception:
 raise SystemExit(1)
if code not in (200,301,302,303,307,308,401,403):raise SystemExit(1)
print("HA_SECURITY_HTTP_READY")
PY
'''
    note("NODEA_HA_SECURITY_HEALTH_CHECK_STARTED=yes")
    for _ in range(48):
        if qstate()!="status: stopped":
            raise RuntimeError("source_started_during_target_health_check")
        try:
            result=nodea(probe,18)
            if "HA_SECURITY_HTTP_READY" in result:
                return
        except Exception:
            pass
        time.sleep(10)
    raise RuntimeError("destination_ha_security_not_http_ready")

def commit():
    # Do not delete source on Node C: it is the user-approved rollback.
    nodea("set -e; test \"$(qm status 906)\" = 'status: running'; qm set 906 --onboot 1 >/dev/null; test \"$(qm config 906 | sed -n 's/^onboot: //p')\" = 1; echo NODEA_AUTOSTART_OK",45)
    if qstate()!="status: stopped":raise RuntimeError("nodec_source_not_stopped_at_commit")
    note("NODEA_VM906_PRIMARY_ONBOOT_ENABLED=yes")
    note("NODEC_VM906_ROLLBACK_STOPPED_ONBOOT_DISABLED=yes")
    note("NODEC_STEWARD_REMAINS_ON=yes")
    note("MIGRATION_SUCCESS=yes")
    note("SECURITY_ALARM_END_TO_END_TESTS_STILL_REQUIRED=yes")

def rollback():
    note("ROLLBACK_STARTED=yes")
    # If destination VM exists, stop it before attempting Node C source restart.
    try:
        states=nodea("qm status 906")
        if "status: running" in states:
            stop=r'''
qm shutdown 906 --timeout 90 >/dev/null 2>&1 || true
if test "$(qm status 906)" != "status: stopped"; then
 qm stop 906 --timeout 60 >/dev/null 2>&1 || true
fi
qm set 906 --onboot 0 >/dev/null
qm status 906
'''
            states=nodea(stop,190)
        if "status: running" in states:
            note("ROLLBACK_BLOCKED_TARGET_STILL_RUNNING=yes")
            return
    except Exception:
        note("ROLLBACK_BLOCKED_TARGET_STATE_UNKNOWN=yes")
        return
    try:
        if qstate()=="status: stopped":
            call(["qm","set",str(VM),"--onboot",original_onboot],20)
            call(["qm","start",str(VM)],120)
        note("NODEC_SOURCE_RESTORED="+("yes" if qstate()=="status: running" else "no"))
    except Exception:
        note("NODEC_SOURCE_RESTORE_FAILED_MANUAL_RECOVERY_NEEDED=yes")

def main():
    global pre_stop
    try:
        original=preflight()
        stop_source()
        archive,size,sha=make_backup(original)
        remote=stream_archive(archive,size,sha)
        restore_and_start(remote,original)
        target_ready()
        commit()
    except Exception as exc:
        note("MIGRATION_FAILED="+str(exc).replace(" ","_")[:150])
        # If graceful shutdown was requested but qstate became stopped later,
        # restore source only when no target is running.
        if pre_stop or qstate()=="status: stopped":
            rollback()
        else:
            try:call(["qm","set",str(VM),"--onboot",original_onboot],18)
            except Exception:pass
        sys.exit(1)
if __name__=="__main__":
    main()
