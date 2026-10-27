#!/usr/bin/env python3
"""JNS VM902 pre-merge full safety backup, OFF-HOST verified. No guest restart.

Node C unprivileged runner orchestrates two pre-authorised SSH transports.
A: Proxmox snapshot backup in private staging (HA-Security stays running).
B: copy verified native VMA zstd and original Proxmox config to NAS.
Fail closed, never delete source, never disclose source guest secrets/log.
"""
import base64,hashlib,json,os,re,shlex,subprocess,sys
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
TAG="jns-vm902-consolidation-20261027-v1"
SOURCE_DIR="/var/lib/jns-solar/ha-p0-primary-lite-902/"+TAG
TARGET_DIR="/mnt/pve/NAS/dump/"+TAG
def fail(msg):
 print("JNS_VM902_SAFETY_BACKUP_BLOCKED="+msg,flush=True);sys.exit(1)
def remote(host,src,timeout=75):
 enc=base64.b64encode(src.encode()).decode()
 command=SSH+[host,shlex.join(["python3","-u","-c","exec(__import__('base64').b64decode('"+enc+"'))"])]
 try:r=subprocess.run(command,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):fail(host+"_transport_timeout")
 if r.returncode:fail(host+"_remote_error_"+str(r.returncode))
 return r.stdout
A=r'''
import os,subprocess,json,re,hashlib,time,sys
from pathlib import Path
TAG="jns-vm902-consolidation-20261027-v1"
def fail(msg):print("PRIVATE_STAGE_BLOCKED="+msg,flush=True);sys.exit(71)
def run(cmd,timeout=15):
 try:return subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":fail("identity")
q=run(["qm","status","902"])
c=run(["qm","config","902"])
if not q or q.returncode or q.stdout.strip()!="status: running":fail("guest_not_running")
if not c or c.returncode or not re.search(r"^name:\s*ha-p0-primary-lite\s*$",c.stdout,re.M):fail("wrong_vm")
if re.search(r"^lock:",c.stdout,re.M):fail("vm_locked")
if not re.search(r"^agent:\s*(?:enabled=)?1(?:,|$)",c.stdout,re.M):fail("agent_not_configured")
if not re.search(r"^scsi0:\s*vmdata:vm-902-disk-1,",c.stdout,re.M):fail("unexpected_disk")
if re.search(r"^(?:usb\d+|hostpci\d+|virtiofs\d+|hookscript|args):",c.stdout,re.M):fail("unsupported_passthrough")
b=run(["df","-Pk","/var/lib/jns-solar"],9)
if not b or b.returncode:fail("free_space_unknown")
free=int(b.stdout.splitlines()[-1].split()[3])
if free<11*1048576:fail("root_less_than_11g_free")
r=run(["free","-m"])
if not r or r.returncode:fail("memory_unknown")
for line in r.stdout.splitlines():
 if line.startswith("Mem:") and int(line.split()[6])<1400:fail("nodea_ram_pressure")
root=Path("/var/lib/jns-solar/ha-p0-primary-lite-902")
root.mkdir(parents=True,exist_ok=True,mode=0o700)
if root.is_symlink():fail("root_symlink")
dest=root/TAG
if dest.exists() or dest.is_symlink():fail("archive_collision")
dest.mkdir(mode=0o700)
config=dest/"vm902-proxmox.conf"
config.write_text(c.stdout)
os.chmod(config,0o600)
log=dest/"private-vzdump.log"
print("JNS_VM902_SNAPSHOT_BACKUP_START=yes",flush=True)
with log.open("w") as f:
 try:p=subprocess.run(["vzdump","902","--mode","snapshot","--compress","zstd",
                        "--dumpdir",str(dest)],stdout=f,stderr=subprocess.STDOUT,timeout=2200)
 except (OSError,subprocess.TimeoutExpired):fail("vzdump_timeout")
if p.returncode:fail("vzdump_failed_check_private_log")
vmas=list(dest.glob("vzdump-qemu-902-*.vma.zst"))
if len(vmas)!=1 or vmas[0].is_symlink():fail("expected_one_vma")
vma=vmas[0]
if not 1024*1024<vma.stat().st_size<35*1024**3:fail("archive_size_invalid")
test=run(["zstd","-q","-t",str(vma)],900)
if not test or test.returncode:fail("zstd_integrity_failed")
h=hashlib.sha256()
with vma.open("rb") as f:
 for chunk in iter(lambda:f.read(4*1024**2),b""):h.update(chunk)
q=run(["qm","status","902"])
if not q or q.returncode or q.stdout.strip()!="status: running":fail("guest_not_running_after_backup")
meta={"name":vma.name,"size":vma.stat().st_size,"sha256":h.hexdigest(),
      "config_sha256":hashlib.sha256(config.read_bytes()).hexdigest(),
      "snapshot_read_only_guest":True,"source_node":"nodea",
      "restore_tested":False,"datetime_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
mf=dest/"MANIFEST.json"
with mf.open("x") as f:json.dump(meta,f,sort_keys=True,indent=2);f.write("\n")
os.chmod(mf,0o600)
print("JNS_VM902_STAGED_METADATA="+json.dumps(meta,sort_keys=True),flush=True)
'''
B=r'''
import os,re,subprocess,json,sys
from pathlib import Path
d=Path("/mnt/pve/NAS/dump/jns-vm902-consolidation-20261027-v1")
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(68)
m=subprocess.run(["findmnt","-n","-M","/mnt/pve/NAS"],capture_output=True)
if m.returncode:raise SystemExit(69)
if not d.parent.is_dir():raise SystemExit(70)
free=subprocess.run(["df","-Pk",str(d.parent)],capture_output=True,text=True)
if free.returncode or int(free.stdout.splitlines()[-1].split()[3])<20*1048576:raise SystemExit(71)
if d.exists() or d.is_symlink():raise SystemExit(72)
d.mkdir(mode=0o700)
print("JNS_VM902_NAS_TARGET_READY=yes")
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":fail("must_run_nodec_runner")
 stage=remote("nodea",A,2400)
 marks=[s for s in stage.splitlines() if s.startswith("JNS_VM902_STAGED_METADATA=")]
 if len(marks)!=1:fail("missing_validated_stage_manifest")
 try:meta=json.loads(marks[0].split("=",1)[1])
 except ValueError:fail("invalid_stage_manifest")
 if not re.fullmatch(r"vzdump-qemu-902-[0-9_-]+\.vma\.zst",meta.get("name","")):fail("bad_filename")
 if not re.fullmatch(r"[0-9a-f]{64}",meta.get("sha256","")):fail("bad_hash")
 if not 1048576<int(meta.get("size",0))<35*1024**3:fail("bad_size")
 b=remote("nodeb",B,65)
 if "JNS_VM902_NAS_TARGET_READY=yes" not in b:fail("NAS_target_gate")
 # Copy each protected file using existing NodeC broker; stdin pipe never persisted on runner.
 for name in ("vm902-proxmox.conf",meta["name"],"MANIFEST.json"):
  src=SOURCE_DIR+"/"+name
  dest=TARGET_DIR+"/"+name
  sender=subprocess.Popen(SSH+["nodea",shlex.join(["cat",src])],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  receiver=subprocess.Popen(SSH+["nodeb",shlex.join(["bash","-c","umask 077; cat > "+shlex.quote(dest)])],
                            stdin=sender.stdout,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  sender.stdout.close()
  try:rc=receiver.wait(timeout=1500);sc=sender.wait(timeout=1500)
  except subprocess.TimeoutExpired:
   sender.kill();receiver.kill();fail("copy_timeout")
  if rc or sc:fail("copy_failed_"+name[:15])
 # Digest file on Node B, without dumping content.
 verify=String=r'''
