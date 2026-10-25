#!/usr/bin/env python3
"""JNS Solar HA900 cold archive to Node C NAS, using native Proxmox VMA.
Source: verified STOPPED VM900 on Node A, preserving all disks until archive passes
on-destination SHA256 + full VMA record verification.
Destination: private directory in Node C NFS. No NAS mount changes, no VM destroy.
"""
import base64,datetime,hashlib,json,os,pathlib,re,shlex,shutil,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
SRC=r'''
import datetime,hashlib,json,os,pathlib,re,subprocess,sys
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":
 raise SystemExit(70)
def cmd(args,timeout=25):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError("command_failed")
 return p.stdout
def assert_stopped():
 if cmd(["qm","status","900"]).strip()!="status: stopped":raise RuntimeError("VM900_NOT_STOPPED")
 cfg=cmd(["qm","config","900"])
 if not re.search(r"^name:\s+homeassistant-recovery\s*$",cfg,re.M):raise RuntimeError("NAME_MISMATCH")
 if not re.search(r"^onboot:\s+0\s*$",cfg,re.M):raise RuntimeError("ONBOOT_NOT_DISABLED")
 for slot,vol in (("scsi0","vmdata:vm-900-disk-1"),
                  ("efidisk0","vmdata:vm-900-disk-0")):
  if not re.search(r"^"+slot+r":\s+"+vol+r"(?:,|\s|$)",cfg,re.M):raise RuntimeError("DISK_MISMATCH")
 return cfg
assert_stopped()
ds="vmdata/jns-solar-ha900-vzdump-20261025"
if subprocess.run(["zfs","list","-H",ds],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
 raise RuntimeError("STAGING_DATASET_ALREADY_EXISTS")
if subprocess.run(["zfs","create","-o","atime=off","-o","compression=zstd",ds],
 stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30).returncode!=0:
 raise RuntimeError("STAGING_DATASET_CREATE_FAILED")
out=cmd(["zfs","get","-Hp","-o","value","mountpoint",ds]).strip()
stage=pathlib.Path(out)
if not stage.is_dir() or out in ("/","-","none","legacy"):raise RuntimeError("INVALID_STAGING_MOUNT")
os.chmod(stage,0o700)
try:
 config=assert_stopped()
 saved=stage/"ha900-original-proxmox.conf"
 with saved.open("x") as f:f.write(config)
 os.chmod(saved,0o600)
 with (stage/"vzdump-private.log").open("w") as private:
  outcome=subprocess.run(["vzdump","900","--mode","stop","--compress","zstd",
    "--dumpdir",str(stage)],stdout=private,stderr=subprocess.STDOUT,timeout=2400)
 if outcome.returncode!=0:raise RuntimeError("VZDUMP_FAILED")
 copies=list(stage.glob("vzdump-qemu-900-*.vma.zst"))
 if len(copies)!=1:raise RuntimeError("BACKUP_ARCHIVE_COUNT_UNEXPECTED")
 archive=copies[0]
 if archive.is_symlink() or not archive.is_file():raise RuntimeError("ARCHIVE_NOT_REGULAR")
 size=archive.stat().st_size
 if not (500000<size<200*1024**3):raise RuntimeError("ARCHIVE_SIZE_UNEXPECTED")
 hashval=hashlib.file_digest(archive.open("rb"),"sha256").hexdigest()
 savedsha=hashlib.file_digest(saved.open("rb"),"sha256").hexdigest()
 assert_stopped()
 print("SOURCE_READY_JSON="+json.dumps({
   "archive_path":str(archive),"archive_basename":archive.name,
   "archive_size":size,"archive_sha256":hashval,
   "config_path":str(saved),"config_sha256":savedsha,"stopped":True,
   "source_staging_dataset":ds},sort_keys=True))
except Exception:
 raise
'''
def fail(code):
 print("HA900_ARCHIVE_BLOCKED="+code,flush=True);sys.exit(1)
