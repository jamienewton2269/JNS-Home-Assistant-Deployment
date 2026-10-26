#!/usr/bin/env python3
"""Cold-stages crash-consistent ZFS source snapshots of LIVE VM903 and VM905
on Node A without touching or overwriting Node A's stale guest configs.
No VM starts/stops/destroy/restore or network changes. Full config saved
privately. Snapshots are preliminary, not a quiesced final cutover.
"""
import hashlib,json,os,re,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
TAG="jns-solar-cluster-prep-20261026-v1"
VM_NAMES={903:"ha-s1-plant",905:"ha-s2-general"}
def fail(code):
 print("JNS_VM_EVAC_STAGE_BLOCKED="+code,flush=True);sys.exit(1)
def remote(host,command,timeout=35):
 try:r=subprocess.run(SSH+[host,shlex.join(["bash","-c",command])],
   stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):fail("REMOTE_TIMEOUT")
 if r.returncode:fail(host+"_RC_"+str(r.returncode))
 return r.stdout.decode("utf-8","replace").strip()
def base_check(vm,name):
 src='''set -Eeuo pipefail
test "$(hostname -s)" = nodeb
test "$(qm status __VM__)" = 'status: running'
config="$(qm config __VM__)"
printf '%s\\n' "$config" | grep -Fxq 'name: __NAME__'
printf '%s\\n' "$config" | grep -Eq '^scsi0: vmdata:vm-__VM__-disk-1,'
printf '%s\\n' "$config" | grep -Eq '^efidisk0: vmdata:vm-__VM__-disk-0,'
if printf '%s\\n' "$config" | grep -Eq '^(hostpci[0-9]+|usb[0-9]+|args|hookscript|virtiofs[0-9]+):'; then exit 72; fi
for n in 0 1; do
 test "$(zfs list -Hp -o type vmdata/vm-__VM__-disk-$n)" = volume
 test ! -e /dev/null/invalid
 if zfs list -H -t snapshot vmdata/vm-__VM__-disk-$n@__TAG__ >/dev/null 2>&1; then exit 73; fi
done
echo SOURCE_READY
'''
 src=src.replace("__VM__",str(vm)).replace("__NAME__",name).replace("__TAG__",TAG)
 if "SOURCE_READY" not in remote("nodeb",src):fail("BAD_SOURCE_GUEST_"+str(vm))
 dst='''set -Eeuo pipefail
test "$(hostname -s)" = nodea
test "$(qm status __VM__)" = 'status: stopped'
test "$(qm config __VM__ | sed -n 's/^onboot: //p')" = 0
test "$(zfs list -Hp -o available vmdata)" -gt 107374182400
test "$(free -m | awk '/^Mem:/ {print $7}')" -gt 1400
for n in 0 1; do
 if zfs list -H vmdata/jns-solar-staging-__VM__-disk-$n-20261026 >/dev/null 2>&1; then exit 75; fi
done
test ! -e /var/lib/jns-solar/cluster-evacuation/nodeb-vm__VM__.conf
install -d -m 0700 /var/lib/jns-solar/cluster-evacuation
echo TARGET_READY
'''
 dst=dst.replace("__VM__",str(vm))
 if "TARGET_READY" not in remote("nodea",dst):fail("DESTINATION_COLLISION_"+str(vm))