import json,hashlib,os,sys
from pathlib import Path
p=Path("/mnt/pve/NAS/dump/jns-vm902-consolidation-20261027-v1")
m=json.loads((p/"MANIFEST.json").read_text())
def sh(f):
 h=hashlib.sha256()
 with f.open("rb") as stream:
  for z in iter(lambda:stream.read(4*1024*1024),b""):h.update(z)
 return h.hexdigest()
a=p/m["name"]
if a.stat().st_size!=m["size"] or sh(a)!=m["sha256"] or sh(p/"vm902-proxmox.conf")!=m["config_sha256"]:
 raise SystemExit(72)
print("JNS_VM902_OFFHOST_BACKUP_VERIFIED="+json.dumps({"size_bytes":m["size"],"sha256_match":True,
  "proxmox_config_match":True,"restore_tested":False,"source":m["source_node"]},sort_keys=True))
'''
 result=remote("nodeb",verify,500)
 mark=[x for x in result.splitlines() if x.startswith("JNS_VM902_OFFHOST_BACKUP_VERIFIED=")]
 if len(mark)!=1:fail("offhost_integrity_unverified")
 print(mark[0],flush=True)
 print("JNS_VM902_BACKUP_READY_FOR_MERGE=yes",flush=True)
if __name__=="__main__":main()