def remote(args,timeout=25):
 try:p=subprocess.run(SSH+["nodea",shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):fail("REMOTE_TIMEOUT")
 if p.returncode:
  # Do not emit stderr: could contain private source environment or backup logs.
  fail("SOURCE_OR_TRANSPORT_EXIT_"+str(p.returncode))
 return p.stdout
def read_source(path,maxbytes=None):
 command=SSH+["nodea",shlex.join(["cat",path])]
 return subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
def copy_stream(path,dest,expected_size,expected_sha):
 part=dest.with_name(dest.name+".part")
 if dest.exists() or part.exists():fail("DESTINATION_COLLISION")
 inp=read_source(path)
 sha=hashlib.sha256()
 size=0
 try:
  with part.open("xb") as f:
   while True:
    b=inp.stdout.read(1024*1024*4)
    if not b:break
    size+=len(b)
    if size>expected_size:fail("ARCHIVE_EXCEEDS_RECORDED_LENGTH")
    sha.update(b);f.write(b)
   f.flush();os.fsync(f.fileno())
  inp.stdout.close()
  ret=inp.wait(timeout=45)
 except (OSError,subprocess.TimeoutExpired):
  inp.kill();fail("STREAM_IO_ERROR")
 if ret!=0 or size!=expected_size or sha.hexdigest()!=expected_sha:
  fail("STREAM_INTEGRITY_FAILED")
 os.chmod(part,0o600)
 part.rename(dest)
 return size
def verify_vma(archive,private_log):
 # Full decompression and VMA stream CRC verification. No writes of
 # uncompressed 256-GB disks, and no VM instantiated on Node C.
 with private_log.open("wb") as log:
  decompressor=subprocess.Popen(["zstd","-q","-d","-c",str(archive)],
     stdout=subprocess.PIPE,stderr=log)
  verifier=subprocess.Popen(["vma","verify","/dev/stdin"],
     stdin=decompressor.stdout,stdout=log,stderr=log)
  decompressor.stdout.close()
  try:
   vr=verifier.wait(timeout=3300)
   zr=decompressor.wait(timeout=120)
  except subprocess.TimeoutExpired:
   verifier.kill();decompressor.kill();fail("VMA_VERIFY_TIMEOUT")
 if vr!=0 or zr!=0:fail("VMA_RECORD_CHECKSUM_VERIFICATION_FAILED")
def main():
 if os.geteuid()==0 or os.uname().nodename.split(".")[0]!="nodec":
  fail("RUNNER_IDENTITY")
 mount=pathlib.Path("/mnt/pve/nfs-ct")
 if subprocess.run(["findmnt","-rn","-M",str(mount)],capture_output=True).returncode!=0:
  fail("BACKUP_NFS_NOT_MOUNTED")
 statv=os.statvfs(mount)
 if (statv.f_bavail*statv.f_frsize)<150*1024**3:fail("NFS_HEADROOM")
 if not os.access(mount,os.W_OK):fail("NFS_NOT_WRITABLE")
 for executable in ("vma","zstd"):
  if shutil.which(executable) is None:fail("MISSING_"+executable)
 print("HA900_NATIVE_BACKUP_STARTED=yes",flush=True)
 code=base64.b64encode(SRC.encode()).decode()
 try:
  p=subprocess.run(SSH+["nodea",shlex.join(["python3","-c",
     "import base64;exec(base64.b64decode('"+code+"'))"])],
     capture_output=True,text=True,timeout=2550)
 except (OSError,subprocess.TimeoutExpired):fail("VZDUMP_REMOTE_TIMEOUT")
 lines=[x for x in p.stdout.splitlines() if x.startswith("SOURCE_READY_JSON=")]
 if p.returncode or len(lines)!=1:fail("SOURCE_BACKUP_NOT_VERIFIED")
 try:meta=json.loads(lines[0].split("=",1)[1])
 except ValueError:fail("BAD_SOURCE_METADATA")
 src=meta.get("archive_path","")
 source_sha=meta.get("archive_sha256","")
 source_size=meta.get("archive_size",0)
 if (meta.get("stopped") is not True or
   not re.fullmatch(r"[0-9a-f]{64}",source_sha) or
   not isinstance(source_size,int) or
   not (500000<source_size<200*1024**3) or
   not re.fullmatch(r"/[A-Za-z0-9_./-]+/vzdump-qemu-900-[0-9_-]+\.vma\.zst",src) or
   not src.endswith(meta.get("archive_basename",""))):
  fail("SOURCE_BACKUP_METADATA_INVALID")
 conf=meta.get("config_path","")
 if not re.fullmatch(r"/[A-Za-z0-9_./-]+/ha900-original-proxmox\.conf",conf):
  fail("SOURCE_CONFIG_PATH_INVALID")
 target=mount/"JNS-Solar-Archives"
 if target.exists() and (target.is_symlink() or not target.is_dir()):
  fail("UNSAFE_ARCHIVE_ROOT")
 target.mkdir(mode=0o700,exist_ok=True)
 archive_dir=target/"HA900-cold-20261025"
 if archive_dir.exists():fail("ARCHIVE_FOLDER_ALREADY_PRESENT")
 archive_dir.mkdir(mode=0o700)
 os.chmod(archive_dir,0o700)
 out=archive_dir/meta["archive_basename"]
 print("HA900_SOURCE_BACKUP_CREATED=yes",flush=True)
 print("HA900_TRANSFER_TO_NODEC_NFS_STARTED=yes",flush=True)
 copy_stream(src,out,source_size,source_sha)
 confsha=meta.get("config_sha256","")
 if not re.fullmatch(r"[a-f0-9]{64}",confsha):fail("CONFIG_SHA_INVALID")
 copy_stream(conf,archive_dir/"ha900-original-proxmox.conf",
      int(remote(["stat","-c","%s",conf]).strip()),confsha)
 print("HA900_BACKUP_ON_NFS_SHA256_VERIFIED=yes",flush=True)
 print("HA900_FULL_VMA_VERIFICATION_STARTED=yes",flush=True)
 verify_vma(out,archive_dir/"vma-verify-private.log")
 print("HA900_FULL_VMA_VERIFICATION_PASSED=yes",flush=True)
 state=remote(["bash","-c",
   'test "$(qm status 900)" = "status: stopped" && test "$(qm config 900 | sed -n \'s/^onboot: //p\')" = 0 && echo STOPPED'])
 if state.strip()!="STOPPED":fail("SOURCE_VM_STATE_CHANGED")
 manifest={
  "archive_format":"Proxmox vzdump-qemu VMA zstd",
  "vmid":900,"vm_name":"homeassistant-recovery",
  "source_host":"nodea","destination_host":"nodec",
  "state_at_backup":"stopped","source_onboot":0,
  "vzdump_archive_filename":out.name,
  "size_bytes":source_size,"sha256":source_sha,
  "proxmox_config_sha256":confsha,
  "verified":{"nfs_sha256":True,"zstd_decompress":True,"vma_verify":True,
              "source_remains_stopped":True},
  "restore_instruction":"From this VMA archive use qmrestore to a new, unused VMID on a Proxmox node with at least 256GiB of disk headroom. Keep NIC disconnected and onboot=0. Node C local-lvm cannot hold a complete restore.",
  "archived_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "source_vm_deleted":False,
 }
 info=archive_dir/"RESTORE_MANIFEST.json"
 with info.open("x") as f:json.dump(manifest,f,indent=2,sort_keys=True);f.write("\n")
 os.chmod(info,0o600)
 print("HA900_NFS_ARCHIVE_VERIFIED=yes",flush=True)
 print("HA900_NFS_ARCHIVE_BYTES="+str(source_size),flush=True)
 print("HA900_NFS_ARCHIVE_SHA256="+source_sha,flush=True)
 print("HA900_SOURCE_VM_DELETION_NOT_EXECUTED=yes",flush=True)
 print("HA900_ARCHIVAL_COMPLETE",flush=True)
if __name__=="__main__":main()