def private_config(vm):
 # Existing Proxmox definitions include MACs; keep them private, never in CI logs.
 command=SSH+["nodeb",shlex.join(["cat","/etc/pve/qemu-server/"+str(vm)+".conf"])]
 try:p=subprocess.run(command,capture_output=True,timeout=20)
 except (OSError,subprocess.TimeoutExpired):fail("CONFIG_READ_TIMEOUT")
 if p.returncode or len(p.stdout)>256*1024 or not p.stdout:fail("CONFIG_SOURCE_UNAVAILABLE")
 content=p.stdout;digest=hashlib.sha256(content).hexdigest()
 dest="/var/lib/jns-solar/cluster-evacuation/nodeb-vm"+str(vm)+".conf"
 try:
  receiver=subprocess.run(SSH+["nodea",shlex.join(["bash","-c","umask 077; cat > "+shlex.quote(dest)])],
        input=content,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=25)
 except (OSError,subprocess.TimeoutExpired):fail("CONFIG_TRANSFER_TIMEOUT")
 if receiver.returncode:fail("CONFIG_TRANSFER_FAILED")
 verify='test "$(sha256sum '+shlex.quote(dest)+''' | awk '{print $1}')" = '''+shlex.quote(digest)+''' && test "$(stat -c %a '''+shlex.quote(dest)+''')" = 600 && echo VERIFIED'''
 if "VERIFIED" not in remote("nodea",verify):fail("CONFIG_HASH_MISMATCH")
 print("VM"+str(vm)+"_PROXMOX_CONFIG_COPIED_PRIVATE=yes",flush=True)
 print("VM"+str(vm)+"_CONFIG_SHA256="+digest,flush=True)
def transfer_disk(vm,n):
 source="vmdata/vm-"+str(vm)+"-disk-"+str(n)
 target="vmdata/jns-solar-staging-"+str(vm)+"-disk-"+str(n)+"-20261026"
 snap=source+"@"+TAG
 remote("nodeb","zfs snapshot "+shlex.quote(snap),25)
 guid=remote("nodeb","zfs get -H -o value guid "+shlex.quote(snap))
 if not guid.isdigit():fail("BAD_SOURCE_GUID")
 try:
  sender=subprocess.Popen(SSH+["nodeb",shlex.join(["zfs","send","-p","-c",snap])],
    stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  recv=subprocess.Popen(SSH+["nodea",shlex.join(["zfs","receive","-u",
    "-o","volmode=none","-o","readonly=on",target])],
    stdin=sender.stdout,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  sender.stdout.close()
  rc=recv.wait(timeout=1100);sc=sender.wait(timeout=1100)
 except (OSError,subprocess.TimeoutExpired):fail("ZFS_STREAM_TIMEOUT_"+str(vm))
 if rc or sc:fail("ZFS_STREAM_FAILED_"+str(vm)+"_DISK"+str(n))
 verify='''set -Eeuo pipefail
test "$(zfs get -H -o value guid '''+shlex.quote(target+"@"+TAG)+''')" = '''+shlex.quote(guid)+'''
test "$(zfs get -H -o value volmode '''+shlex.quote(target)+''')" = none
test "$(zfs get -H -o value readonly '''+shlex.quote(target)+''')" = on
test "$(qm status '''+str(vm)+''')" = 'status: stopped'
echo VERIFIED
'''
 if "VERIFIED" not in remote("nodea",verify,30):fail("VERIFICATION_FAILED_"+str(vm)+"_"+str(n))
 print("VM"+str(vm)+"_DISK"+str(n)+"_SNAPSHOT_GUID_MATCH=yes",flush=True)
 print("VM"+str(vm)+"_DISK"+str(n)+"_OFFLINE_ZVOL_STAGE=yes",flush=True)
def main():
 print("JNS_VM903_VM905_COLD_STAGING_START",flush=True)
 for vm,name in VM_NAMES.items():base_check(vm,name)
 for vm,name in VM_NAMES.items():
  private_config(vm)
  for disk in (0,1):transfer_disk(vm,disk)
 print("JNS_VM903_VM905_COLD_STAGING_COMPLETED=yes",flush=True)
 print("NODE_B_LIVE_GUESTS_UNCHANGED=yes",flush=True)
 print("NODE_A_STOPPED_GUEST_CONFIGS_UNCHANGED=yes",flush=True)
 print("FINAL_CONSISTENT_BACKUP_AND_RAM_UPGRADE_PENDING=yes",flush=True)
if __name__=="__main__":main()
