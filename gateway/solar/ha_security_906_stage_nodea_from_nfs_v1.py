#!/usr/bin/env python3
"""JNS VM906: guarded preliminary NFS-to-NodeA offline restore.

Run as root on Node C after ha_security_906_source_prebackup_nodec_v1.sh.
Preserves live source VM906. Copies SHA-256 pinned NFS VMA and restores a
stopped, onboot=0 guest on Node A. Does NOT promote/start duplicate security.
"""
import hashlib,json,os,pathlib,re,shlex,subprocess,sys,time
BASE=pathlib.Path("/mnt/pve/nfs-ct/JNS-Solar-Archives/HA-Security-906")
DST="/var/lib/jns-solar/ha-security-906/VM906-stage.vma.zst"
SSH=["runuser","-u","github-runner","--","ssh",
     "-o","BatchMode=yes","-o","ConnectTimeout=6",
     "-o","StrictHostKeyChecking=yes","nodea"]
def fail(s):
 print("VM906_OFFLINE_RESTORE_BLOCKED="+s,flush=True);sys.exit(1)
def local(a,timeout=20):
 try:r=subprocess.run(a,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):fail("local_command_timeout")
 if r.returncode:fail("local_command_error_"+str(r.returncode))
 return r.stdout
def remote(script,timeout=40):
 try:r=subprocess.run(SSH+[shlex.join(["bash","-c",script])],
       capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):fail("nodea_connection_timeout")
 if r.returncode:fail("nodea_validation_or_restore_rc_"+str(r.returncode))
 return r.stdout
def sha_file(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  while True:
   b=f.read(4*1024**2)
   if not b:break
   h.update(b)
 return h.hexdigest()
def newest():
 if not BASE.is_dir() or BASE.is_symlink():fail("NFS_BACKUP_FOLDER_ABSENT")
 entries=sorted(BASE.glob("source-snapshot-*"),reverse=True)
 for folder in entries:
  if folder.is_symlink() or not folder.is_dir():continue
  mf=folder/"MANIFEST.json"
  if mf.is_symlink() or not mf.is_file():continue
  try:m=json.loads(mf.read_text())
  except (OSError,ValueError):continue
  if m.get("schema")!="jns.solar.vm906.source-snapshot.v1" or m.get("vmid")!=906:continue
  if time.time()-mf.stat().st_mtime>3600:continue
  name=m.get("archive_name")
  if not isinstance(name,str) or not re.fullmatch(r"vzdump-qemu-906-[0-9_-]+\.vma\.zst",name):continue
  src=folder/name
  if src.is_symlink() or not src.is_file() or src.stat().st_size!=m.get("bytes"):continue
  if not re.fullmatch(r"[a-f0-9]{64}",m.get("sha256","")):continue
  if sha_file(src)!=m["sha256"]:fail("BACKUP_RECHECK_SHA_MISMATCH")
  return src,m
 fail("NO_RECENT_VERIFIED_NFS_ARCHIVE")
def main():
 if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodec":
  fail("MUST_RUN_FROM_NODEC_ROOT")
 if "status: running" not in local(["qm","status","906"]):
  fail("NODEC_SOURCE_NOT_RUNNING")
 if not subprocess.run(["findmnt","-rn","-M","/mnt/pve/nfs-ct"],
    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
  fail("NFS_NOT_MOUNTED")
 src,m=newest()
 gate=r'''
set -Eeuo pipefail
test "$(hostname -s)" = nodea
test ! -e /etc/pve/qemu-server/906.conf
if qm config 906 >/dev/null 2>&1; then exit 77; fi
test "$(qm status 900)" = "status: stopped"
memory="$(free -m | awk '/^Mem:/ {print $7}')"
test "$memory" -ge 3150
freebytes="$(zfs list -Hp -o available vmdata)"
test "$freebytes" -ge 68719476736
test ! -e /var/lib/jns-solar/ha-security-906/VM906-stage.vma.zst
test ! -e /var/lib/jns-solar/ha-security-906/VM906-stage.vma.zst.partial
install -d -m 0700 /var/lib/jns-solar/ha-security-906
echo NODEA_OFFLINE_RESTORE_GATE_OK
'''
 if "NODEA_OFFLINE_RESTORE_GATE_OK" not in remote(gate,30):
  fail("NODEA_PRECHECK_MISSING_MARKER")
 print("VM906_NFS_TO_NODEA_PRIVATE_TRANSFER_STARTED=yes",flush=True)
 # Transfer as a pipe; Node C root owns source, NodeA destination owned by root.
 try:
  with src.open("rb") as f:
   process=subprocess.Popen(SSH+[shlex.join(["bash","-c",
     "umask 077; cat > "+shlex.quote(DST+".partial")])],
     stdin=f,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   ret=process.wait(timeout=1000)
 except (OSError,subprocess.TimeoutExpired):fail("ARCHIVE_TRANSFER_TIMEOUT")
 if ret!=0:fail("ARCHIVE_TRANSFER_FAILED")
 hashval=m["sha256"]
 size=m["bytes"]
 restore=r'''
set -Eeuo pipefail
target=__TARGET__
partial="$target.partial"
test "$(stat -c %s "$partial")" = __SIZE__
test "$(sha256sum "$partial" | awk '{print $1}')" = __SHA__
chmod 0600 "$partial"
mv -- "$partial" "$target"
test ! -e /etc/pve/qemu-server/906.conf
if ! timeout 1500 qmrestore "$target" 906 --storage vmdata --unique 0 \
   > /var/lib/jns-solar/ha-security-906/private-restore.log 2>&1; then
 echo OFFLINE_RESTORE_COMMAND_FAILED
 exit 81
fi
qm set 906 --onboot 0 >/dev/null
test "$(qm status 906)" = "status: stopped"
test "$(qm config 906 | sed -n 's/^onboot: //p')" = 0
test "$(qm config 906 | sed -n 's/^name: //p')" = "ha-security"
echo NODEA_VM906_OFFLINE_RESTORE_OK
'''
 restore=restore.replace("__TARGET__",shlex.quote(DST)).replace("__SIZE__",str(size)).replace("__SHA__",shlex.quote(hashval))
 if "NODEA_VM906_OFFLINE_RESTORE_OK" not in remote(restore,1640):
  fail("RESTORE_COMPLETED_BUT_POSTCHECK_FAILED")
 if "status: running" not in local(["qm","status","906"]):
  fail("NODEC_SOURCE_STATE_CHANGED")
 print("VM906_NODEA_STAGED_OFFLINE=yes",flush=True)
 print("VM906_NODEA_ONBOOT_DISABLED=yes",flush=True)
 print("VM906_SOURCE_NODEC_STILL_RUNNING=yes",flush=True)
 print("VM906_NODEA_ARCHIVE_SHA256="+hashval,flush=True)
 print("VM906_NOT_YET_CUTOVER=yes",flush=True)
if __name__=="__main__":main()
