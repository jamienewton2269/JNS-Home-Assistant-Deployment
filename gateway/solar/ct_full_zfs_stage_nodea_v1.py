#!/usr/bin/env python3
"""Solar: transfer complete read-only-at-receive ZFS LXC filesystem snapshots B->A.

Each source continues RUNNING unchanged. ZFS source snapshots are created,
sent through strict SSH, and received as NOT-MOUNTED, CANMOUNT=OFF datasets
with names never registered to Proxmox. Destination CT230/231 remain absent.
This is staging, NOT a clean final service-state cutover.
"""
import re,shlex,subprocess,sys
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
PAIRS=[
  (212,"mqtt-infra-a",230,"vmdata/jns-solar-coldstage-mqtt-20261024"),
  (214,"zigbee2mqtt-a",231,"vmdata/jns-solar-coldstage-zigbee-20261024")
]
SNAP="jns-solar-stage-20261024-v1"
def fail(tag):
 print("JNS_SOLAR_ZFS_MOVE_STAGE_BLOCKED="+tag,flush=True);sys.exit(1)
def run(host,cmd,timeout=30):
 try:p=subprocess.run(SSH+[host,shlex.join(cmd)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):fail("ssh_timeout")
 if p.returncode:fail(host+"_exit_"+str(p.returncode))
 return p.stdout
def validate_source(ct,name):
 code='''set -Eeuo pipefail
test "$(hostname -s)" = nodeb
test "$(pct status '''+str(ct)+''')" = "status: running"
c="$(pct config '''+str(ct)+''')"
printf '%s\n' "$c" | grep -Fxq '''+shlex.quote("hostname: "+name)+'''
if printf '%s\n' "$c" | grep -Eq '^(mp[0-9]+|dev[0-9]+|lxc.mount.entry):'; then exit 73; fi
printf '%s\n' "$c" | sed -n 's/^rootfs: \\(vmdata:subvol-'''+str(ct)+'''-disk-[0-9][0-9]*\\),.*/\\1/p' | head -1
'''
 out=run("nodeb",["bash","-c",code])
 lines=[l.strip() for l in out.splitlines() if re.fullmatch(r"vmdata:subvol-"+str(ct)+r"-disk-\d+",l.strip())]
 if len(lines)!=1:fail("source_rootfs_layout_unexpected_ct"+str(ct))
 dataset=lines[0].replace(":","/",1)
 desc=run("nodeb",["zfs","list","-Hp","-o","type,referenced",dataset])
 parts=desc.strip().split()
 if len(parts)!=2 or parts[0]!="filesystem":fail("source_dataset_not_filesystem_ct"+str(ct))
 try:size=int(parts[1])
 except ValueError:fail("source_referenced_unknown")
 if size>20*1024**3:fail("source_exceeds_20gib_ct"+str(ct))
 snapname=dataset+"@"+SNAP
 test=run("nodeb",["bash","-c","if zfs list -H -t snapshot "+shlex.quote(snapname)+" >/dev/null 2>&1; then exit 77; fi; echo OK"],12)
 if "OK" not in test:fail("source_snapshot_collision")
 return dataset,size
def validate_target(ct,target):
 script='''set -Eeuo pipefail
test "$(hostname -s)" = nodea
test ! -e /etc/pve/lxc/'''+str(ct)+'''.conf
if zfs list -H '''+shlex.quote(target)+''' >/dev/null 2>&1; then exit 79; fi
available="$(zfs list -Hp -o available vmdata)"
test "$available" -ge 5368709120
echo TARGET_FREE
'''
 if "TARGET_FREE" not in run("nodea",["bash","-c",script]):fail("destination_preflight")
def replicate(src,dst,ct,source_size):
 full=src+"@"+SNAP
 run("nodeb",["zfs","snapshot",full],25)
 guid=run("nodeb",["zfs","get","-Hp","-o","value","guid",full]).strip()
 if not re.fullmatch(r"\d+",guid):fail("source_guid_missing")
 try:
  sender=subprocess.Popen(SSH+["nodeb",shlex.join(["zfs","send","-p",full])],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  receiver=subprocess.Popen(SSH+["nodea",shlex.join(["zfs","receive","-u","-o","mountpoint=none","-o","canmount=off",dst])],
                            stdin=sender.stdout,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  sender.stdout.close()
  rc_receiver=receiver.wait(timeout=580)
  rc_sender=sender.wait(timeout=580)
 except (OSError,subprocess.TimeoutExpired):fail("zfs_stream_timeout_ct"+str(ct))
 if rc_receiver!=0 or rc_sender!=0:fail("zfs_stream_failed_ct"+str(ct))
 verification='''set -Eeuo pipefail
test "$(hostname -s)" = nodea
test "$(zfs get -H -o value guid '''+shlex.quote(dst+"@"+SNAP)+''')" = '''+shlex.quote(guid)+'''
test "$(zfs get -H -o value canmount '''+shlex.quote(dst)+''')" = off
test "$(zfs get -H -o value mountpoint '''+shlex.quote(dst)+''')" = none
test "$(zfs get -H -o value mounted '''+shlex.quote(dst)+''')" = no
test ! -e /etc/pve/lxc/'''+str(ct)+'''.conf
zfs list -Hp -o referenced '''+shlex.quote(dst)+'''
'''
 output=run("nodea",["bash","-c",verification],35)
 try:referenced=int(output.strip().splitlines()[-1])
 except (ValueError,IndexError):fail("zfs_ref_bytes_unknown")
 print("CT_"+str(ct)+"_FS_STAGED_NODEA=yes",flush=True)
 print("CT_"+str(ct)+"_SOURCE_REFERENCED_BYTES="+str(source_size),flush=True)
 print("CT_"+str(ct)+"_DEST_REFERENCED_BYTES="+str(referenced),flush=True)
 print("CT_"+str(ct)+"_SNAPSHOT_GUID_VERIFIED=yes",flush=True)
 print("CT_"+str(ct)+"_DATASET_MOUNTED=no",flush=True)
 print("CT_"+str(ct)+"_DEST_PROXMOX_GUEST_REGISTERED=no",flush=True)
def main():
 print("JNS_SOLAR_ZFS_FULL_CT_OFFLINE_STAGE_START",flush=True)
 for ct,hostname,targetid,dest in PAIRS:
  src,size=validate_source(ct,hostname)
  validate_target(targetid,dest)
  replicate(src,dest,targetid,size)
 print("JNS_SOLAR_ZFS_FULL_CT_OFFLINE_STAGE_COMPLETE",flush=True)
 print("ORIGINAL_MQTT_AND_ZIGBEE_RUNNING=yes",flush=True)
 print("FINAL_QUIESCED_SYNC_NEEDED=yes",flush=True)
if __name__=="__main__":main()
